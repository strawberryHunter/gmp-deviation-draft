// engine.js — rules, checks, document model and workspace calculations. No DOM.
// The judgement part (validate / classify / findRecurrence / buildModel) is the V5 logic unchanged:
// it must give the same grade, reasons and recurrence as the CLI (devdraft) on the 8 synthetic forms.
// The tool never fills root cause, impact assessment, CAPA or the final grade.

export const VERSION = "devdraft-web 0.6.0";

// The rule sets of the page. Each is a rules file of this repository as the CLI reads it, and sha256 is that file's SHA-256:
// the value the CLI prints in a draft. tests/engine.test.mjs compares each with its file (through tests/fixtures/rules*.json),
// so the page and the files cannot drift apart unnoticed. The page does not read rule files of its own.
const REQUIRED_FIELDS = ["id", "title", "site", "area", "product", "batch", "detected_at", "detected_by", "process_step", "description", "immediate_actions"];
const REQUIRED_FLAGS = ["cpp_excursion", "spec_oos", "other_batches_possibly_affected", "sterility_assurance_impacted", "released_product_affected", "data_integrity_concern", "patient_safety_impact", "regulatory_report_required"];
const CATEGORIES = ["equipment", "environmental_monitoring", "documentation", "process_parameter", "material", "personnel", "utilities"];
const ISHIKAWA = [["Man", "작업자 교육 이력, 해당 SOP 숙지 여부, 교대 인수인계"], ["Machine", "설비 정비·교정 이력, 알람 로그, 최근 변경"],
  ["Method", "SOP 버전, 배치 기록서 지시 내용과 실제 수행 비교"], ["Material", "원자재·소모품 lot, 입고 시험 결과, 보관 조건"],
  ["Measurement", "계측기 교정 상태, 분석법, 샘플링 위치·시점"], ["Milieu", "환경 모니터링 결과, 차압·온습도 추이, 유틸리티 상태"]];
export const RULE_SETS = [
  { id: "default", label: "기본 규칙", file: "rules.yaml", sha256: "31e23d7599804a61cc23c868c1b16a9c00ad999b99100b83d88365eeb1c3b63f", rules: {
    sop_reference: "",
    required_fields: REQUIRED_FIELDS,
    required_flags: REQUIRED_FLAGS,
    levels: [{ id: "critical", label: "CRITICAL" }, { id: "major", label: "MAJOR" }, { id: "minor", label: "MINOR" }],
    default_level: "minor",
    default_reason: "상위 등급 트리거에 해당 없음 (보고자 입력 기준) — 검토자 확인 필요",
    classes: {
      critical: [
        { field: "sterility_assurance_impacted", equals: true, reason: "무균 보증에 영향 가능성" },
        { field: "released_product_affected", equals: true, reason: "출하된 제품에 영향 가능성" },
        { field: "data_integrity_concern", equals: true, reason: "데이터 완전성(ALCOA+) 우려" },
        { field: "patient_safety_impact", equals: true, reason: "환자 안전에 영향 가능성" }],
      major: [
        { field: "cpp_excursion", equals: true, reason: "주요 공정 변수(CPP) 기준 이탈" },
        { field: "spec_oos", equals: true, reason: "규격 이탈(OOS) 결과" },
        { field: "other_batches_possibly_affected", equals: true, reason: "다른 배치 영향 가능성" },
        { field: "recurrence_count", min: 2, reason: "조회 기간 내 동일 사업장·설비·유형 반복 (2회 이상)" }],
    },
    manual_checks: [],
    recurrence: { window_days: 365, match_on: ["site", "equipment_id", "category"] },
    categories: CATEGORIES,
    ishikawa: ISHIKAWA,
  } },
  // config/examples/rules_Duke_COMM-PAS-013.yaml: a public SOP without Critical/Major/Minor. The tool proposes only what the SOP defines
  // (Repeat Deviation, clause 4.26) and leaves the SOP's other criteria to the reviewer as manual checks.
  { id: "duke", label: "공개 SOP 예시 · Duke COMM-PAS-013", file: "rules_Duke_COMM-PAS-013.yaml", sha256: "e80bad546c19e73189b9f7168ecf1d08592de6776d61293863739b0db5e94215", rules: {
    sop_reference: "Duke COMM-PAS-013 Rev 01 (eff. 2025-07-01) — 공개 SOP 기반 예시, Duke와 무관",
    required_fields: REQUIRED_FIELDS,
    required_flags: REQUIRED_FLAGS,
    levels: [{ id: "repeat", label: "Repeat Deviation (SOP 4.26)" }, { id: "not_repeat", label: "Repeat Deviation 해당 없음" }],
    default_level: "not_repeat",
    default_reason: "최근 2년 내 같은 사업장·설비·유형 deviation 없음 — 검토자 확인 필요 (SOP 4.26)",
    classes: { repeat: [{ field: "recurrence_count", min: 1, reason: "최근 2년 내 같은 사업장·설비·유형 deviation 재발 (SOP 4.26)" }] },
    manual_checks: [
      { clause: "3.4", text: "발견 후 3영업일 안에 deviation이 개시되었는가 (발견 일시와 QMS 개시일 대조)" },
      { clause: "8.4.2", text: "Severity·Probability·Detectability 각 1–5점과 근거를 COMM-PAS-014 기준으로 기재하고, 세 점수를 곱한 Combined Risk Score 기재 — 도구는 점수를 매기지 않음" },
      { clause: "8.4.2.1", text: "이번에 일어나지 않았지만 생길 수 있는 관련 결과까지 위험 평가에 포함했는가" },
      { clause: "8.4.3.1", text: "어느 파라미터라도 5점이면 CAPA를 검토했는가 — CAPA를 열지 않으면 Risk Assessment Summary에 근거 기재" },
      { clause: "8.8.1.2", text: "Repeat Deviation이면 trend 조사와 이전 조치의 효과성 평가를 포함했는가 (아래 4. 반복성 검토 목록 참고)" },
      { clause: "3.7.2.1", text: "관련 제품을 quarantine 했는가, 해제는 CQP 승인 후인가" }],
    history_class_labels: ["critical", "major", "minor"],   // the page shows a history row's grade as written and never warns about it
    recurrence: { window_days: 730, match_on: ["site", "equipment_id", "category"] },
    categories: CATEGORIES,
    ishikawa: ISHIKAWA,
  } },
];
// The rules in force and their file. useRules() swaps the contents in place, so every reader sees the change (the bundled page holds these two objects).
export const RULES_FILE = {};
export const RULES = {};
// Column names of the summary table (the CLI's eight). The fifth names the lookup window of the rules in force.
export const SUMMARY_HEAD = ["Deviation 번호", "제목", "제안 등급", "제안 근거", "", "발견 일시", "보고 기한", "보완 필요"];
export function useRules(id) {
  const set = RULE_SETS.find(x => x.id === id);
  if (!set) throw new Error("모르는 규칙 묶음: " + id);
  Object.keys(RULES).forEach(k => delete RULES[k]);
  Object.assign(RULES, JSON.parse(JSON.stringify(set.rules)));
  RULES_FILE.name = set.file; RULES_FILE.sha256 = set.sha256;
  SUMMARY_HEAD[4] = "반복 건 (최근 " + RULES.recurrence.window_days + "일)";
  return set;
}
export function activeRuleSet() { return RULE_SETS.find(x => x.file === RULES_FILE.name); }
useRules("default");
// Colour of a grade chip. The three grades of the default rules keep their own; in any other rule set the default level is grey and the rest orange.
export function levelTone(id) { return ["critical", "major", "minor"].includes(id) ? id : id === RULES.default_level ? "minor" : "major"; }

export const FIELD_LABEL = { id: "Deviation 번호", title: "제목", category: "유형", site: "사업장", area: "구역/실", product: "제품", batch: "배치",
  equipment_id: "설비 ID", detected_at: "발견 일시", detected_by: "발견자", process_step: "공정 단계", description: "사건 경위",
  immediate_actions: "즉시 조치", today: "초안 생성일" };
