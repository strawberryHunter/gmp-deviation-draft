// node --test tests/
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as E from "../src/engine.js";
import { SAMPLE_FORMS, SAMPLE_HISTORY } from "../src/sample.js";

const here = p => new URL(p, import.meta.url);
const FORMS = JSON.parse(readFileSync(here("./fixtures/forms.json")));
const CLI = JSON.parse(readFileSync(here("./fixtures/cli_expected.json")));
const V5 = JSON.parse(readFileSync(here("./fixtures/v5_results.json")));   // recorded from the published V5 page before the redesign
const HISTORY_TEXT = readFileSync(here("../../data/synthetic/history.csv"), "utf8");
const history = await E.parseHistory("history.csv", HISTORY_TEXT);
const clone = o => JSON.parse(JSON.stringify(o));
const good = () => clone(FORMS.find(f => f.file === "DEV-2026-2301.yaml").form);

async function result(form) {
  const errs = E.validate(form, history);
  if (errs.length) return { rejected: true };
  const md = E.toMarkdown(await E.buildModel(form, history));
  return {
    rejected: false,
    grade: md.match(/\*\*제안 등급: (\w+)\*\*/)[1],
    reasons: md.match(/근거:\n\n((?:- .*\n?)+)/)[1].trim().split("\n").map(x => x.slice(2)),
    rec: [...md.matchAll(/^\| (DEV-\d{4}-\d{4}) \| \d{4}-\d{2}-\d{2} \|/gm)].map(x => x[1]),
    recUnchecked: md.includes("반복성 조회를 하지 않았습니다"),
  };
}

/* ---------- parity: the redesign must not change any result ---------- */
test("8 synthetic forms: same result as the CLI (devdraft)", async () => {
  assert.equal(FORMS.length, 8);
  for (const { file, form } of FORMS) {
    const got = await result(form), want = CLI[file];
    assert.equal(got.rejected, want.rejected, file);
    if (want.rejected) continue;
    assert.equal(got.grade, want.grade, file);
    assert.deepEqual(got.reasons, want.reasons, file);
    assert.deepEqual(got.rec, want.rec, file);
    assert.equal(got.recUnchecked, want.recUnchecked, file);
  }
});
test("8 synthetic forms: same result as the published V5 page", async () => {
  for (const { file, form } of FORMS) {
    const got = await result(form), want = V5[file];
    assert.equal(got.rejected, want.rejected, file);
    if (want.rejected) continue;
    assert.deepEqual([got.grade, got.reasons, got.rec, got.recUnchecked], [want.grade, want.reasons, want.rec, want.recUnchecked], file);
  }
});
test("proposal() agrees with the document model", async () => {
  for (const { file, form } of FORMS) {
    if (CLI[file].rejected) continue;
    const p = E.proposal(form, history);
    assert.equal(E.levelLabel(p.level), CLI[file].grade, file);
    assert.deepEqual(p.reasons, CLI[file].reasons, file);
    assert.deepEqual(p.rec.map(r => r.dev_id), CLI[file].rec, file);
  }
});
test("the app's bundled samples are the same 8 forms and history", () => {
  assert.deepEqual(SAMPLE_FORMS, FORMS.map(f => f.form));
  assert.equal(SAMPLE_HISTORY, HISTORY_TEXT);
});

/* ---------- judgement fields stay blank ---------- */
test("root cause, impact, CAPA and the final grade are always blank", async () => {
  for (const { file, form } of FORMS) {
    if (CLI[file].rejected) continue;
    const m = await E.buildModel(form, history);
    const at = t => m.blocks.findIndex(b => b.k === "h2" && b.runs[0].t === t);
    for (const h of ["6. 근본원인", "7. 제품 품질 영향 평가"]) {
      const b = m.blocks[at(h) + 1];
      assert.ok(b.runs[0].blank, h);
      assert.ok(!b.runs.some(r => r.user), h + " has no entered text");
    }
    const capa = m.blocks[at("8. CAPA") + 1];
    assert.ok(capa.rows.every(r => r[1][0].blank && r[2][0].t === "" && r[3][0].t === ""));
    const final = m.blocks.find(b => b.k === "p" && b.runs[0].t === "QA 검토자 확정 등급: ");
    assert.ok(final.runs[1].blank);
    assert.ok(m.blanks >= 13, "blank count " + m.blanks);
  }
});

/* ---------- validation ---------- */
test("validate: a complete form passes; each kind of problem is reported with where to fix it", () => {
  assert.deepEqual(E.validate(good(), history), []);
  let f = good(); f.detected_by = " "; f.title = "";
  let e = E.validate(f, history);
  assert.equal(e[0].code, "missing"); assert.deepEqual(e[0].targets, ["title", "detected_by"]);
  f = good(); f.flags.spec_oos = null; delete f.flags.cpp_excursion;
  e = E.validate(f, history);
  assert.equal(e[0].code, "unanswered"); assert.deepEqual(e[0].targets, ["flag-cpp_excursion", "flag-spec_oos"]);
  f = good(); f.detected_at = "어제 새벽 3시"; assert.equal(E.validate(f, history)[0].code, "when");
  f = good(); f.detected_at = "2027-11-21T14:20"; assert.equal(E.validate(f, history)[0].code, "future");
  f = good(); f.today = "2026-13-40"; assert.equal(E.validate(f, history)[0].code, "today");
  f = good(); f.category = "장비"; assert.equal(E.validate(f, history)[0].code, "category");
  f = good(); f.title = "a\nb"; assert.equal(E.validate(f, history)[0].code, "newline");
  f = good(); f.synthetic = false; assert.equal(E.validate(f, history)[0].code, "synthetic-history");
  assert.deepEqual(E.validate(f, null), [], "a real form without history is drafted (lookup not done)");
});
test("missingRequired: an unanswered question is never read as no", () => {
  const f = E.blankForm("2026-11-24");
  const m = E.missingRequired(f);
  assert.equal(m.fields.length, 11); assert.equal(m.flags.length, 8);
  assert.equal(E.proposal(f, history), null);
});