export const FLAGS = [
  ["cpp_excursion", "CPP 이탈", "주요 공정 변수(CPP)가 기준을 벗어났는가"],
  ["spec_oos", "규격 이탈(OOS)", "규격 이탈(OOS) 시험 결과가 있는가"],
  ["other_batches_possibly_affected", "타 배치 영향 가능성", "다른 배치에 영향이 있을 가능성이 있는가"],
  ["sterility_assurance_impacted", "무균 보증 영향", "무균 보증에 영향 가능성이 있는가"],
  ["released_product_affected", "출하 제품 영향", "이미 출하된 제품에 영향 가능성이 있는가"],
  ["data_integrity_concern", "데이터 완전성 우려", "데이터 완전성(ALCOA+) 우려가 있는가"],
  ["patient_safety_impact", "환자 안전 영향", "환자 안전에 영향을 줄 가능성이 있는가"],
  ["regulatory_report_required", "규제 신고 대상 가능성", "규제기관 신고 대상일 가능성이 있는가"],
];
export const DRAFT_FLAG_ORDER = ["sterility_assurance_impacted", "released_product_affected", "data_integrity_concern", "patient_safety_impact", "cpp_excursion", "spec_oos", "other_batches_possibly_affected", "regulatory_report_required"];
export const FLAG_NAME = Object.fromEntries(FLAGS.map(f => [f[0], f[1]]));
export const CAT_LABEL = { equipment: "설비", environmental_monitoring: "환경 모니터링", documentation: "문서·기록",
  process_parameter: "공정 변수", material: "원자재", personnel: "인원", utilities: "유틸리티" };
export const MATCH_LABEL = { equipment_id: "설비", category: "유형", site: "사업장" };
export const FOCUS = { equipment: ["Machine", "Method"], process_parameter: ["Machine", "Method"], environmental_monitoring: ["Milieu", "Man"],
  documentation: ["Man", "Method"], material: ["Material", "Measurement"], personnel: ["Man", "Method"], utilities: ["Milieu", "Machine"] };
export const TBD = "☐ 작성 필요";
export const TEXT_FIELDS = ["id", "title", "site", "area", "product", "batch", "equipment_id", "category", "detected_at", "detected_by", "process_step", "description", "immediate_actions"];
export const ONE_LINE = ["id", "title", "site", "area", "product", "batch", "equipment_id", "detected_by", "process_step"];
export const JUDGEMENT_FIELDS = ["근본원인", "제품 품질 영향 평가", "CAPA", "QA 검토자 확정 등급"];

// The form, in the order of the intake template.
export const STEPS = [
  { id: "s1", no: "01", name: "식별 정보", fields: ["id", "category", "title"] },
  { id: "s2", no: "02", name: "발생 위치 / 대상", fields: ["site", "area", "product", "batch", "equipment_id", "process_step"] },
  { id: "s3", no: "03", name: "발견", fields: ["detected_at", "detected_by"] },
  { id: "s4", no: "04", name: "사건 내용", fields: ["description", "immediate_actions"] },
  { id: "s5", no: "05", name: "관련 공정 변수 / 측정값", fields: [] },
  { id: "s6", no: "06", name: "위험 확인 질문", fields: [] },
  { id: "s7", no: "07", name: "반복성 조회", fields: [] },
  { id: "s8", no: "08", name: "기준일", fields: ["today"] },
];

/* ---------- small helpers ---------- */
export function todayISO(now = new Date()) {
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
export function isISODate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s))) return false;
  const d = new Date(s + "T00:00:00Z");
  return !isNaN(d) && d.toISOString().slice(0, 10) === s;
}
export const WHEN = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$/;
export function levelLabel(id) { const l = RULES.levels.find(x => x.id === id); return l ? l.label : id; }
export function blankForm(today) {
  const f = { synthetic: false, flags: {}, parameters: [], today: today || todayISO() };
  TEXT_FIELDS.forEach(k => { f[k] = ""; });
  RULES.required_flags.forEach(k => { f.flags[k] = null; });
  return f;
}
// JSON with keys sorted at every depth, so the same input always gives the same hash.
export function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") return "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  return JSON.stringify(value === undefined ? null : value);
}
export async function sha256(text) {
  const buf = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}

/* ---------- history CSV ---------- */
export function parseCSV(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter(r => r.some(x => x.trim() !== ""));
}
// A history problem: what is wrong, and what to do next (one line each).
export class HistoryError extends Error {
  constructor(cause, next) { super(cause); this.name = "HistoryError"; this.next = next; }
}
export async function parseHistory(name, text, warning) {
  text = text.replace(/^\uFEFF/, "");
  const rows = parseCSV(text);
  if (!rows.length) throw new HistoryError("빈 파일", "QMS에서 이력을 다시 내보내기");
  const head = rows[0].map(h => h.trim());
  const need = ["dev_id", "opened", "site", "equipment_id", "category", "final_class"];
  const missing = need.filter(c => !head.includes(c));
  if (missing.length) throw new HistoryError("필수 열 없음: " + missing.join(", "), "첫 줄의 열 이름 확인 후 다시 선택");
  const recs = rows.slice(1).map(r => Object.fromEntries(head.map((h, i) => [h, (r[i] || "").trim()])));
  const errors = []; const seen = new Set();
  recs.forEach((r, i) => {
    if (!r.dev_id) errors.push((i + 2) + "행 dev_id 비어 있음");
    else if (seen.has(r.dev_id)) errors.push((i + 2) + "행 dev_id 중복 (" + r.dev_id + ")"); else seen.add(r.dev_id);
    if (!isISODate(r.opened)) errors.push((i + 2) + "행 opened가 YYYY-MM-DD 아님 (" + r.opened + ")");
  });
  if (errors.length) throw new HistoryError("이력 오류 " + errors.length + "건: " + errors.slice(0, 5).join(" / ") + (errors.length > 5 ? " …" : ""), "해당 행 수정 후 다시 선택");
  return { name, rows: recs, sha: await sha256(text), synthetic: recs.some(r => /^true$/i.test(r.synthetic || "")), warning: warning || "", text };
}
// Which history a form may use: the user's file, or (synthetic forms only) the bundled synthetic one.
export function pickHistory(form, userHistory, sampleHistory) {
  if (userHistory) return userHistory;
  return form.synthetic ? (sampleHistory || null) : null;
}