/* ---------- recurrence ---------- */
test("findRecurrence: same site, equipment and category within the window; not itself, not the future", () => {
  const f = clone(FORMS.find(x => x.file === "DEV-2026-2201.yaml").form);
  const rec = E.findRecurrence(f, history);
  assert.equal(rec.length, 5);
  assert.ok(rec.every(r => r.site === f.site && r.equipment_id === f.equipment_id && r.category === f.category));
  assert.ok(rec[0].opened >= rec[4].opened, "newest first");
  f.id = rec[0].dev_id; assert.equal(E.findRecurrence(f, history).length, 4, "itself excluded");
  f.id = "X"; f.today = "2026-09-01"; assert.ok(E.findRecurrence(f, history).every(r => r.opened <= "2026-09-01"));
  f.today = "2028-01-01"; assert.equal(E.findRecurrence(f, history).length, 0, "outside 365 days");
  assert.deepEqual(E.findRecurrence(f, null), []);
});
test("lookup: says why a lookup was not done", () => {
  const f = good();
  assert.equal(E.lookup(f, history).checked, true);
  assert.equal(E.lookup(f, null).why, "이력 파일 없음");
  f.equipment_id = ""; f.category = "";
  assert.deepEqual([E.lookup(f, history).checked, E.lookup(f, history).why], [false, "설비·유형 미기재"]);
  assert.deepEqual(E.unmatchedKeys(f), ["equipment_id", "category"]);
});
test("a real form never gets matches from a synthetic history", () => {
  const f = good(); f.site = "Plant A"; f.equipment_id = "CHR-03"; f.category = "process_parameter";
  assert.equal(history.synthetic, true);
  assert.equal(E.lookup(f, history).rec.length, 5, "the practice form does get them");
  f.synthetic = false;
  assert.equal(E.historyBlocked(f, history), true);
  assert.deepEqual(E.lookup(f, history), { checked: false, rec: [], why: "합성 이력" });
  const p = E.proposal(f, history);
  assert.deepEqual([p.checked, p.rec.length], [false, 0]);
  assert.ok(p.reasons.some(r => r.startsWith("반복성 조회를 하지 않음(합성 이력)")), p.reasons.join(" / "));
  assert.ok(!p.reasons.some(r => r.includes("유사 건")), "no reason built on made-up past cases");
  assert.equal(E.validate(f, history).some(e => e.code === "synthetic-history"), true, "and the form is still refused, as in the CLI");
  assert.equal(E.historyBlocked(f, null), false);
  const real = Object.assign({}, history, { synthetic: false });
  assert.equal(E.historyBlocked(f, real), false); assert.equal(E.lookup(f, real).rec.length, 5);
});
test("blockCount: only unfilled places, or something to correct", () => {
  const f = good();
  assert.deepEqual(E.blockCount(E.validate(f, history)), { n: 0, missingOnly: true });
  f.detected_by = ""; f.flags[E.RULES.required_flags[0]] = null;
  assert.deepEqual(E.blockCount(E.validate(f, history)), { n: 2, missingOnly: true });
  f.synthetic = false;
  assert.deepEqual(E.blockCount(E.validate(f, history)), { n: 3, missingOnly: false });
});
test("classify: top level reasons, lower triggers, unevaluated recurrence", () => {
  const f = good(); f.flags.cpp_excursion = true;
  const c = E.classify(f, [], true, history);
  assert.equal(c.level, "critical"); assert.deepEqual(c.lower, [["major", "주요 공정 변수(CPP) 기준 이탈"]]); assert.equal(c.note, "");
  const g = good(); g.flags.data_integrity_concern = false;
  assert.equal(E.classify(g, [], true, history).level, "minor");
  const u = E.classify(g, [], false, null);
  assert.ok(u.reasons[0].startsWith("반복성 조회를 하지 않음(이력 파일 없음)")); assert.ok(u.note.includes("반복 기준 미평가"));
  assert.equal(E.matchedTriggers(g, 2).length, 1);
  assert.equal(E.hasRecTrigger(), true);
  assert.equal(E.plan(g)[0][0], "Man");
});

/* ---------- history file ---------- */
test("parseCSV: quotes, embedded commas and CRLF", () => {
  assert.deepEqual(E.parseCSV('a,b\r\n"x, y","he said ""hi"""\n\n'), [["a", "b"], ["x, y", 'he said "hi"']]);
});
test("parseHistory: reads Excel's BOM; names the problem and the next step", async () => {
  const h = await E.parseHistory("h.csv", "﻿" + HISTORY_TEXT);
  assert.equal(h.rows.length, 51); assert.equal(h.synthetic, true); assert.equal(h.rows[0].dev_id, "DEV-2025-1026");
  await assert.rejects(E.parseHistory("h.csv", ""), e => e instanceof E.HistoryError && e.message === "빈 파일" && !!e.next);
  await assert.rejects(E.parseHistory("h.csv", "dev_id,opened\nA,2026-01-01\n"), e => e.message.startsWith("필수 열 없음: site"));
  const head = "dev_id,opened,site,equipment_id,category,final_class\n";
  await assert.rejects(E.parseHistory("h.csv", head + "A,2026-01-01,P,E,equipment,minor\nA,2026/01/02,P,E,equipment,minor\n"),
    e => e.message.includes("dev_id 중복") && e.message.includes("YYYY-MM-DD"));
});
test("pickHistory: the bundled synthetic history is never used for a real form", () => {
  const sample = { synthetic: true }, user = { synthetic: false };
  assert.equal(E.pickHistory({ synthetic: true }, null, sample), sample);
  assert.equal(E.pickHistory({ synthetic: false }, null, sample), null);
  assert.equal(E.pickHistory({ synthetic: false }, user, sample), user);
  assert.equal(E.pickHistory({ synthetic: true }, user, sample), user);
});

/* ---------- document ---------- */
test("the rules in the page are config/rules.yaml, and a draft records that file's SHA-256 like the CLI", async () => {
  const F = JSON.parse(readFileSync(here("./fixtures/rules.json"))), R = F.rules;
  const same = ["sop_reference", "required_fields", "required_flags", "levels", "default_level", "default_reason", "classes", "manual_checks", "categories"];
  for (const k of same) assert.deepEqual(E.RULES[k], R[k], k);
  assert.deepEqual(E.RULES.recurrence, { window_days: R.recurrence.window_days, match_on: R.recurrence.match_on });
  assert.equal(R.recurrence.show_root_cause, false, "the page never lists root causes from the history");
  assert.deepEqual(E.RULES.ishikawa, Object.entries(R.ishikawa));
  assert.deepEqual(Object.keys(R).sort(), same.concat(["recurrence", "ishikawa"]).sort(), "a key in rules.yaml the page does not know");
  assert.deepEqual(Object.keys(E.RULES).sort(), Object.keys(R).sort());
  assert.deepEqual(E.RULES_FILE, { name: F.file, sha256: F.sha256 });
  const md = E.toMarkdown(await E.buildModel(good(), history));
  assert.ok(md.includes("| 분류 규칙 | rules.yaml (SHA-256 " + F.sha256 + ") |"), "the same line as in a CLI draft");
});
// Runs fn with another rule set in force and puts the default rules back, whatever happens.
async function withRules(id, fn) { E.useRules(id); try { return await fn(); } finally { E.useRules("default"); } }
test("every rule set of the page is its rules file, key by key", () => {
  assert.deepEqual(E.RULE_SETS.map(x => x.id), ["default", "duke"]);
  for (const [set, fixture] of [[E.RULE_SETS[0], "rules.json"], [E.RULE_SETS[1], "rules_duke.json"]]) {
    const F = JSON.parse(readFileSync(here("./fixtures/" + fixture))), R = F.rules;
    assert.deepEqual([set.file, set.sha256], [F.file, F.sha256], set.id);
    assert.deepEqual(Object.keys(set.rules).sort(), Object.keys(R).sort(), set.id + ": a key the page does not know, or one it made up");
    for (const k of Object.keys(R)) {
      if (k === "recurrence") { assert.deepEqual(set.rules[k], { window_days: R[k].window_days, match_on: R[k].match_on }, set.id); assert.equal(R[k].show_root_cause, false); }
      else if (k === "ishikawa") assert.deepEqual(set.rules[k], Object.entries(R[k]), set.id);
      else assert.deepEqual(set.rules[k], R[k], set.id + " " + k);
    }
  }
});
test("useRules: swaps the rules in force in place, refuses an unknown name", async () => {
  const rules = E.RULES, file = E.RULES_FILE;
  assert.equal(E.activeRuleSet().id, "default");
  await withRules("duke", () => {
    assert.equal(E.RULES, rules, "the same object, so the page's reference stays valid"); assert.equal(E.RULES_FILE, file);
    assert.equal(E.activeRuleSet().id, "duke");
    assert.deepEqual(E.RULES.levels.map(l => l.id), ["repeat", "not_repeat"]);
    assert.equal(E.RULES.recurrence.window_days, 730);
    assert.equal(E.RULES_FILE.name, "rules_Duke_COMM-PAS-013.yaml");
    assert.deepEqual([E.levelTone("repeat"), E.levelTone("not_repeat")], ["major", "minor"], "no red for a rule set without a critical grade");
    E.RULES.levels.push({ id: "x", label: "x" });   // a change to the rules in force must not reach the stored set
  });
  assert.equal(E.activeRuleSet().id, "default");
  assert.deepEqual(E.RULES.levels.map(l => l.id), ["critical", "major", "minor"]);
  assert.deepEqual(E.RULE_SETS[1].rules.levels.map(l => l.id), ["repeat", "not_repeat"]);
  assert.deepEqual(["critical", "major", "minor"].map(E.levelTone), ["critical", "major", "minor"]);
  assert.throws(() => E.useRules("nope"), /모르는 규칙 묶음: nope/);
  assert.equal(E.activeRuleSet().id, "default", "a refused name changes nothing");
});
test("8 synthetic forms under the Duke example rules: same proposal and the same draft sections 3 and 4 as the CLI", async () => {
  const DUKE = JSON.parse(readFileSync(here("./fixtures/cli_expected_duke.json")));
  const lines = t => t.split("\n").map(l => l.trimEnd()).filter(Boolean).join("\n");   // the two writers differ only in blank lines
  await withRules("duke", async () => {
    let drafted = 0;
    for (const { file, form } of FORMS) {
      const want = DUKE[file], rejected = E.validate(form, history).length > 0;
      assert.equal(rejected, want.rejected, file);
      if (rejected) continue;
      const m = await E.buildModel(form, history), md = E.toMarkdown(m);
      assert.equal(md.match(/\*\*제안 등급: (.+?)\*\*/)[1], want.grade, file);
      assert.equal(lines(md.slice(md.indexOf("## 3. 분류 (제안)"), md.indexOf("## 5. 조사 계획"))), lines(want.sections), file);
      assert.equal(E.proposal(form, history).level, m.level, file);
      assert.ok(md.includes("| 분류 규칙 | rules_Duke_COMM-PAS-013.yaml (SHA-256 " + E.RULE_SETS[1].sha256 + ") |"), file);
      assert.equal(md.split("- ☐ SOP ").length - 1, 6, file + ": the six clauses the tool does not judge, each a box for the reviewer");
      assert.equal(m.boxes, 6); drafted++;
    }
    assert.equal(drafted, 7);
    assert.deepEqual(Object.values(DUKE).filter(w => !w.rejected).map(w => w.grade).sort().filter((g, i, a) => a.indexOf(g) === i),
      ["Repeat Deviation (SOP 4.26)", "Repeat Deviation 해당 없음"], "both levels occur in the reference");
  });
  // Back on the default rules the same form gets its usual proposal: nothing of the other set is left behind.
  assert.equal((await result(FORMS[0].form)).grade, CLI[FORMS[0].file].grade);
});
test("toMarkdown: bold markers hug the words (a space inside them shows as literal asterisks)", async () => {
  for (const { form } of FORMS) {
    if (E.validate(form, history).length) continue;
    const md = E.toMarkdown(await E.buildModel(form, history));
    assert.ok(md.includes("\n**QA 검토자 확정 등급:** ☐ **작성 필요**\n"), "as in the CLI draft");
    assert.ok(md.includes("\n**제안과 다를 경우 사유:** ☐ **작성 필요**\n"));
    for (const m of md.matchAll(/\*\*(.+?)\*\*/g)) assert.equal(m[1], m[1].trim(), "bold span with outer space: [" + m[1] + "]");
  }
});
test("toMarkdown: entered text is shown as entered (a | does not shift table columns)", async () => {
  const f = good(); f.parameters = [{ name: "Glove leak | port 4", spec: "Pass", actual: "Fail*", duration: "" }];
  const md = E.toMarkdown(await E.buildModel(f, history));
  assert.ok(md.includes("| Glove leak \\| port 4 | Pass | Fail\\* |  |"));
  assert.equal(E.mdInline("#4 포트"), "\\#4 포트");
  assert.equal(E.mdInline("3.40-3.60"), "3.40-3.60");
});
test("the form hash covers risk answers and parameters (V5 hashed top-level keys only)", async () => {
  const a = good(), b = good(); b.flags.patient_safety_impact = true;
  const c = good(); c.parameters[0].actual = "97.0%";
  const [ma, mb, mc] = [await E.buildModel(a, history), await E.buildModel(b, history), await E.buildModel(c, history)];
  assert.notEqual(ma.formSha, mb.formSha); assert.notEqual(ma.formSha, mc.formSha);
  assert.equal(ma.formSha, (await E.buildModel(good(), history)).formSha, "same input, same hash");
  assert.equal(E.canonical({ b: 1, a: [{ d: 1, c: 2 }] }), '{"a":[{"c":2,"d":1}],"b":1}');
  assert.equal((await E.sha256("abc")), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});
test("buildDocx: draft stamp in the header, blanks highlighted, entered text present", async () => {
  const D = createRequire(import.meta.url)("../vendor/docx-8.5.0.umd.js");
  const m = await E.buildModel(good(), history);
  const dir = mkdtempSync(join(tmpdir(), "dd-")); const file = join(dir, "t.docx");
  writeFileSync(file, await D.Packer.toBuffer(E.buildDocx(m, D)));
  const xml = n => execFileSync("unzip", ["-p", file, n], { encoding: "utf8" });
  assert.ok(xml("word/header1.xml").includes("초안 — 승인 문서 아님"));
  const doc = xml("word/document.xml");
  assert.equal(doc.split('<w:highlight w:val="yellow"/>').length - 1, m.blanks);
  assert.ok(doc.includes("SEC-HPLC 순도 시험 수동 재적분"));
  assert.throws(() => E.buildDocx(m, null), /Word 변환 모듈 없음/);
  await withRules("duke", async () => {   // the reviewer's check boxes of another rule set are highlighted like the blanks
    const md = await E.buildModel(good(), history), f2 = join(dir, "d.docx");
    writeFileSync(f2, await D.Packer.toBuffer(E.buildDocx(md, D)));
    const x = execFileSync("unzip", ["-p", f2, "word/document.xml"], { encoding: "utf8" });
    assert.equal(md.boxes, 6);
    assert.equal(x.split('<w:highlight w:val="yellow"/>').length - 1, md.blanks + md.boxes);
    assert.ok(x.includes("SOP 8.4.2: Severity"));
  });
  assert.equal(m.boxes, 0);
  // Fonts and headings as in the CLI's Word file, not the library's blue defaults.
  const styles = xml("word/styles.xml"), style = id => styles.match(new RegExp('<w:style [^>]*w:styleId="' + id + '"[\\s\\S]*?</w:style>'))[0];
  const fonts = styles.match(/<w:rFonts[^>]*>/g);
  assert.ok(fonts.length >= 5, "document default, Normal and three headings");
  assert.ok(style("Normal").includes('w:eastAsia="Malgun Gothic"'));
  assert.ok(!doc.includes('<w:b w:val="false"/>'), "no run switches bold off (it would undo the heading style)");
  assert.ok(/<w:pStyle w:val="Heading1"\/><\/w:pPr><w:r><w:t[^>]*>Deviation 보고서 초안/.test(doc), "heading text carries no formatting of its own");
  for (const f of fonts) for (const a of ['w:ascii="Arial"', 'w:hAnsi="Arial"', 'w:cs="Arial"', 'w:eastAsia="Malgun Gothic"']) assert.ok(f.includes(a), "Arial for Latin, Malgun Gothic for Korean: " + f);
  for (const [id, size] of [["Heading1", 30], ["Heading2", 24], ["Heading3", 22]]) {
    const s = style(id);
    assert.ok(s.includes("<w:b/>") && s.includes('<w:color w:val="000000"/>') && s.includes('<w:sz w:val="' + size + '"/>'), id + ": " + s);
  }
  // Tables carry real widths (the library's default of 100 twips per column draws as one letter per line outside Word).
  const page = doc.match(/<w:pgSz w:w="(\d+)"[^>]*\/><w:pgMar[^>]*w:right="(\d+)"[^>]*w:left="(\d+)"/);
  assert.equal(Number(page[1]) - Number(page[2]) - Number(page[3]), E.DOCX_TEXT_WIDTH, "text width of the page the library writes");
  const tables = doc.match(/<w:tbl>[\s\S]*?<\/w:tbl>/g);
  assert.ok(tables.length >= 6, "tables found: " + tables.length);
  for (const t of tables) {
    const grid = [...t.matchAll(/<w:gridCol w:w="(\d+)"\/>/g)].map(x => Number(x[1])), sum = grid.reduce((a, b) => a + b, 0);
    assert.ok(grid.every(w => w >= 2000), "column widths " + grid.join(","));
    assert.ok(sum <= E.DOCX_TEXT_WIDTH && sum > E.DOCX_TEXT_WIDTH - grid.length, "columns fill the text width: " + sum);
    assert.ok(t.includes('<w:tblW w:type="dxa" w:w="' + E.DOCX_TEXT_WIDTH + '"/>'));
    const mar = (t.match(/<w:tblCellMar>.*?<\/w:tblCellMar>/) || [""])[0];
    for (const [side, w] of [["top", 40], ["bottom", 40], ["left", 100], ["right", 100]]) assert.ok(mar.includes('<w:' + side + ' w:type="dxa" w:w="' + w + '"/>'), "cell padding " + side + ": " + mar);
    const cells = t.split("<w:tc>").length - 1, sized = [...t.matchAll(/<w:tcW w:type="dxa" w:w="(\d+)"\/>/g)].map(x => Number(x[1]));
    assert.equal(sized.length, cells, "every cell has a width"); assert.ok(sized.every(w => w === grid[0]));
    const rows = t.match(/<w:tr>[\s\S]*?<\/w:tr>/g);
    assert.ok(rows.length >= 1 && rows.every(r => /^<w:tr><w:trPr>(?:(?!<\/w:trPr>).)*<w:cantSplit\/>/.test(r)), "no row is split across two pages");
  }
});

/* ---------- workspace calculations ---------- */
test("dueDate / dday / ddayLabel / shortDate", () => {
  const f = good();
  assert.equal(E.dueDate(f, 30), "2026-12-24");
  f.detected_at = "2026-12-20 08:00"; assert.equal(E.dueDate(f, 30), "2027-01-19");
  f.detected_at = "2028-02-28T08:00"; assert.equal(E.dueDate(f, 2), "2028-03-01", "leap year");
  f.detected_at = ""; assert.equal(E.dueDate(f, 30), null);
  f.detected_at = "2026-02-31T08:00"; assert.equal(E.dueDate(f, 30), null);
  assert.equal(E.dueDate(good(), 1.5), null); assert.equal(E.dueDate(good(), -1), null);
  assert.equal(E.dday("2026-12-24", "2026-11-26"), 28);
  assert.equal(E.dday("2026-11-26", "2026-11-26"), 0);
  assert.equal(E.dday("2026-11-24", "2026-11-26"), -2);
  assert.deepEqual([E.ddayLabel(28), E.ddayLabel(0), E.ddayLabel(-2)], ["D-28", "D-DAY", "D+2"]);
  assert.equal(E.shortDate("2026-12-04"), "12/4"); assert.equal(E.shortDate(null), "");
  assert.equal(E.todayISO(new Date(2026, 10, 26, 0, 30)), "2026-11-26");
  assert.ok(E.isISODate("2028-02-29")); assert.ok(!E.isISODate("2026-02-29")); assert.ok(!E.isISODate("2026/02/01"));
});
test("completeness and stepIssues: which step still needs what", () => {
  const f = good();
  assert.deepEqual([E.completeness(f).done, E.completeness(f).total], [19, 19]);
  assert.deepEqual(E.stepIssues(f, history), [0, 0, 0, 0, 0, 0, 0, 0]);
  f.title = ""; f.batch = ""; f.site = ""; f.flags.spec_oos = null; f.immediate_actions = "";
  const c = E.completeness(f);
  assert.deepEqual([c.done, c.fieldsDone, c.flagsDone], [14, 7, 7]);
  assert.deepEqual(E.stepIssues(f, history), [1, 2, 0, 1, 0, 1, 0, 0]);
  const g = good(); g.synthetic = false; g.detected_at = "2027-01-01T00:00";
  assert.deepEqual(E.stepIssues(g, history), [0, 0, 1, 0, 0, 0, 1, 1]);
  assert.deepEqual([E.stepOfTarget("flag-spec_oos"), E.stepOfTarget("step-s7"), E.stepOfTarget("batch"), E.stepOfTarget("today")], [5, 6, 1, 7]);
});
test("inspect and statusOf", () => {
  const f = good();
  const i = E.inspect(f, history, 30, "2026-11-26");
  assert.deepEqual([i.errs.length, i.level, i.due, i.dd, i.look.checked], [0, "critical", "2026-12-24", 28, true]);
  assert.equal(E.statusOf({ exported: false, done: false }, []), "drafting");
  assert.equal(E.statusOf({ exported: true, done: false }, []), "review");
  assert.equal(E.statusOf({ exported: true, done: true }, []), "done");
  assert.equal(E.statusOf({ exported: true, done: true }, [{ code: "missing" }]), "drafting", "a form with something missing is never review or done");
  const miss = good(); miss.detected_by = "";
  const mi = E.inspect(miss, history, 30, "2026-11-26");
  assert.deepEqual([mi.level, mi.prop.level], ["none", "critical"], "answers alone give a provisional grade, but no proposal until the form is complete");
  const b = E.inspect(E.blankForm("2026-11-26"), null, 30, "2026-11-26");
  assert.deepEqual([b.level, b.due, b.dd], ["none", null, null]);
});
test("cloneForNew: place and people are kept; the event and every risk answer are not", () => {
  const f = good(), n = E.cloneForNew(f, "2026-11-26");
  for (const k of E.CLONE_KEEPS) assert.equal(n[k], f[k], k);
  for (const k of ["id", "title", "batch", "detected_at", "description", "immediate_actions"]) assert.equal(n[k], "", k);
  assert.deepEqual(n.parameters, []);
  assert.ok(Object.values(n.flags).every(v => v === null)); assert.equal(Object.keys(n.flags).length, 8);
  assert.deepEqual([n.today, n.synthetic], ["2026-11-26", true]);
});
test("suggestions: most used first, blanks left out", () => {
  const s = E.suggestions(FORMS.map(f => f.form));
  assert.equal(s.site[0], "Plant A"); assert.ok(!s.equipment_id.includes(""));
  assert.deepEqual(Object.keys(s), E.SUGGEST_FIELDS);
});
test("parseParamPaste: a copied Excel range becomes measurement rows, text unchanged", () => {
  assert.deepEqual(E.parseParamPaste("항목\t기준\t실측\t비고\r\nElution pH\t3.40-3.60\t3.62\t6 min\r\nTOC\t≤ 500 ppb\t412 ppb\r\n\r\n"),
    [{ name: "Elution pH", spec: "3.40-3.60", actual: "3.62", duration: "6 min" }, { name: "TOC", spec: "≤ 500 ppb", actual: "412 ppb", duration: "" }]);
  assert.deepEqual(E.parseParamPaste("a\tb\tc\td\te"), [{ name: "a", spec: "b", actual: "c", duration: "d e" }]);
  assert.deepEqual(E.parseParamPaste("=1+1\tx"), [{ name: "=1+1", spec: "x", actual: "", duration: "" }], "kept as text");
  assert.deepEqual(E.parseParamPaste("한 칸짜리 문장"), [], "a single cell is an ordinary paste");
  assert.deepEqual(E.parseParamPaste(""), []);
});
test("missingLabel: names what is missing, up to two", () => {
  const f = good(); assert.equal(E.missingLabel(f), "");
  f.detected_by = ""; assert.equal(E.missingLabel(f), "빠짐 · 발견자");
  f.flags.spec_oos = null; assert.equal(E.missingLabel(f), "빠짐 · 발견자, 규격 이탈(OOS)");
  f.title = ""; assert.equal(E.missingLabel(f), "필수 3개 빠짐");
});
test("isDraftShape: stored data that this version cannot open is recognised", () => {
  assert.equal(E.isDraftShape({ uid: "d1", form: good() }), true);
  assert.equal(E.isDraftShape({ uid: "d1", form: { id: "x" } }), false);
  assert.equal(E.isDraftShape({ form: good() }), false);
  assert.equal(E.isDraftShape(null), false);
  const f = good(); f.parameters = "x"; assert.equal(E.isDraftShape({ uid: "d", form: f }), false);
});
test("agoLabel", () => {
  const now = 1e12;
  assert.deepEqual([0, 59e3, 5 * 60e3, 3 * 3600e3, 50 * 3600e3].map(d => E.agoLabel(now - d, now)),
    ["방금 저장", "방금 저장", "5분 전 저장", "3시간 전 저장", "2일 전 저장"]);
});

/* ---------- lists ---------- */
function items() {
  return FORMS.map(({ form }, n) => Object.assign({ form, savedAt: n }, E.inspect(form, history, 30, "2026-12-22"),
    { status: E.statusOf({ exported: n === 1, done: n === 0 }, E.validate(form, history)) }));
}
test("filterItems: status, category, level, site, quick filters and search", () => {
  const all = items();
  const none = { status: "all", category: "", level: "", site: "", quick: "" };
  assert.equal(E.filterItems(all, none, "").length, 8);
  assert.deepEqual(E.filterItems(all, { ...none, status: "done" }, "").map(i => i.form.id), ["DEV-2026-2201"]);
  assert.deepEqual(E.filterItems(all, { ...none, status: "review" }, "").map(i => i.form.id), ["DEV-2026-2202"]);
  assert.equal(E.filterItems(all, { ...none, level: "critical" }, "").length, 3);
  assert.deepEqual(E.filterItems(all, { ...none, level: "none" }, "").map(i => i.form.id), ["DEV-2026-2204"], "a form with something missing has no proposed grade");
  assert.equal(E.filterItems(all, { ...none, level: "major" }, "").length, 3);
  assert.ok(E.filterItems(all, { ...none, category: "documentation" }, "").every(i => i.form.category === "documentation"));
  assert.deepEqual(E.filterItems(all, { ...none, quick: "missing" }, "").map(i => i.form.id), ["DEV-2026-2204"]);
  assert.deepEqual(E.filterItems(all, { ...none, quick: "recur" }, "").map(i => i.form.id), ["DEV-2026-2201", "DEV-2026-2204"], "the two forms with matching past records");
});
test("filterItems: due filters skip finished drafts; search looks at id, title, equipment, batch, product", () => {
  const all = items();
  const none = { status: "all", category: "", level: "", site: "", quick: "" };
  const week = E.filterItems(all, { ...none, quick: "week" }, "");
  assert.ok(week.length > 0 && week.every(i => i.dd >= 0 && i.dd <= 7 && i.status !== "done"));
  assert.ok(E.filterItems(all, { ...none, quick: "today" }, "").every(i => i.dd === 0));
  assert.ok(E.filterItems(all, { ...none, quick: "overdue" }, "").every(i => i.dd < 0));
  assert.deepEqual(E.filterItems(all, none, "hplc-07").map(i => i.form.id), ["DEV-2026-2301"]);
  assert.equal(E.filterItems(all, none, "없는 검색어").length, 0);
});
test("sortItems: by due date, last saved or number; never by grade", () => {
  const all = items();
  const due = E.sortItems(all, "due").map(i => i.dd);
  assert.deepEqual(due, due.slice().sort((a, b) => a - b));
  assert.equal(E.sortItems(all, "saved")[0].savedAt, 7);
  assert.equal(E.sortItems(all, "id")[0].form.id, "DEV-2026-2201");
  assert.deepEqual(E.sortItems(all, "grade"), all, "unknown sort leaves the order alone");
});
test("heroItems: nearest due date among open drafts; without dates, most items missing", () => {
  const all = items();
  const hero = E.heroItems(all, 3);
  assert.equal(hero.length, 3); assert.ok(hero.every(i => i.status !== "done")); assert.ok(hero[0].dd <= hero[1].dd);
  const undated = all.map(i => ({ ...i, dd: null, due: null }));
  assert.equal(E.heroItems(undated, 1)[0].form.id, "DEV-2026-2204");
});

/* ---------- exports ---------- */
test("guardCell / toTSV / toCSV: nothing typed in a form can run as a formula in Excel", () => {
  assert.deepEqual(["=1+1", "+1", "-1", "@x", "\tq", "ok", 3, null].map(E.guardCell), ["'=1+1", "'+1", "'-1", "'@x", "'\tq", "ok", "3", ""]);
  assert.equal(E.toTSV(["a", "b"], [["x\ty", "=HYPERLINK(\"u\")"], ["line1\nline2", 2]]), "a\tb\nx y\t'=HYPERLINK(\"u\")\nline1 line2\t2\n");
  assert.equal(E.toCSV(["a", "b"], [['say "hi"', "x,y"], ["=1", "-2"]]), '﻿a,b\r\n"say ""hi""","x,y"\r\n\'=1,\'-2\r\n');
});
test("summaryRows: proposals only; forms with something missing have no grade", () => {
  const rows = E.summaryRows(items());
  assert.equal(rows[0].length, E.SUMMARY_HEAD.length);
  assert.deepEqual(rows[0].slice(0, 5), ["DEV-2026-2201", "Protein A 크로마토그래피 용출 pH 상한 이탈", "MAJOR (제안)",
    "주요 공정 변수(CPP) 기준 이탈; 다른 배치 영향 가능성; 조회 기간 내 동일 사업장·설비·유형 반복 (2회 이상) — 유사 건 5건", "5"]);
  assert.deepEqual([rows[2][2], rows[2][4]], ["MINOR (제안, 반복 기준 미평가)", "조회 안 함"]);
  assert.deepEqual(rows[3].slice(2, 5).concat(rows[3][7]), ["", "", "", "필수 항목 누락: 발견자"]);
  assert.ok(!E.SUMMARY_HEAD.some(h => /확정|우선|근본원인/.test(h)));
});
test("mailSummary: facts and the proposal; judgement items listed as still to write", () => {
  const all = items();
  const text = E.mailSummary(all[4], 30);
  assert.ok(text.startsWith("[Deviation 초안] DEV-2026-2301 · SEC-HPLC"));
  assert.ok(text.includes("도구 제안 등급: CRITICAL (제안, QA 확정 전)"));
  assert.ok(text.includes("보고 기한: 2026-12-24 (발견일 + 30일, 설정값)"));
  assert.ok(text.includes("담당자 작성 필요: 근본원인, 제품 품질 영향 평가, CAPA, QA 검토자 확정 등급"));
  assert.ok(E.mailSummary(all[2], 30).includes("조회 안 함 (설비 미기재)"));
  assert.throws(() => E.mailSummary(all[3], 30), /필수 항목이 빠진/);
  assert.equal(E.fileBase(" DEV 2026/1 "), "DEV_2026_1_draft"); assert.equal(E.fileBase(""), "deviation_draft");
  assert.equal(E.blankForm("2026-01-01").today, "2026-01-01");
});

/* ---------- YAML intake forms: read exactly as the CLI reads them ---------- */
import { TEMPLATE_COMMENTS } from "../src/sample.js";
const YAML_CASES = JSON.parse(readFileSync(here("./fixtures/yaml_cases.json")));
const FORMS_YAML = Object.fromEntries(FORMS.map(({ file }) => [file,
  readFileSync(here("../../data/synthetic/" + (file < "DEV-2026-23" ? "intake/" : "showcase/") + file), "utf8")]));

test("parseFormYAML: every reference text reads the same as the CLI's form loader, or is refused", () => {
  assert.ok(YAML_CASES.length >= 40);
  for (const c of YAML_CASES) {
    if (c.error || c.web === "refuse") {
      assert.throws(() => E.parseFormYAML(c.text), E.YamlError, c.name + " must be refused");
    } else {
      let got;
      assert.doesNotThrow(() => { got = E.parseFormYAML(c.text); }, c.name);
      assert.deepEqual(got, c.value, c.name);
    }
  }
});
test("parseFormYAML: errors carry the line number", () => {
  assert.throws(() => E.parseFormYAML("a: 1\nb: x: y\n"), e => e instanceof E.YamlError && e.line === 2);
  assert.throws(() => E.parseFormYAML("a: 1\na: 2\n"), e => e.line === 2 && e.message.includes("같은 항목이 두 번"));
});
test("the 8 synthetic YAML files become the same forms the CLI fixtures hold", () => {
  for (const { file, form } of FORMS) {
    const r = E.formFromRaw(E.parseFormYAML(FORMS_YAML[file]), "2026-11-24", TEMPLATE_COMMENTS);
    assert.deepEqual(r.errors, [], file); assert.deepEqual(r.notes, [], file);
    assert.deepEqual(r.form, form, file);
  }
});
test("formFromRaw: what the CLI refuses is refused; odd answers are imported as unanswered and reported", () => {
  const T = TEMPLATE_COMMENTS;
  let r = E.formFromRaw(E.parseFormYAML("id: X\nroot_cause: 추정\ncapa: y\n"), "2026-11-26", T);
  assert.deepEqual([r.form, r.errors], [null, ["알 수 없는 항목: capa, root_cause"]]);
  r = E.formFromRaw(E.parseFormYAML("id: X\ntitle: 제목# [필수] 한 줄 제목. 무엇이 기준과 달랐는지. 원인을 제목에 넣지 않습니다.\n"), "2026-11-26", T);
  assert.ok(r.errors[0].startsWith("값에 양식 주석이 붙어 있음: title"));
  r = E.formFromRaw(E.parseFormYAML("parameters: text\n"), "2026-11-26", T);
  assert.ok(r.errors[0].startsWith("parameters는"));
  r = E.formFromRaw(E.parseFormYAML("id: X\nbatch: 0412\ndetected_at: 2026-11-21 14:20\nspec_oos: no\ncpp_excursion: true\nsynthetic: yes\nparameters:\n- name: pH\n  actual: 3.40\n"), "2026-11-26", T);
  assert.deepEqual(r.errors, []);
  assert.deepEqual([r.form.batch, r.form.detected_at, r.form.flags.spec_oos, r.form.flags.cpp_excursion, r.form.synthetic, r.form.today], ["0412", "2026-11-21T14:20", null, true, false, "2026-11-26"]);
  assert.deepEqual(r.form.parameters, [{ name: "pH", spec: "", actual: "3.40", duration: "" }]);
  assert.equal(r.notes.length, 2); assert.ok(r.notes[1].includes("규격 이탈(OOS): 'no' → 미응답"));
  assert.deepEqual(E.gluedTemplateComments({ a: "plain", b: 3 }, T), []);
  assert.ok(E.FORM_KEYS.includes("regulatory_report_required") && E.FORM_KEYS.length === 23);
});

/* ---------- a draft form as a CLI intake file ---------- */
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
// These two tests run the CLI itself (the repository's Python). PYTHON overrides which one; otherwise the repo's .venv, then the python on PATH.
const REPO = fileURLToPath(here("../../"));
const VENV = join(REPO, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const PY = process.env.PYTHON || (existsSync(VENV) ? VENV : process.platform === "win32" ? "python" : "python3");
// Characters a YAML file may not hold raw, or would read as a line break: bell, NEL, line separator, byte order mark.
const ODD = [0x07, 0x85, 0x2028, 0xfeff].map(c => String.fromCharCode(c)).join(" ");
const tricky = () => {
  const f = good();
  Object.assign(f, { id: "DEV-2026-9: 9", title: "# 로 시작 · 값: 콜론 \"따옴표\" 'ㅁ' \\ 역슬래시", site: "  앞뒤 공백  ", area: "true", product: "null", batch: "0412",
    equipment_id: "", process_step: "1:30", detected_by: "~", category: "equipment",
    description: "첫 줄\n  들여쓴 둘째 줄\n\n# 주석처럼 보이는 줄\t탭 | 세로줄 > 꺾쇠 " + ODD + " " + String.fromCodePoint(0x1f600) + " 끝 ",
    immediate_actions: "- 목록처럼 보이는 줄\n- 둘째: 값" });
  f.parameters = [{ name: "pH: 상한", spec: "3.40-3.60", actual: "3.62", duration: "" }, { name: "", spec: "'", actual: "\"", duration: "6 min # 주석 아님" }];
  f.flags.cpp_excursion = null; f.flags.spec_oos = true; f.synthetic = false;
  return f;
};
// What YAML allows unescaped in a file (its "printable" set), less the characters it reads as line breaks and the byte order mark.
const rawOk = c => c === 9 || c === 10 || (c >= 0x20 && c <= 0x7e) || (c >= 0xa0 && c <= 0xd7ff && c !== 0x2028 && c !== 0x2029) || (c >= 0xe000 && c <= 0xfffd && c !== 0xfeff) || c >= 0x10000;
test("toFormYAML: the page reads its own export back as the same form (finished or not, any characters)", () => {
  const forms = FORMS.map(x => x.form).concat([tricky(), E.blankForm("2026-11-24")]);
  for (const f of forms) {
    const text = E.toFormYAML(f);
    const r = E.formFromRaw(E.parseFormYAML(text), f.today, TEMPLATE_COMMENTS);
    assert.deepEqual([r.errors, r.notes], [[], []], f.id);
    assert.deepEqual(r.form, f, f.id);
    for (const ch of text) assert.ok(rawOk(ch.codePointAt(0)), "a character YAML does not allow raw: U+" + ch.codePointAt(0).toString(16) + " in " + f.id);
  }
  assert.equal(E.formFileName("DEV-2026-2201"), "DEV-2026-2201.yaml.txt");
  assert.equal(E.formFileName(" a/b:c "), "a_b_c.yaml.txt"); assert.equal(E.formFileName(""), "deviation.yaml.txt");
});
test("toFormYAML: the CLI's loader reads the same values, and the CLI gives its own result from the exported file", () => {
  const dir = mkdtempSync(join(tmpdir(), "dd-yaml-"));
  const run = args => execFileSync(PY, args, { cwd: REPO, encoding: "utf8", env: Object.assign({}, process.env, { PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" }) });
  // 1. the loader: every value comes back exactly
  const f = tricky(), file = join(dir, E.formFileName("tricky"));
  writeFileSync(file, E.toFormYAML(f));
  const raw = JSON.parse(run(["-c", "import json,sys; from devdraft.rules import form_load; print(json.dumps(form_load(open(sys.argv[1], encoding='utf-8').read())))", file]));
  for (const k of E.TEXT_FIELDS) assert.equal(raw[k], f[k], k);
  assert.deepEqual(raw.parameters, f.parameters);
  for (const k of E.RULES.required_flags) assert.equal(raw[k], f.flags[k], k);
  assert.equal("synthetic" in raw, false);
  // 2. the whole CLI: each synthetic form, exported by the page, gives the result the CLI gave from the original file
  for (const { file: name, form } of FORMS) {
    const out = mkdtempSync(join(dir, "out-")), src = join(dir, E.formFileName(form.id));
    writeFileSync(src, E.toFormYAML(form));
    let stdout;
    try { stdout = run(["-m", "devdraft.cli", src, "--today", form.today, "--out", out]); }
    catch (e) { if (e.status !== 1) throw e; stdout = e.stdout; }   // exit 1 = the form was refused, which is a result too
    const made = join(out, form.id + "_draft.md"), md = existsSync(made) ? readFileSync(made, "utf8") : null;
    const want = CLI[name];
    assert.equal(md === null, want.rejected, name + ": " + stdout);
    if (md === null) { assert.ok(stdout.includes(want.error.replace(/^ERR \S+: /, "")), name + ": " + stdout); continue; }
    assert.equal(md.match(/\*\*제안 등급: (\w+)\*\*/)[1], want.grade, name);
    assert.deepEqual(md.match(/근거:\n\n?((?:- .*\n?)+)/)[1].trim().split("\n").map(x => x.slice(2)), want.reasons, name);
    assert.deepEqual([...md.matchAll(/^\| (DEV-\d{4}-\d{4}) \| \d{4}-\d{2}-\d{2} \|/gm)].map(x => x[1]), want.rec, name);
  }
});