/* ---------- YAML intake forms (the CLI's file format) ---------- */
export class YamlError extends Error {
  constructor(message, line) { super(message); this.name = "YamlError"; this.line = line; }
}
// Reads an intake form the way the CLI's FormLoader does: text stays as typed, only true/false and empty values
// have a meaning. It covers the block style the template uses (key: value, quotes, "|" blocks, wrapped lines,
// "- name:" lists). Anything else (anchors, tags, {…}, nested maps, ">" blocks) is refused, never guessed.
export function parseFormYAML(text) {
  const lines = String(text).replace(/^﻿/, "").replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  const fail = (msg, at) => { throw new YamlError(msg, (at === undefined ? i : at) + 1); };
  const blank = s => /^[ \t]*$/.test(s);
  const comment = s => /^[ \t]*#/.test(s);
  const indentOf = (s, at) => { const m = s.match(/^[ ]*/)[0].length; if (s[m] === "\t") fail("탭 들여쓰기는 지원 안 함", at); return m; };
  const skip = () => { while (i < lines.length && (blank(lines[i]) || comment(lines[i]))) i++; };
  const KEY = /^([A-Za-z_][A-Za-z0-9_]*)[ ]*:(?:[ \t]+(.*))?$/;
  const resolve = s => {
    if (/^(true|True|TRUE)$/.test(s)) return true;
    if (/^(false|False|FALSE)$/.test(s)) return false;
    if (/^(~|null|Null|NULL|)$/.test(s)) return null;
    if (s === "=" || s === "<<") fail("'" + s + "' 값은 지원 안 함", i - 1);
    return s;
  };
  // Lines that continue a wrapped scalar: joined with one space; an empty line between them is a line break.
  function fold(first, parts) {
    let out = first, gap = 0;
    parts.forEach(p => { if (p === null) { gap++; return; } out += gap ? "\n".repeat(gap) : (out === "" ? "" : " "); out += p; gap = 0; });
    return out;
  }
  // A quoted value may run over several lines: a line break is one space, an empty line is a line break.
  function quoted(rest, q) {
    let at = i - 1, out = "", gap = 0, glue = true, line = rest.slice(1);
    for (;;) {
      let k = 0, piece = "", closed = false, cont = false;
      while (k < line.length) {
        const c = line[k];
        if (q === "'" && c === "'") { if (line[k + 1] === "'") { piece += "'"; k += 2; continue; } closed = true; k++; break; }
        if (q === '"' && c === '"') { closed = true; k++; break; }
        if (q === '"' && c === "\\") {
          const e = line[k + 1];
          if (e === undefined) { cont = true; k++; break; }
          const simple = { n: "\n", t: "\t", r: "\r", "0": "\0", '"': '"', "\\": "\\", "/": "/", " ": " ", a: "\x07", b: "\b", e: "\x1b", f: "\f", v: "\v", N: "\x85", _: "\xa0", L: "\u2028", P: "\u2029" };
          if (e in simple) { piece += simple[e]; k += 2; continue; }
          const len = { x: 2, u: 4, U: 8 }[e];
          const hex = len ? line.slice(k + 2, k + 2 + len) : "";
          if (!len || hex.length !== len || !/^[0-9A-Fa-f]+$/.test(hex)) fail("알 수 없는 \\ 표기", at);
          piece += String.fromCodePoint(parseInt(hex, 16)); k += 2 + len; continue;
        }
        piece += c; k++;
      }
      out += glue ? "" : gap ? "\n".repeat(gap) : " ";
      out += closed || cont ? piece : piece.replace(/[ \t]+$/, "");
      gap = 0; glue = cont;
      if (closed) { if (!/^([ \t]+#.*|[ \t]*)$/.test(line.slice(k))) fail("따옴표 뒤에 글자가 있음", at); return out; }
      for (;;) {
        if (i >= lines.length) fail("따옴표가 닫히지 않음", at);
        at = i; const raw = lines[i++];
        if (blank(raw)) { gap++; continue; }
        line = raw.replace(/^[ \t]+/, ""); break;
      }
    }
  }
  function block(header, parentIndent) {
    const m = header.match(/^\|([+-]?)[ \t]*(#.*)?$/);
    if (!m) fail(header[0] === ">" ? "'>' 블록은 지원 안 함 · '|' 사용" : "'|' 뒤 표기는 지원 안 함", i - 1);
    const got = [];
    while (i < lines.length && (blank(lines[i]) || indentOf(lines[i]) > parentIndent)) got.push(lines[i++]);
    const firstText = got.find(l => !blank(l));
    if (firstText === undefined) return m[1] === "+" ? "\n".repeat(got.length) : "";
    const ind = indentOf(firstText);
    const body = got.map((l, n) => { if (blank(l)) return ""; if (indentOf(l) < ind) fail("블록 안 들여쓰기가 맞지 않음", i - got.length + n); return l.slice(ind); });
    let tail = 0; while (body.length && body[body.length - 1] === "") { body.pop(); tail++; }
    return body.join("\n") + (m[1] === "-" ? "" : m[1] === "+" ? "\n".repeat(tail + 1) : "\n");
  }
  function plain(rest, parentIndent) {
    const cut = s => { const c = s.search(/[ \t]#/); return (c < 0 ? s : s.slice(0, c)).trim(); };
    const check = (s, at) => { if (/:[ \t]/.test(s) || /:$/.test(s)) fail("값 안에 ': ' 가 있음 · 따옴표로 감싸기", at); };
    const first = cut(rest); check(first, i - 1);
    const parts = []; let j = i, pending = 0, ended = /[ \t]#/.test(rest);
    while (!ended && j < lines.length) {
      const l = lines[j];
      if (blank(l)) { pending++; j++; continue; }
      if (comment(l) || indentOf(l, j) <= parentIndent) break;
      for (; pending; pending--) parts.push(null);
      const t = cut(l); check(t, j); parts.push(t); j++; i = j;
      if (/[ \t]#/.test(l)) ended = true;
    }
    return resolve(fold(first, parts));
  }
  function value(rest, parentIndent, allowList) {
    rest = (rest || "").replace(/[ \t]+$/, "");
    if (rest === "" || rest[0] === "#") {
      let j = i; while (j < lines.length && (blank(lines[j]) || comment(lines[j]))) j++;
      if (j >= lines.length) return null;
      const ind = indentOf(lines[j], j), body = lines[j].slice(ind);
      if (/^-([ \t]|$)/.test(body) && ind >= Math.max(parentIndent, 0)) { if (!allowList) fail("이 자리에는 목록을 둘 수 없음", j); i = j; return list(ind); }
      if (ind <= parentIndent) return null;
      if (KEY.test(body)) fail("중첩된 '항목: 값'은 지원 안 함", j);
      i = j + 1; return scalar(body, parentIndent);
    }
    return scalar(rest, parentIndent);
  }
  function scalar(rest, parentIndent) {
    const c = rest[0];
    if (c === "'" || c === '"') return quoted(rest, c);
    if (c === "|" || c === ">") return block(rest, parentIndent);
    if (/^\[[ \t]*\][ \t]*(#.*)?$/.test(rest)) return [];
    if ("[]{},".includes(c)) fail("[ ] { } 한 줄 묶음은 지원 안 함", i - 1);
    if ("&*!%@`".includes(c)) fail("'" + c + "' 로 시작하는 값은 지원 안 함 · 따옴표로 감싸기", i - 1);
    if (/^[-?:]([ \t]|$)/.test(rest)) fail("'" + c + " ' 로 시작하는 값은 따옴표로 감싸기", i - 1);
    return plain(rest, parentIndent);
  }
  function list(ind) {
    const items = [];
    for (;;) {
      skip();
      if (i >= lines.length) break;
      const l = lines[i], here = indentOf(l);
      if (here !== ind || !/^-([ \t]|$)/.test(l.slice(here))) { if (here > ind) fail("목록 들여쓰기가 맞지 않음"); break; }
      const after = l.slice(here + 1), pad = after.match(/^[ \t]*/)[0].length, itemIndent = here + 1 + pad;
      let m = after.slice(pad).match(KEY);
      if (!m) fail("목록 항목은 '- name: 값' 형태만 지원");
      const item = {};
      i++;
      for (;;) {
        if (m[1] in item) fail("같은 항목이 두 번: " + m[1], i - 1);
        item[m[1]] = value(m[2], itemIndent, false);
        skip();
        if (i >= lines.length || indentOf(lines[i]) !== itemIndent) break;
        m = lines[i].slice(itemIndent).match(KEY);
        if (!m) fail("'항목: 값' 형태가 아님");
        i++;
      }
      if (i < lines.length && !blank(lines[i]) && indentOf(lines[i]) > ind) fail("목록 들여쓰기가 맞지 않음");
      items.push(item);
    }
    return items;
  }
  const out = {};
  let started = false;
  for (;;) {
    skip();
    if (i >= lines.length) break;
    const l = lines[i];
    if (/^---[ \t]*(#.*)?$/.test(l) && !started) { started = true; i++; continue; }
    if (/^(---|\.\.\.)/.test(l)) fail("문서 구분선(---)이 여러 번 나오는 파일은 지원 안 함");
    if (indentOf(l) !== 0) fail("들여쓰기가 맞지 않음");
    const m = l.match(KEY);
    if (!m) fail("'항목: 값' 형태가 아님");
    if (m[1] in out) fail("같은 항목이 두 번: " + m[1]);
    started = true; i++;
    out[m[1]] = value(m[2], 0, true);
  }
  return out;
}
export const FORM_KEYS = ["synthetic", "id", "title", "site", "area", "product", "batch", "equipment_id", "category", "detected_at", "detected_by",
  "process_step", "description", "immediate_actions", "parameters"].concat(RULES.required_flags);
// A draft form as a CLI intake file: the keys the CLI reads, in the order of its template (the draft date is not part of a form;
// the CLI takes it as --today). Every text is written double-quoted, the one YAML form that carries any character exactly,
// so the CLI's loader and this page's own reader get back what the page shows. An unanswered question stays empty.
export function toFormYAML(f) {
  // JSON string syntax is YAML double-quoted syntax; the characters YAML does not allow raw (or would fold as a line break) are escaped too.
  const q = v => JSON.stringify(String(v == null ? "" : v)).replace(/[\u007f-\u009f\u2028\u2029\ufeff\ufffe\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
  const lines = ["# Deviation 초안 데스크에서 내보낸 입력 양식 (devdraft CLI 양식과 같은 항목)"];
  if (f.synthetic) lines.push("synthetic: true");
  TEXT_FIELDS.forEach(k => lines.push(k + ": " + q(f[k])));
  if (!f.parameters.length) lines.push("parameters: []");
  else {
    lines.push("parameters:");
    f.parameters.forEach(p => ["name", "spec", "actual", "duration"].forEach((k, n) => lines.push((n ? "  " : "- ") + k + ": " + q(p[k]))));
  }
  RULES.required_flags.forEach(k => lines.push(k + ":" + (f.flags[k] === true ? " true" : f.flags[k] === false ? " false" : "")));
  return lines.join("\n") + "\n";
}
// The viewer saves .txt but not .yaml: the file is named <number>.yaml.txt, and both this page and the CLI read it as it is.
export function formFileName(id) { return (String(id || "").trim() || "deviation").replace(/[^\w.\-가-힣]+/g, "_") + ".yaml.txt"; }
// Template guidance that ended up inside a value (a "#" glued to the text, or a "# …" line inside a "|" block). Same test as the CLI.
export function gluedTemplateComments(raw, template) {
  return Object.keys(raw).filter(k => typeof raw[k] === "string" &&
    ((template.own[k] && raw[k].includes(template.own[k].slice(0, 8))) || template.phrases.some(p => raw[k].includes(p)))).sort();
}
// A parsed YAML form as a draft form. errors: the file is not taken (the CLI refuses it too). notes: taken, with something to look at.
export function formFromRaw(raw, today, template) {
  const errors = [], notes = [];
  const unknown = Object.keys(raw).filter(k => !FORM_KEYS.includes(k)).sort();
  if (unknown.length) errors.push("알 수 없는 항목: " + unknown.join(", "));
  const glued = gluedTemplateComments(raw, template);
  if (glued.length) errors.push("값에 양식 주석이 붙어 있음: " + glued.join(", "));
  if (raw.parameters != null && (!Array.isArray(raw.parameters) || raw.parameters.some(p => !p || typeof p !== "object"))) errors.push("parameters는 '- name: …' 목록이어야 함");
  const lists = TEXT_FIELDS.filter(k => Array.isArray(raw[k]));
  if (lists.length) errors.push("글자 칸에 목록이 있음: " + lists.join(", "));
  if (errors.length) return { form: null, errors, notes };
  const f = blankForm(today);
  f.synthetic = raw.synthetic === true;
  if (raw.synthetic != null && typeof raw.synthetic !== "boolean") notes.push("synthetic: '" + raw.synthetic + "' → 연습용 표시 안 함 (true/false만 인정)");
  TEXT_FIELDS.forEach(k => { f[k] = raw[k] == null ? "" : String(raw[k]); });
  f.detected_at = f.detected_at.trim().replace(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/, "$1T$2");
  RULES.required_flags.forEach(k => {
    const v = raw[k];
    if (v === true || v === false) f.flags[k] = v;
    else if (v != null) notes.push(FLAG_NAME[k] + ": '" + v + "' → 미응답으로 가져옴 (true/false만 인정)");
  });
  f.parameters = (raw.parameters || []).map(p => Object.fromEntries(["name", "spec", "actual", "duration"].map(k => [k, p[k] == null ? "" : String(p[k])])));
  return { form: f, errors, notes };
}

/* ---------- validation (same rules as the CLI) ---------- */
export function missingRequired(f) {
  return {
    fields: RULES.required_fields.filter(k => !String(f[k] || "").trim()),
    flags: RULES.required_flags.filter(k => f.flags[k] !== true && f.flags[k] !== false),
  };
}
export function validate(f, history) {
  const errs = [];
  const m = missingRequired(f);
  if (m.fields.length) errs.push({ code: "missing", text: "필수 항목 누락: " + m.fields.map(k => FIELD_LABEL[k] || k).join(", "), targets: m.fields });
  if (m.flags.length) errs.push({ code: "unanswered", text: "예/아니오 미응답: " + m.flags.map(k => FLAG_NAME[k]).join(", "), targets: m.flags.map(k => "flag-" + k) });
  if (f.detected_at && !WHEN.test(f.detected_at)) errs.push({ code: "when", text: "발견 일시 형식 오류 (예: 2026-11-21 14:20)", targets: ["detected_at"] });
  if (!isISODate(f.today)) errs.push({ code: "today", text: "초안 생성일 형식 오류", targets: ["today"] });
  else if (f.detected_at && WHEN.test(f.detected_at) && f.detected_at.slice(0, 10) > f.today) {
    errs.push({ code: "future", text: "발견 일시가 초안 생성일보다 미래임: " + f.detected_at.replace("T", " ") + " > " + f.today, targets: ["detected_at", "today"] });
  }
  if (f.category && !RULES.categories.includes(f.category)) errs.push({ code: "category", text: "유형이 목록에 없음: " + f.category, targets: ["category"] });
  const oneLine = ONE_LINE.filter(k => /[\r\n]/.test(f[k] || ""));
  if (oneLine.length) errs.push({ code: "newline", text: "한 줄 항목에 줄바꿈: " + oneLine.map(k => FIELD_LABEL[k] || k).join(", "), targets: oneLine });
  if (historyBlocked(f, history)) errs.push({ code: "synthetic-history", text: "실제 양식에 합성 이력 사용 불가 · 실제 이력 CSV 필요", targets: ["step-s7"] });
  return errs;
}

/* ---------- classification (proposal only) ---------- */
export function unmatchedKeys(f) { return RULES.recurrence.match_on.filter(k => !String(f[k] || "").trim()); }
// A real form with a synthetic history: the CLI refuses the pair so that no made-up past case lands on a real document.
// Here the form is refused too (validate), and no lookup is done, so no made-up match is shown on the way.
export function historyBlocked(f, history) { return !f.synthetic && !!history && !!history.synthetic; }
// What stops a draft: how many places, and whether they are all just unfilled (otherwise something has to be corrected).
export function blockCount(errs) {
  return { n: errs.reduce((k, e) => k + e.targets.length, 0), missingOnly: errs.every(e => e.code === "missing" || e.code === "unanswered") };
}
export function hasRecTrigger() { return Object.values(RULES.classes).some(ts => ts.some(t => t.field === "recurrence_count")); }
export function findRecurrence(f, history) {
  if (!history) return [];
  const cut = new Date(f.today + "T00:00:00Z"); cut.setUTCDate(cut.getUTCDate() - RULES.recurrence.window_days);
  const cutoff = cut.toISOString().slice(0, 10);
  return history.rows.filter(r => r.opened >= cutoff && r.opened <= f.today && r.dev_id !== f.id.trim() &&
    RULES.recurrence.match_on.every(k => (r[k] || "").trim() && r[k].trim() === String(f[k] || "").trim()))
    .sort((a, b) => a.opened < b.opened ? 1 : -1);
}
export function matchedTriggers(f, n) {
  const hits = [];
  RULES.levels.forEach(l => (RULES.classes[l.id] || []).forEach(t => {
    if ("equals" in t && f.flags[t.field] === t.equals) hits.push([l.id, t.reason]);
    else if ("min" in t && t.field === "recurrence_count" && n >= t.min) hits.push([l.id, t.reason + " — 유사 건 " + n + "건"]);
  }));
  return hits;
}
export function classify(f, rec, recChecked, history) {
  const hits = matchedTriggers(f, rec.length);
  let level = RULES.default_level, reasons = [RULES.default_reason];
  if (hits.length) { level = hits[0][0]; reasons = hits.filter(h => h[0] === level).map(h => h[1]); }
  const lower = hits.filter(h => h[0] !== level);
  let note = "";
  if (!recChecked && hasRecTrigger()) {
    const why = !history ? "이력 파일 없음" : historyBlocked(f, history) ? "합성 이력" : unmatchedKeys(f).map(k => MATCH_LABEL[k]).join("·") + " 미기재";
    const n = "반복성 조회를 하지 않음(" + why + ") — 반복 기준은 평가되지 않았습니다. 검토자가 QMS에서 직접 확인 필요";
    reasons = level === RULES.default_level ? [n, "그 밖의 분류 기준에는 해당 없음 (보고자 입력 기준) — 검토자 확인 필요"] : reasons.concat([n]);
    note = " (반복 기준 미평가 — 반복성 조회를 하지 않음)";
  }
  const used = new Set(Object.values(RULES.classes).flat().filter(t => "equals" in t).map(t => t.field));
  const unused = RULES.required_flags.filter(k => f.flags[k] === true && !used.has(k) && k !== "regulatory_report_required");
  return { level, reasons, lower, note, unused };
}
// The recurrence lookup for one form: done or not, and why not.
export function lookup(f, history) {
  const keys = unmatchedKeys(f);
  const blocked = historyBlocked(f, history);
  const checked = !!history && !blocked && keys.length === 0 && isISODate(f.today);
  const why = checked ? "" : !history ? "이력 파일 없음" : blocked ? "합성 이력" : keys.length ? keys.map(k => MATCH_LABEL[k]).join("·") + " 미기재" : "초안 생성일 형식 오류";
  return { checked, rec: checked ? findRecurrence(f, history) : [], why };
}
// The tool's proposal, or null while any risk question is unanswered (an empty answer is never read as "no").
export function proposal(f, history) {
  if (missingRequired(f).flags.length) return null;
  const look = lookup(f, history);
  return Object.assign(classify(f, look.rec, look.checked, history), { checked: look.checked, rec: look.rec, why: look.why });
}
export function plan(f) {
  const focus = FOCUS[f.category] || [];
  return RULES.ishikawa.slice().sort((a, b) => (focus.indexOf(a[0]) < 0 ? 99 : focus.indexOf(a[0])) - (focus.indexOf(b[0]) < 0 ? 99 : focus.indexOf(b[0])));
}

/* ---------- the draft as a neutral model: rendered to screen, Markdown and Word ---------- */
// A run: {t: text, user: entered value?, b: bold?, blank: ☐ placeholder?, box: ☐ for the reviewer to tick?}
const U = t => ({ t: String(t), user: true });
const T = t => ({ t });
const B = t => ({ t, b: true });
const BL = () => ({ t: TBD, blank: true, b: true });
const BOX = () => ({ t: "☐", box: true, b: true });
export async function buildModel(f, history) {
  const recChecked = !!history && unmatchedKeys(f).length === 0;
  const rec = recChecked ? findRecurrence(f, history) : [];
  const c = classify(f, rec, recChecked, history);
  const window = "최근 " + RULES.recurrence.window_days + "일";
  const match = RULES.recurrence.match_on.map(k => MATCH_LABEL[k]).join("·");
  const formSha = await sha256(canonical(f));
  const B_ = [];
  B_.push({ k: "h1", runs: [T("Deviation 보고서 초안 — "), U(f.id)] });
  const banner = [[B("초안입니다 — 승인 문서가 아닙니다.")],
    [T("이 문서는 입력된 내용을 보고서 형식으로 재배열한 것입니다. 조사 결과·근본원인·영향평가 결론은 담당자가 직접 작성해야 하며, 분류는 제안일 뿐 QA 검토자의 확인이 필요합니다.")],
    [T("전자서명·승인 기능은 포함하지 않습니다 (해당 기능은 검증된 QMS에서 수행).")]];
  if (f.synthetic) banner.unshift([B("합성(가짜) 데이터로 만든 초안 — 실제 deviation 문서로 사용 금지")]);
  B_.push({ k: "banner", lines: banner });
  B_.push({ k: "table", head: ["항목", "내용"], rows: [
    [[T("Deviation 번호")], [U(f.id)]], [[T("제목")], [U(f.title)]],
    [[T("사업장 / 구역")], [U(f.site), T(" / "), U(f.area)]], [[T("제품 / 배치")], [U(f.product), T(" / "), U(f.batch)]],
    [[T("설비")], [f.equipment_id.trim() ? U(f.equipment_id) : T("해당 없음")]], [[T("공정 단계")], [U(f.process_step)]],
    [[T("발견 일시")], [U(f.detected_at.replace("T", " "))]], [[T("발견자")], [U(f.detected_by)]],
    [[T("유형")], [f.category ? U(f.category) : BL()]], [[T("초안 생성일")], [U(f.today)]]] });
  B_.push({ k: "h2", runs: [T("1. 사건 경위")] });
  B_.push({ k: "pre", runs: [U(f.description)] });
  B_.push({ k: "h3", runs: [T("관련 공정 변수")] });
  if (f.parameters.length) B_.push({ k: "table", head: ["항목", "기준", "실측", "비고"], rows: f.parameters.map(p => [[U(p.name)], [U(p.spec)], [U(p.actual)], [U(p.duration || "")]]) });
  else B_.push({ k: "p", runs: [T("해당 없음")] });
  B_.push({ k: "h2", runs: [T("2. 즉시 조치")] });
  B_.push({ k: "pre", runs: [U(f.immediate_actions)] });
  B_.push({ k: "h2", runs: [T("3. 분류 (제안)")] });
  B_.push({ k: "p", grade: true, runs: [B("제안 등급: " + levelLabel(c.level)), T(c.note)] });
  B_.push({ k: "p", runs: [T("근거:")] });
  B_.push({ k: "ul", items: c.reasons.map(r => [T(r)]) });
  if (c.lower.length) { B_.push({ k: "p", runs: [T("그 밖에 해당한 트리거 (하위 등급):")] }); B_.push({ k: "ul", items: c.lower.map(h => [T("[" + levelLabel(h[0]) + "] " + h[1])]) }); }
  if (c.unused.length) {
    B_.push({ k: "p", runs: [B("보고자가 \"예\"로 답했지만 이 규칙의 분류 기준이 아닌 항목: " + c.unused.map(k => FLAG_NAME[k]).join(", ")), T(" — 제안 등급에 반영되지 않았습니다. 도구는 기준을 만들지 않습니다.")] });
    B_.push({ k: "ul", items: [[BL(), T(" SOP에 따라 이 답변이 등급에 영향을 주는지 확인")]] });
  }
  B_.push({ k: "p", runs: [T("분류 기준 출처: "), ...(RULES.sop_reference ? [T(RULES.sop_reference)] : [BL(), T(" — 분류 기준 출처 미기재. 사내 SOP와 대조 필요.")])] });
  if (RULES.manual_checks.length) {
    B_.push({ k: "p", runs: [B("도구가 판단하지 않은 SOP 기준 — 검토자가 직접 확인"), T(" (해당하면 위 제안 등급과 다를 수 있음):")] });
    B_.push({ k: "ul", items: RULES.manual_checks.map(m => [BOX(), T(" SOP " + m.clause + ": " + m.text)]) });
  }
  B_.push({ k: "table", head: ["확인 항목", "보고자 입력"], rows: DRAFT_FLAG_ORDER.map(k => [[T(FLAG_NAME[k])], [T(f.flags[k] ? "예" : "아니오")]]) });
  if (f.flags.regulatory_report_required) {
    B_.push({ k: "p", runs: [B("보고자 입력: 규제기관 신고 대상 가능성 \"예\""), T(" — 도구는 신고 여부를 판단하지 않습니다.")] });
    B_.push({ k: "ul", items: [[BL(), T(" 신고 필요 여부·기한·신고처 확인 (사내 절차)")]] });
  }
  B_.push({ k: "p", runs: [B("QA 검토자 확정 등급: "), BL()] });
  B_.push({ k: "p", runs: [B("제안과 다를 경우 사유: "), BL()] });
  B_.push({ k: "h2", runs: [T("4. 반복성 검토")] });
  if (!recChecked) {
    const why = history ? unmatchedKeys(f).map(k => MATCH_LABEL[k]).join("·") + " 값이 비어 있어 같은 건을 찾을 수 없습니다" : "이력 파일을 고르지 않았습니다";
    B_.push({ k: "p", runs: [B("반복성 조회를 하지 않았습니다"), T(" — " + why + " (\"반복 없음\"이 아닙니다).")] });
    B_.push({ k: "ul", items: [[BL(), T(" QMS에서 반복 여부 직접 확인 (" + window + ", 동일 " + match + " 기준)")]] });
  } else if (rec.length) {
    B_.push({ k: "p", runs: [T(window + " 내 동일 " + match + " 건 " + rec.length + "건 (목록만 표시, 원인 연관성은 판단하지 않음):")] });
    B_.push({ k: "table", head: ["번호", "개설일", "등급"], rows: rec.map(r => [[U(r.dev_id)], [U(r.opened)], [U(r.final_class)]]) });
  } else B_.push({ k: "p", runs: [T(window + " 내 동일 " + match + " 건 없음.")] });
  if (history && history.rows.some(r => r.dev_id === f.id.trim())) B_.push({ k: "p", runs: [T("※ 이력 파일에 이번 deviation("), U(f.id), T(") 자체가 있어 반복 건에서 제외했습니다.")] });
  B_.push({ k: "h2", runs: [T("5. 조사 계획 (6M)")] });
  B_.push({ k: "table", head: ["구분", "확인할 것", "조사 결과"], rows: plan(f).map(([k, v]) => [[T(k)], [T(v)], [BL()]]) });
  B_.push({ k: "h2", runs: [T("6. 근본원인")] });
  B_.push({ k: "p", runs: [BL(), T(" — 조사 완료 후 작성. 조사 결과로 뒷받침되지 않는 추정은 기재하지 않습니다.")] });
  B_.push({ k: "h2", runs: [T("7. 제품 품질 영향 평가")] });
  B_.push({ k: "p", runs: [BL(), T(" — 해당 배치 및 영향 가능 배치에 대한 평가. 결론(출하 가능 / 보류 / 폐기)과 근거 기재.")] });
  B_.push({ k: "h2", runs: [T("8. CAPA")] });
  B_.push({ k: "table", head: ["구분", "내용", "담당", "기한"], rows: [["시정조치(Correction)"], ["재발방지(Corrective)"], ["예방조치(Preventive)"]].map(([n]) => [[T(n)], [BL()], [T("")], [T("")]]) });
  B_.push({ k: "h2", runs: [T("9. 검토 및 승인")] });
  B_.push({ k: "p", runs: [T("검증된 QMS에서 수행합니다. 이 초안에는 서명란을 두지 않습니다.")] });
  B_.push({ k: "h2", runs: [T("부록. 생성 근거")] });
  B_.push({ k: "p", runs: [T("같은 입력·규칙·이력이면 같은 초안이 나옵니다. SHA-256 값으로 입력이 바뀌지 않았는지 확인할 수 있습니다.")] });
  B_.push({ k: "table", head: ["항목", "값"], rows: [
    [[T("입력 양식")], [T("화면 입력 (SHA-256 " + formSha + ")")]],
    [[T("분류 규칙")], [T(RULES_FILE.name + " (SHA-256 " + RULES_FILE.sha256 + ")")]],
    [[T("분류 기준 SOP")], [T(RULES.sop_reference || "미기재")]],
    [[T("반복성 조회 이력")], [history ? U(history.name + " (SHA-256 " + history.sha + ", " + history.rows.length + "행" + (history.synthetic ? ", 합성 데이터" : "") + ")") : T("사용 안 함")]],
    [[T("기준일")], [U(f.today)]], [[T("생성 도구")], [T(VERSION)]]] });
  const blanks = B_.reduce((n, b) => n + canonical(b).split('"blank":true').length - 1, 0);
  return { blocks: B_, id: f.id, today: f.today, synthetic: f.synthetic, level: c.level, note: c.note, recChecked, recCount: rec.length, blanks, boxes: RULES.manual_checks.length, formSha };
}

// Markdown: entered values are escaped so they show exactly as entered (same rules as devdraft.mdtext).
export function mdInline(s) {
  s = String(s == null ? "" : s);
  s = s.replace(/([\\`*|\[\]~])/g, "\\$1");
  s = s.replace(/(^|[^0-9A-Za-z가-힣])_|_(?=[^0-9A-Za-z가-힣]|$)/g, (m, p) => (p === undefined ? "\\_" : p + "\\_"));
  s = s.replace(/<(?=[A-Za-z/!?])/g, "\\<").replace(/&(?=#?[0-9A-Za-z]+;)/g, "\\&");
  s = s.replace(/^(\s*)([#>+=-])/, "$1\\$2").replace(/^(\s*\d{1,9})([.)])(?=\s|$)/, "$1\\$2");
  return s;
}
function mdRuns(runs, multi) {
  return runs.map(r => {
    let t = r.user ? (multi ? r.t.split(/\r?\n/).map(l => mdInline(l.replace(/\s+$/, ""))).join("  \n") : mdInline(r.t.replace(/[\r\n]+/g, " "))) : r.t;
    // The markers hug the words: "**label:** " and not "**label: **", which Markdown shows as literal asterisks.
    if (r.blank) t = "☐ **작성 필요**"; else if (r.box) t = "☐"; else if (r.b && t.trim()) t = t.replace(/^(\s*)([\s\S]*?)(\s*)$/, "$1**$2**$3");
    return t;
  }).join("");
}
export function toMarkdown(m) {
  const out = [];
  m.blocks.forEach(b => {
    if (b.k === "h1") out.push("# " + mdRuns(b.runs));
    else if (b.k === "h2") out.push("## " + mdRuns(b.runs));
    else if (b.k === "h3") out.push("### " + mdRuns(b.runs));
    else if (b.k === "p") out.push(mdRuns(b.runs));
    else if (b.k === "pre") out.push(mdRuns(b.runs, true));
    else if (b.k === "ul") out.push(b.items.map(i => "- " + mdRuns(i)).join("\n"));
    else if (b.k === "banner") out.push(b.lines.map(l => "> " + mdRuns(l)).join("  \n"));
    else if (b.k === "table") out.push(["| " + b.head.join(" | ") + " |", "|" + b.head.map(() => "---|").join("")]
      .concat(b.rows.map(r => "| " + r.map(c => mdRuns(c)).join(" | ") + " |")).join("\n"));
  });
  return out.join("\n\n") + "\n\n---\n*이 초안은 화면 입력으로부터 자동 생성되었습니다. 생성 도구는 사실을 재배열할 뿐, 조사 결과나 결론을 생성하지 않습니다.*\n";
}
// Word document object from the model. D is the docx library (window.docx in the page).
// Width of the text area in twips: A4 (11906) minus the library's default 1-inch margins (1440 each). A test reads both back from the file.
export const DOCX_TEXT_WIDTH = 11906 - 2 * 1440;
export function buildDocx(m, D) {
  if (!D) throw new Error("Word 변환 모듈 없음");
  const runs = (rs) => rs.flatMap(r => {
    const lines = r.t.split(/\r?\n/);
    // bold only where it is wanted: an explicit "not bold" on a run would switch off the bold of a heading style.
    return lines.map((line, i) => new D.TextRun(Object.assign({ text: line, break: i > 0 ? 1 : 0 }, r.b || r.blank ? { bold: true } : {},
      r.blank || r.box ? { highlight: "yellow" } : {})));
  });
  const para = (rs, opts) => new D.Paragraph(Object.assign({ children: runs(rs) }, opts || {}));
  // Every table and cell gets its width in twips. Left out, the library writes 100 twips (under 2 mm) per column,
  // and a viewer that draws the table as written (seen in macOS Quick Look) shows one letter per line.
  const full = { size: DOCX_TEXT_WIDTH, type: D.WidthType.DXA };
  const pad = { top: 40, bottom: 40, left: 100, right: 100 };   // space inside every cell, in twips; without it Word sets the text against the lines
  const split = n => Array(n).fill(Math.floor(DOCX_TEXT_WIDTH / n));
  const kids = [];
  m.blocks.forEach(b => {
    if (b.k === "h1") kids.push(para(b.runs, { heading: D.HeadingLevel.HEADING_1 }));
    else if (b.k === "h2") kids.push(para(b.runs, { heading: D.HeadingLevel.HEADING_2, spacing: { before: 240 } }));
    else if (b.k === "h3") kids.push(para(b.runs, { heading: D.HeadingLevel.HEADING_3 }));
    // The proposed grade, and any line that leads into a list or table, stays on the page of what follows (as in the CLI's file):
    // a page must not end with the proposal and leave its reasons to the next one.
    else if (b.k === "p" || b.k === "pre") kids.push(para(b.runs, b.grade || /:\s*$/.test(b.runs.map(r => r.t).join("")) ? { keepNext: true } : undefined));
    else if (b.k === "ul") b.items.forEach((i, n) => kids.push(para(i, Object.assign({ bullet: { level: 0 } }, n < b.items.length - 1 ? { keepNext: true } : {}))));   // the items of one list share a page
    else if (b.k === "banner") kids.push(new D.Table({ width: full, columnWidths: [DOCX_TEXT_WIDTH], margins: pad,
      rows: [new D.TableRow({ cantSplit: true, children: [new D.TableCell({ width: full, shading: { fill: "FFF2CC", type: D.ShadingType.CLEAR, color: "auto" },
        children: b.lines.map(l => para(l)) })] })] }), new D.Paragraph(""));
    else if (b.k === "table") {
      const widths = split(b.head.length);
      const cell = (rs, head) => new D.TableCell({ width: { size: widths[0], type: D.WidthType.DXA }, children: [para(head ? [B(rs)] : rs)], shading: head ? { fill: "D9D9D9", type: D.ShadingType.CLEAR, color: "auto" } : undefined });
      kids.push(new D.Table({ width: full, columnWidths: widths, margins: pad, rows:
        // cantSplit: Word moves a whole row to the next page instead of breaking a cell mid-sentence (the CLI's file does the same).
        [new D.TableRow({ tableHeader: true, cantSplit: true, children: b.head.map(h => cell(h, true)) })].concat(b.rows.map(r => new D.TableRow({ cantSplit: true, children: r.map(c => cell(c)) }))) }));
    }
  });
  const band = (m.synthetic ? "합성 데이터 — 실제 문서 아님 · " : "") + "초안 — 승인 문서 아님 · " + m.id + " · 초안 생성일 " + m.today;
  // The look of the CLI's Word file: Arial for Latin letters, Malgun Gothic for Korean, black bold headings (30/24/22 half-points).
  // Left alone, the library gives blue headings and one font name for every script.
  const font = { ascii: "Arial", hAnsi: "Arial", cs: "Arial", eastAsia: "Malgun Gothic" };
  const heading = size => ({ run: { font, size, bold: true, color: "000000" } });
  return new D.Document({
    styles: { default: { document: { run: { font, size: 20 } }, heading1: heading(30), heading2: heading(24), heading3: heading(22) },
      paragraphStyles: [{ id: "Normal", name: "Normal", quickFormat: true, run: { font, size: 20 } }] },   // the heading styles are based on Normal; the library writes no such style unless asked
    sections: [{
      headers: { default: new D.Header({ children: [new D.Paragraph({ children: [new D.TextRun({ text: band, color: "C00000", bold: true, size: 18 })] })] }) },
      footers: { default: new D.Footer({ children: [new D.Paragraph({ alignment: D.AlignmentType.CENTER, children: [
        new D.TextRun({ text: "자동 생성 초안 — 검토·승인은 검증된 QMS에서 · ", size: 16 }), new D.TextRun({ children: [D.PageNumber.CURRENT], size: 16 })] })] }) },
      children: kids }] });
}

/* ---------- workspace calculations (do not touch the judgement above) ---------- */
// Report due date: detection date + dueDays. dueDays is a workspace setting, not an SOP rule.
export function dueDate(f, dueDays) {
  if (!WHEN.test(f.detected_at || "") || !isISODate(f.detected_at.slice(0, 10)) || !Number.isInteger(dueDays) || dueDays < 0) return null;
  const d = new Date(f.detected_at.slice(0, 10) + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + dueDays);
  return d.toISOString().slice(0, 10);
}
// Days left: due - today (negative = overdue).
export function dday(dueISO, today) {
  return Math.round((Date.parse(dueISO + "T00:00:00Z") - Date.parse(today + "T00:00:00Z")) / 86400000);
}
export function ddayLabel(n) { return n === 0 ? "D-DAY" : n > 0 ? "D-" + n : "D+" + (-n); }
export function shortDate(iso) { return iso ? Number(iso.slice(5, 7)) + "/" + Number(iso.slice(8, 10)) : ""; }
export function completeness(f) {
  const m = missingRequired(f);
  const total = RULES.required_fields.length + RULES.required_flags.length;
  return { done: total - m.fields.length - m.flags.length, total, fields: m.fields, flags: m.flags,
    fieldsDone: RULES.required_fields.length - m.fields.length, flagsDone: RULES.required_flags.length - m.flags.length };
}
// How many things each form step still needs (required items missing or invalid).
export function stepIssues(f, history) {
  const errs = validate(f, history);
  const targets = new Set(errs.flatMap(e => e.targets));
  return STEPS.map(s => {
    if (s.id === "s6") return [...targets].filter(t => t.startsWith("flag-")).length;
    if (s.id === "s7") return targets.has("step-s7") ? 1 : 0;
    return s.fields.filter(k => targets.has(k)).length;
  });
}
export function stepOfTarget(target) {
  if (target.startsWith("flag-")) return 5;
  if (target === "step-s7") return 6;
  const i = STEPS.findIndex(s => s.fields.includes(target));
  return i < 0 ? 0 : i;
}
// Everything the lists and cards need to know about one form.
// level: the proposed grade, only for a form the CLI would draft. A form with anything missing has no proposal ("none").
export function inspect(form, history, dueDays, today) {
  const errs = validate(form, history);
  const prop = proposal(form, history);
  const look = lookup(form, history);
  const due = dueDate(form, dueDays);
  return { errs, comp: completeness(form), prop, look, level: prop && !errs.length ? prop.level : "none", due, dd: due ? dday(due, today) : null };
}
// 작성 중: something is missing, or not exported yet. 검토 대기: exported for the reviewer. 완료: marked done by the user.
export function statusOf(draft, errs) {
  if (errs.length) return "drafting";
  if (draft.done) return "done";
  return draft.exported ? "review" : "drafting";
}
export const STATUS_LABEL = { drafting: "작성 중", review: "검토 대기", done: "완료", all: "전체" };
// Start a similar draft: where it happened and who found it are kept; what happened and every risk answer are not.
export const CLONE_KEEPS = ["site", "area", "product", "equipment_id", "category", "process_step", "detected_by"];
export function cloneForNew(f, today) {
  const n = blankForm(today);
  n.synthetic = !!f.synthetic;
  CLONE_KEEPS.forEach(k => { n[k] = f[k] || ""; });
  return n;
}
// Measurements copied from a spreadsheet range (tab-separated cells): 항목, 기준, 실측, 비고 in that order.
// Text is kept exactly as copied. A first row that is a header is skipped. Returns [] when the text is not a cell range.
export function parseParamPaste(text) {
  if (!/\t/.test(String(text || ""))) return [];
  const rows = String(text).replace(/\r\n?/g, "\n").split("\n").map(l => l.split("\t").map(c => c.trim())).filter(r => r.some(c => c));
  if (rows.length && /^(항목|항목명|parameter|name)$/i.test(rows[0][0])) rows.shift();
  return rows.map(r => ({ name: r[0] || "", spec: r[1] || "", actual: r[2] || "", duration: r.slice(3).filter(c => c).join(" ") }));
}
// What is missing, by name, for lists: up to two names, then a count.
export function missingLabel(f) {
  const m = missingRequired(f), names = m.fields.map(k => FIELD_LABEL[k]).concat(m.flags.map(k => FLAG_NAME[k]));
  return !names.length ? "" : names.length <= 2 ? "빠짐 · " + names.join(", ") : "필수 " + names.length + "개 빠짐";
}
// Is this a draft this version can open? (stored data from another version, or damaged, is left out and reported)
export function isDraftShape(d) {
  const f = d && d.form;
  return !!f && typeof d.uid === "string" && typeof f === "object" && !!f.flags && typeof f.flags === "object" && Array.isArray(f.parameters) &&
    TEXT_FIELDS.every(k => typeof f[k] === "string") && typeof f.today === "string";
}
export const SUGGEST_FIELDS = ["site", "area", "product", "equipment_id", "process_step", "detected_by"];
export function suggestions(forms) {
  const out = {};
  SUGGEST_FIELDS.forEach(k => {
    const count = new Map();
    forms.forEach(f => { const v = String(f[k] || "").trim(); if (v) count.set(v, (count.get(v) || 0) + 1); });
    out[k] = [...count.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(e => e[0]);
  });
  return out;
}
export function agoLabel(thenMs, nowMs) {
  const min = Math.floor((nowMs - thenMs) / 60000);
  if (min < 1) return "방금 저장";
  if (min < 60) return min + "분 전 저장";
  if (min < 1440) return Math.floor(min / 60) + "시간 전 저장";
  return Math.floor(min / 1440) + "일 전 저장";
}

/* ---------- lists: filter and sort ---------- */
// item = {form, status, level, dd, due, look, comp, savedAt}
export function filterItems(items, filter, query) {
  const q = String(query || "").trim().toLowerCase();
  return items.filter(i => {
    const f = i.form;
    if (filter.status && filter.status !== "all" && i.status !== filter.status) return false;
    if (filter.category && (f.category || "none") !== filter.category) return false;
    if (filter.level && i.level !== filter.level) return false;
    if (filter.site && f.site !== filter.site) return false;
    const open = i.status !== "done";
    if (filter.quick === "overdue" && !(open && i.dd !== null && i.dd < 0)) return false;
    if (filter.quick === "today" && !(open && i.dd === 0)) return false;
    if (filter.quick === "week" && !(open && i.dd !== null && i.dd >= 0 && i.dd <= 7)) return false;
    if (filter.quick === "missing" && i.comp.done === i.comp.total) return false;
    if (filter.quick === "recur" && !(i.look.checked && i.look.rec.length > 0)) return false;
    if (q) {
      const hay = [f.id, f.title, f.equipment_id, f.batch, f.product, f.site, f.area].join("\n").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
// Sorting is by dates and numbers only. There is no sort by proposed grade: the tool does not rank deviations.
export function sortItems(items, sort) {
  const by = {
    due: (a, b) => (a.dd === null) - (b.dd === null) || (a.dd ?? 0) - (b.dd ?? 0) || (a.form.id < b.form.id ? -1 : 1),
    saved: (a, b) => b.savedAt - a.savedAt || (a.form.id < b.form.id ? -1 : 1),
    id: (a, b) => (a.form.id || "\uffff") < (b.form.id || "\uffff") ? -1 : 1,
  }[sort] || null;
  return by ? items.slice().sort(by) : items.slice();
}
// The drafts to show first: nearest due date among open drafts; with no due dates at all, most required items missing.
export function heroItems(items, max) {
  const open = items.filter(i => i.status !== "done");
  const dated = open.filter(i => i.dd !== null);
  const list = dated.length ? sortItems(dated, "due") : open.slice().sort((a, b) => (b.comp.total - b.comp.done) - (a.comp.total - a.comp.done));
  return list.slice(0, max);
}

/* ---------- exports that go straight into mail and Excel ---------- */
// A cell that starts like a formula would be run by Excel. Prefix it so it stays text (the cell shows the added ').
export function guardCell(v) {
  const s = String(v == null ? "" : v);
  return /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
}
// Same content as the CLI summary: proposals only. No final grade, no priority, no root cause, no process values.
export function summaryRows(items) {
  return items.map(i => {
    const f = i.form, ok = !i.errs.length && i.prop;
    return [f.id, f.title,
      ok ? levelLabel(i.prop.level) + " (제안" + (i.prop.note ? ", 반복 기준 미평가" : "") + ")" : "",
      ok ? i.prop.reasons.join("; ") : "",
      ok ? (i.look.checked ? String(i.look.rec.length) : "조회 안 함") : "",
      (f.detected_at || "").replace("T", " "), i.due || "",
      i.errs.map(e => e.text).join(" / ")];
  });
}
export function toTSV(head, rows) {
  const cell = v => guardCell(String(v == null ? "" : v).replace(/[\t\r\n]+/g, " "));
  return [head].concat(rows).map(r => r.map(cell).join("\t")).join("\n") + "\n";
}
export function toCSV(head, rows) {
  const cell = v => { const s = guardCell(v); return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  return "\uFEFF" + [head].concat(rows).map(r => r.map(cell).join(",")).join("\r\n") + "\r\n";
}
// A short plain-text note for mail. Facts and the proposal only; the judgement items are listed as still to write.
export function mailSummary(item, dueDays) {
  const f = item.form, p = item.prop;
  if (item.errs.length || !p) throw new Error("필수 항목이 빠진 초안은 요약을 만들지 않음");
  return [
    "[Deviation 초안] " + f.id + " · " + f.title,
    "발견: " + f.detected_at.replace("T", " ") + " · " + f.site + " / " + f.area + (f.equipment_id.trim() ? " · " + f.equipment_id : ""),
    "제품 / 배치: " + f.product + " / " + f.batch,
    "도구 제안 등급: " + levelLabel(p.level) + " (제안, QA 확정 전)" + (p.note ? " · 반복 기준 미평가" : ""),
    "근거: " + p.reasons.join("; "),
    "반복 건 (최근 " + RULES.recurrence.window_days + "일): " + (item.look.checked ? item.look.rec.length + "건" : "조회 안 함 (" + item.look.why + ")"),
    "보고 기한: " + (item.due ? item.due + " (발견일 + " + dueDays + "일, 설정값)" : "미정"),
    "즉시 조치: " + f.immediate_actions.replace(/\s*\r?\n\s*/g, " "),
    "담당자 작성 필요: " + JUDGEMENT_FIELDS.join(", "),
    "",
    "초안 문서이며 승인 문서가 아님.",
  ].join("\n");
}
export function fileBase(id) { return (String(id || "").trim() || "deviation").replace(/[^\w.\-가-힣]+/g, "_") + "_draft"; }

/* ---------- several files in one .zip ---------- */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
export function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
// Names for the files of one archive. A name used twice (two drafts with the same number) gets _2, _3 before its extension,
// so no file replaces another when the archive is unpacked. Compared without case: Windows and macOS folders ignore it.
export function uniqueNames(names) {
  const used = new Set();
  return names.map(name => {
    const dot = name.lastIndexOf("."), stem = dot > 0 ? name.slice(0, dot) : name, ext = dot > 0 ? name.slice(dot) : "";
    let out = name, n = 1;
    while (used.has(out.toLowerCase())) out = stem + "_" + (++n) + ext;
    used.add(out.toLowerCase());
    return out;
  });
}
// A .zip that holds the given files as they are (stored, not compressed: a .docx is compressed already and the rest is small).
// files: [{ name, data: Uint8Array }]. Names are written as UTF-8. A name with a folder part or a character Windows refuses is an error.
export function zipStore(files, when = new Date()) {
  if (!files.length || files.length > 65535) throw new Error("zip: 파일 수 " + files.length);
  const enc = new TextEncoder();
  const time = (when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1);
  const date = ((when.getFullYear() - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate();
  const seen = new Set(), body = [], central = [];
  let offset = 0;
  for (const f of files) {
    if (typeof f.name !== "string" || !f.name || /[\\/:*?"<>|\u0000-\u001f]/.test(f.name) || /^\.+$/.test(f.name)) throw new Error("zip: 쓸 수 없는 파일 이름 (" + f.name + ")");
    if (seen.has(f.name.toLowerCase())) throw new Error("zip: 같은 파일 이름이 두 번 (" + f.name + ")");
    seen.add(f.name.toLowerCase());
    if (!(f.data instanceof Uint8Array)) throw new Error("zip: 파일 내용이 바이트 배열이 아님 (" + f.name + ")");
    const name = enc.encode(f.name), crc = crc32(f.data), size = f.data.length;
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);   // 0x0800: the name is UTF-8
    local.setUint16(10, time, true); local.setUint16(12, date, true); local.setUint32(14, crc, true);
    local.setUint32(18, size, true); local.setUint32(22, size, true); local.setUint16(26, name.length, true);
    const entry = new DataView(new ArrayBuffer(46));
    entry.setUint32(0, 0x02014b50, true); entry.setUint16(4, 20, true); entry.setUint16(6, 20, true); entry.setUint16(8, 0x0800, true);
    entry.setUint16(12, time, true); entry.setUint16(14, date, true); entry.setUint32(16, crc, true);
    entry.setUint32(20, size, true); entry.setUint32(24, size, true); entry.setUint16(28, name.length, true); entry.setUint32(42, offset, true);
    body.push(new Uint8Array(local.buffer), name, f.data);
    central.push(new Uint8Array(entry.buffer), name);
    offset += 30 + name.length + size;
  }
  const centralSize = central.reduce((n, b) => n + b.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, centralSize, true); end.setUint32(16, offset, true);
  const out = new Uint8Array(offset + centralSize + 22);
  let at = 0;
  for (const b of body.concat(central, [new Uint8Array(end.buffer)])) { out.set(b, at); at += b.length; }
  return out;
}
