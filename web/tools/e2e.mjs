// Do each job the way a QA author would: real clicks and typing in a headless browser, counting clicks.
// node tools/e2e.mjs   (headless only: it never touches the real mouse or keyboard)
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { CHROME } from "./browser.mjs";

const url = new URL("../dist/local.html", import.meta.url).href;
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const results = [];
const bad = [];

async function open({ downloads = true, storage, phone } = {}) {
  const ctx = await browser.newContext(phone ? { viewport: phone, isMobile: true, hasTouch: true, locale: "ko-KR" } : { viewport: { width: 1280, height: 900 }, locale: "ko-KR" });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"]);
  const page = await ctx.newPage();
  page.on("console", m => { if (m.type() === "error") bad.push("console error: " + m.text()); });
  page.on("pageerror", e => bad.push("page error: " + e.message));
  page.on("request", r => { if (!/^(file|data|blob):/.test(r.url())) bad.push("outside request: " + r.url()); });
  // The claude.ai viewer gives the page a save function; here a stand-in records what would be saved.
  if (downloads) await page.addInitScript(() => {
    window.__saved = [];
    window.claude = { use: async name => name === "downloads" ? { save: async ({ filename, data }) => {
      const size = typeof data === "string" ? data.length : data.size;
      const head = typeof data === "string" ? data.slice(0, 80) : new TextDecoder("latin1").decode(new Uint8Array(await data.slice(0, 2).arrayBuffer()));
      window.__saved.push({ filename, size, head }); return { status: "saved" };
    } } : null };
  });
  if (storage) await page.addInitScript(s => { for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); }, storage);
  await page.goto(url, { waitUntil: "load" });
  let clicks = 0;
  const click = async sel => { await page.click(sel); clicks++; };
  return { ctx, page, click, clicks: () => clicks, reset: () => { clicks = 0; } };
}
const text = (page, sel) => page.locator(sel).first().innerText();
async function job(name, fn) {
  try { const note = await fn(); results.push(["ok", name, note || ""]); }
  catch (e) { results.push(["FAIL", name, e.message.split("\n").slice(0, 6).join(" | ") + " @ " + ((e.stack || "").match(/e2e\.mjs:(\d+)/) || [])[1]]); }
}

await job("1 새 초안을 처음부터 써서 Word로 받기", async () => {
  const { page, click, clicks, ctx } = await open();
  await click("#side .new");                                   // 1: the cursor is already in the first field
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-id");
  const kb = page.keyboard;
  await kb.type("DEV-2026-9001"); await kb.press("Tab");
  await page.selectOption("#f-category", "equipment"); await kb.press("Tab");
  await kb.type("HPLC 시스템 적합성 분해능 기준 미달"); await kb.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-synthetic"); await kb.press("Tab");   // the practice checkbox is one Tab stop
  for (const v of ["Plant A", "QC Lab", "SYN-mAb-07 drug substance", "DS-26-0500", "HPLC-07", "Release testing"]) { await kb.type(v); await kb.press("Tab"); }
  await page.fill("#f-detected_at", "2026-11-25T09:15"); await page.focus("#f-detected_by");
  await kb.type("QC 분석원"); await kb.press("Tab");
  await kb.type("시스템 적합성 분해능 1.8 (기준 2.0 이상). 분석 중단."); await kb.press("Tab");
  await kb.type("결과 보류, QA 통보 (09:40)");
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-immediate_actions");
  // Risk questions with the keyboard only: Tab into each group, Space = 예, ArrowRight = 아니오.
  await page.focus("#cpp_excursion-true");
  const answers = [false, true, false, false, false, false, false, false];
  for (let n = 0; n < answers.length; n++) { await kb.press(answers[n] ? "Space" : "ArrowRight"); if (n < answers.length - 1) await kb.press("Tab"); }
  assert.equal(await text(page, "#e-prog .txt"), "필수 11/11 · 질문 8/8");
  assert.equal(await text(page, "#e-aside .acard:nth-child(2) .chip"), "MAJOR (제안)");
  await click(".ebar .btn.primary");                           // 2: 내보내기
  await click('.menu button:has-text("Word")');                // 3: Word (.docx)
  await page.waitForFunction(() => window.__saved.length === 1);
  const saved = await page.evaluate(() => window.__saved[0]);
  assert.equal(saved.filename, "DEV-2026-9001_draft.docx"); assert.equal(saved.head, "PK"); assert.ok(saved.size > 8000);
  assert.equal(await text(page, "#e-chips .chip"), "검토 대기");
  assert.equal(clicks(), 3);
  await ctx.close();
  return "클릭 3번 (새 초안 → 내보내기 → Word) + 타이핑";
});

await job("1b 파일 저장이 없는 화면에서는 본문 복사", async () => {
  const { page, click, ctx } = await open({ downloads: false });
  await click("#loadExamples"); await page.waitForSelector(".card");
  await click('.card:has-text("DEV-2026-2301") .open');
  await click(".ebar .btn.primary");
  assert.equal(await page.locator('.menu button:has-text("Word")').count(), 0);
  await click('.menu button:has-text("본문 복사")');
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("복사함"));
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  assert.ok(clip.startsWith("# Deviation 보고서 초안 — DEV-2026-2301")); assert.ok(clip.includes("☐ **작성 필요**"));
  await ctx.close();
});

await job("2 빠진 항목 찾기", async () => {
  const { page, click, clicks, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  assert.equal(await text(page, '.stat:has-text("필수 항목 빠짐") b'), "1");
  const before = clicks();
  await click('.stat:has-text("필수 항목 빠짐")');              // 1: the list shows only drafts with something missing
  assert.equal(await page.locator(".card").count(), 1);
  await click(".card .open");                                  // 2: opens with the cursor in the missing field
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-detected_by");
  assert.equal(await page.locator("#e-steps .nav-item:nth-child(3) .cnt").textContent(), "1개 빠짐");
  await page.keyboard.type("유틸리티 담당");
  assert.equal(await page.locator("#e-steps .cnt").count(), 0);
  assert.equal(clicks() - before, 2);
  // An export attempt on an incomplete draft makes nothing and points at what is missing.
  await page.fill("#f-detected_by", "");
  await click(".ebar .btn.primary"); await click('.menu button:has-text("본문 복사")');
  assert.ok((await text(page, ".drawer .alert b")).startsWith("초안 안 만듦 · 빠진 항목 1개"));
  await click('.drawer .panel button:has-text("발견자")');
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-detected_by");
  assert.equal(await page.getAttribute("#f-detected_by", "aria-invalid"), "true");
  await ctx.close();
  return "클릭 2번 (숫자 → 카드), 커서가 빠진 칸에 놓임";
});

await job("3 등급 따져 보기 (제안과 근거만, 판단 칸은 빈칸)", async () => {
  const { page, click, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  const chips = await page.locator(".card .foot .chip").allInnerTexts();
  assert.deepEqual(chips.sort(), ["CRITICAL 제안", "CRITICAL 제안", "CRITICAL 제안", "MAJOR 제안", "MAJOR 제안", "MAJOR 제안", "MINOR 제안", "빠짐 · 발견자"]);
  // The counts in the sidebar are the CLI's results for the 8 forms: 3 / 3 / 1 and one form it rejects.
  assert.deepEqual(await page.locator('#side nav[aria-label="도구 제안 등급"] .n').allInnerTexts(), ["3", "3", "1", "1"]);
  await click('.card:has-text("DEV-2026-2204") .open');
  assert.equal(await text(page, "#e-aside .acard:nth-child(2) .chip"), "MAJOR · 입력 완료 전");
  await page.keyboard.press("Escape"); await page.keyboard.press("Escape");
  await click('.card:has-text("DEV-2026-2201") .open');         // 1
  assert.equal(await text(page, "#e-aside .acard:nth-child(2) .chip"), "MAJOR (제안)");
  assert.equal(await page.locator("#e-aside .acard:nth-child(2) li").count(), 3);
  assert.deepEqual(await page.locator("#e-aside .jrow .chip").allInnerTexts(), ["담당자 작성", "담당자 작성", "담당자 작성", "담당자 작성"]);
  await click('.ebar button:has-text("미리보기")');             // 2
  await page.waitForSelector(".doc");
  const doc = (await text(page, ".doc")).replace(/\n+/g, "\n");
  for (const h of ["6. 근본원인\n☐ 작성 필요", "7. 제품 품질 영향 평가\n☐ 작성 필요", "QA 검토자 확정 등급: ☐ 작성 필요"]) assert.ok(doc.includes(h), h);
  assert.equal(await page.locator(".doc .blank").count(), 14);
  await ctx.close();
  return "카드에 바로 표시 (클릭 0번), 근거는 클릭 1번";
});

await job("4 같은 설비의 과거 건 찾기", async () => {
  const { page, click, clicks, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  const before = clicks();
  await click('.stat:has-text("반복 건 있음")');                 // 1
  assert.deepEqual((await page.locator(".card .saved .id").allInnerTexts()).sort(), ["DEV-2026-2201", "DEV-2026-2204"]);
  assert.equal(clicks() - before, 1);
  // A real (not synthetic) draft never uses the bundled synthetic history.
  await click("#side .new");
  await page.fill("#f-site", "Plant A"); await page.fill("#f-equipment_id", "CHR-03"); await page.selectOption("#f-category", "process_parameter");
  assert.equal(await text(page, "#step-s7 dd:nth-of-type(3)"), "조회 안 함 · 이력 파일 없음");
  // Loading a history file: a real one (synthetic column removed) gives 5 matches for the same keys.
  const csv = (await page.evaluate(() => window.__desk.E && document.querySelector("body") && null)) || null; void csv;
  const real = await page.evaluate(() => { const t = window.__desk; return t.S.sampleHistory.text.split("\n").map(l => l.split(",").slice(0, 7).join(",")).join("\n"); });
  await page.setInputFiles('#step-s7 input[type=file]', { name: "qms_history.csv", mimeType: "text/csv", buffer: Buffer.from("﻿" + real, "utf8") });
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("이력 51건"));
  assert.equal(await text(page, "#step-s7 dd:nth-of-type(3)"), "반복 건 5건");
  // A broken file says what is wrong and what to do next.
  await page.setInputFiles('#step-s7 input[type=file]', { name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from("dev_id,opened\nA,2026-01-01\n") });
  await click('#step-s7 button:has-text("이력 관리")');
  assert.ok((await text(page, ".alert")).includes("필수 열 없음: site"));
  assert.ok((await text(page, ".alert .next")).startsWith("다음:"));
  await ctx.close();
  return "클릭 1번 (숫자), 이력 파일은 한 번만 선택";
});

await job("5 보고 기한", async () => {
  const { page, click, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  const today = await page.evaluate(() => window.__desk.E.todayISO());
  const want = await page.evaluate(() => { const D = window.__desk, E = D.E; const due = D.items().map(i => i.due).sort()[0]; return [E.ddayLabel(E.dday(due, E.todayISO())), E.shortDate(due)]; });
  assert.equal(await text(page, ".hero .dday"), want[0]);
  assert.ok((await text(page, ".hero .why")).startsWith("보고 기한 " + want[1]));
  // Changing the rule (days after detection) updates every card.
  await click("#moreBtn"); await page.fill('.menu input[type=number]', "3"); await page.keyboard.press("Tab"); await page.keyboard.press("Escape");
  const dd = await page.evaluate(() => window.__desk.items().map(i => i.dd));
  assert.ok(dd.every(n => n <= 3), "all due within 3 days of detection: " + dd.join(","));
  assert.ok(Number(await text(page, '.stat:has-text("7일 안 기한") b')) + Number(await page.locator('.stat:has-text("기한 지남") b').count() ? await text(page, '.stat:has-text("기한 지남") b') : 0) >= 1, today);
  await ctx.close();
  return "입력 즉시 D-day 표시 (클릭 0번)";
});

await job("6 비슷한 건 복제해서 시작 + 자동완성", async () => {
  const { page, click, clicks, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  const before = clicks();
  await click('.card:has-text("DEV-2026-2201") .more');         // 1
  await click('.menu button:has-text("복제해서 새 초안")');      // 2
  assert.equal(clicks() - before, 2);
  assert.equal(await page.evaluate(() => document.activeElement.id), "f-id");
  const v = id => page.inputValue("#f-" + id);
  assert.deepEqual([await v("site"), await v("equipment_id"), await v("category"), await v("detected_by")], ["Plant A", "CHR-03", "process_parameter", "공정 운전원 (2교대)"]);
  assert.deepEqual([await v("id"), await v("title"), await v("batch"), await v("description")], ["", "", "", ""]);
  assert.equal(await page.locator("#f-flags input:checked").count(), 0, "risk answers are never carried over");
  assert.ok((await page.locator("#dl-equipment_id option").evaluateAll(o => o.map(x => x.value))).includes("HPLC-07"));
  await ctx.close();
  return "클릭 2번, 위치·설비·발견자 유지, 사건 내용·위험 질문은 비움";
});

await job("새 초안의 생성일은 오늘 날짜를 따라감 (직접 바꾸면 고정)", async () => {
  const { page, click, ctx } = await open();
  await click("#side .new");
  const r = await page.evaluate(() => { const D = window.__desk, d = D.S.drafts[0]; d.form.today = "2026-01-01"; D.render(); const auto = d.form.today; return [auto, D.E.todayISO()]; });
  assert.equal(r[0], r[1]);
  await page.fill("#f-today", "2026-11-20");
  assert.equal(await page.evaluate(() => { const D = window.__desk; D.render(); return D.S.drafts[0].form.today; }), "2026-11-20");
  await ctx.close();
});

await job("측정값: Excel 범위를 한 번에 붙여넣기", async () => {
  const { page, click, ctx } = await open();
  await click("#side .new");
  await click('#step-s5 button:has-text("측정값 추가")');
  await page.evaluate(() => navigator.clipboard.writeText("항목\t기준\t실측\t비고\nElution pH\t3.40-3.60\t3.62\t6 min\nTOC\t≤ 500 ppb\t412 ppb\t"));
  await page.keyboard.press("ControlOrMeta+V");
  await page.waitForFunction(() => document.querySelectorAll("#f-parameters .prow").length === 2);
  assert.deepEqual(await page.evaluate(() => window.__desk.S.drafts[0].form.parameters),
    [{ name: "Elution pH", spec: "3.40-3.60", actual: "3.62", duration: "6 min" }, { name: "TOC", spec: "≤ 500 ppb", actual: "412 ppb", duration: "" }]);
  await ctx.close();
  return "행마다 클릭 1번 + 4칸 입력 → 붙여넣기 1번";
});

await job("YAML 가져오기: CLI 양식을 그대로, CLI가 거부하는 파일은 이유와 함께 거부", async () => {
  const { page, click, ctx } = await open();
  const { readFileSync } = await import("node:fs");
  const data = name => readFileSync(new URL("../../data/synthetic/" + name, import.meta.url), "utf8");
  const forms = { "DEV-2026-2201.yaml": data("intake/DEV-2026-2201.yaml"), "DEV-2026-2202.yaml": data("intake/DEV-2026-2202.yaml"),
    "DEV-2026-2203.yaml": data("intake/DEV-2026-2203.yaml"), "DEV-2026-2301.yaml": data("showcase/DEV-2026-2301.yaml") };
  const file = (name, text) => ({ name, mimeType: "application/x-yaml", buffer: Buffer.from(text, "utf8") });
  await click("#moreBtn");
  await page.locator('.menu button:has-text("YAML 양식 가져오기")').waitFor();
  await page.keyboard.press("Escape");
  await page.setInputFiles("#yamlFile", [
    file("DEV-2026-2201.yaml", forms["DEV-2026-2201.yaml"]), file("DEV-2026-2203.yaml", forms["DEV-2026-2203.yaml"]),
    file("with_root_cause.yaml", forms["DEV-2026-2202.yaml"] + "root_cause: 장갑 노후\n"),
    file("odd.yaml", forms["DEV-2026-2301.yaml"].replace("spec_oos: false", "spec_oos: no").replace("batch: DS-26-0418", "batch: 0412")),
    file("broken.yaml", "id: X\ntitle: a: b\n")]);
  await page.waitForSelector(".drawer");
  const result = (await text(page, ".drawer .scroll")).replace(/\n+/g, " | ");
  assert.ok(result.includes("가져옴 3건") && result.includes("거부 2건"), result);
  assert.ok(result.includes("알 수 없는 항목: root_cause"), result);
  assert.ok(result.includes("YAML 문법 오류 (2행)"), result);
  assert.ok(result.includes("규격 이탈(OOS): 'no' → 미응답으로 가져옴"), result);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".card").count(), 3);
  // Same proposals as the CLI for the two clean files (the synthetic history comes with synthetic forms, as in the CLI).
  assert.equal(await text(page, '.card:has-text("DEV-2026-2201") .foot .chip'), "MAJOR 제안");
  assert.equal(await text(page, '.card:has-text("DEV-2026-2203") .foot .chip'), "MINOR 제안");
  assert.equal(await text(page, '.card:has-text("DEV-2026-2301") .foot .chip'), "빠짐 · 규격 이탈(OOS)");
  assert.equal(await page.evaluate(() => window.__desk.S.drafts.find(d => d.form.id === "DEV-2026-2301").form.batch), "0412");
  await ctx.close();
  return "클릭 2번 + 파일 선택, 여러 파일 한 번에";
});

await job("저장된 데이터가 깨졌으면 알리고 나머지만 불러옴", async () => {
  const { page, ctx } = await open({ storage: { "deviation-desk-data-v1": JSON.stringify({ v: 1, drafts: [{ uid: "x", form: { id: "broken" } }], sample: false, history: null }) } });
  await page.waitForFunction(() => !document.querySelector("#toast").hidden);
  assert.ok((await text(page, "#toast")).includes("1건은 형식이 달라"));
  assert.equal(await page.locator(".card").count(), 0);
  await ctx.close();
});

await job("저장: 기본은 탭에만 보관, 켜면 새로고침 뒤에도 남음", async () => {
  const { page, click, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  assert.equal(await page.evaluate(() => localStorage.getItem("deviation-desk-data-v1")), null);
  await click("#moreBtn");
  // The settings rows must read as rows: label on one line, a real switch beside it (this once collapsed to one letter per line).
  const row = await page.evaluate(() => { const r = document.querySelector(".menu .mrow"), s = r.querySelector(".switch"), l = r.querySelector("span");
    return { label: l.textContent, labelH: l.getBoundingClientRect().height, switchW: s.getBoundingClientRect().width, switchH: s.getBoundingClientRect().height }; });
  assert.deepEqual([row.label, row.switchW, row.switchH], ["브라우저 저장", 40, 24]); assert.ok(row.labelH < 30, "label height " + row.labelH);
  await click('.menu .switch'); await page.keyboard.press("Escape");
  await page.evaluate(() => { const D = window.__desk; D.S.ui.filter.level = "critical"; D.render(); });
  await click('.seg button:has-text("MAJOR")');
  await page.reload({ waitUntil: "load" }); await page.waitForSelector(".card");
  assert.equal(await page.locator(".card").count(), 3, "drafts and the MAJOR filter survive a reload");
  assert.equal(await page.getAttribute('.seg button:has-text("MAJOR")', "aria-pressed"), "true");
  await click("#moreBtn"); await click('.menu .switch'); await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => localStorage.getItem("deviation-desk-data-v1")), null, "turning it off removes what was stored");
  await ctx.close();
});

await job("목록: 검색, 필터, 삭제 되돌리기, 완료 표시, 키보드", async () => {
  const { page, click, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  await page.keyboard.press("/"); await page.keyboard.type("hplc-07");
  assert.equal(await page.locator(".card").count(), 1);
  await page.keyboard.press("Escape"); await click('.filters button:has-text("필터 지움")');
  await click('#side .nav-item:has-text("CRITICAL")'); assert.equal(await page.locator(".card").count(), 3);
  await click('#side .nav-item:has-text("전체")'); await click('#side .nav-item:has-text("CRITICAL")');
  assert.equal(await page.locator(".card").count(), 8);
  await click('.card:has-text("DEV-2026-2301") .more'); await click('.menu button:has-text("삭제")');
  assert.equal(await page.locator(".card").count(), 7);
  await click('#toast button'); assert.equal(await page.locator(".card").count(), 8);
  await click('.card:has-text("DEV-2026-2204") .more');
  assert.equal(await page.locator('.menu button:has-text("완료로 표시")').count(), 0, "a draft with something missing cannot be marked done");
  await page.keyboard.press("Escape");
  await click('.card:has-text("DEV-2026-2301") .more'); await click('.menu button:has-text("완료로 표시")');
  assert.equal(await text(page, '#side .nav-item:has-text("완료") .n'), "1");
  // A finished draft shows no countdown, even when its due date has passed.
  await page.evaluate(() => { const D = window.__desk; D.S.settings.dueDays = 0; D.render(); });
  assert.ok((await text(page, '.card:has-text("DEV-2026-2301") .line')).startsWith("완료 · 기한 11/24"));
  assert.equal(await page.locator('.card:has-text("DEV-2026-2301") .line b.late').count(), 0);
  assert.ok((await text(page, '.card:has-text("DEV-2026-2201") .line')).startsWith("D+"));
  await page.evaluate(() => { const D = window.__desk; D.S.settings.dueDays = 30; D.render(); });
  await click('.card:has-text("DEV-2026-2301") .open'); await page.keyboard.press("Escape"); await page.keyboard.press("Escape");
  assert.equal(await page.locator("#editor").isVisible(), false, "Esc leaves the editor");
  await ctx.close();
});

await job("폰: 메뉴 서랍이 화면 안에 들어오고 맨 아래 사용법까지 닿음", async () => {
  // A short phone (iPhone SE height). The drawer was once as tall as its content, so its last rows sat below the screen with no way to scroll.
  const { page, ctx } = await open({ phone: { width: 375, height: 667 } });
  await page.tap("#loadExamples"); await page.waitForSelector(".card");
  await page.tap("#menuBtn"); await page.waitForSelector(".shell.nav-open");
  const m = await page.evaluate(() => { const s = document.getElementById("side"), r = s.getBoundingClientRect();
    return { bottom: Math.round(r.bottom), vh: innerHeight, scrolls: s.scrollHeight > s.clientHeight }; });
  assert.equal(m.bottom, m.vh, "drawer ends at the screen's bottom edge"); assert.equal(m.scrolls, true, "content longer than the screen scrolls inside the drawer");
  await page.locator('#side .nav-item:has-text("사용법")').scrollIntoViewIfNeeded();
  const foot = await page.evaluate(() => { const r = document.querySelector("#side .foot p").getBoundingClientRect(); return { text: document.querySelector("#side .foot p").textContent, bottom: Math.round(r.bottom), vh: innerHeight }; });
  assert.equal(foot.text, "개인 프로젝트 · 셀트리온과 무관"); assert.ok(foot.bottom <= foot.vh, "last line on screen: " + foot.bottom + " > " + foot.vh);
  await page.tap('#side .nav-item:has-text("사용법")');
  assert.equal(await text(page, "#view h1"), "사용법");
  assert.equal(await page.evaluate(() => document.querySelector(".shell").classList.contains("nav-open")), false, "drawer closes after choosing");
  await ctx.close();
});

await job("내보내기: 요약표 복사와 CSV, 메일용 요약", async () => {
  const { page, click, ctx } = await open();
  await click("#loadExamples"); await page.waitForSelector(".card");
  await click('#side .nav-item:has-text("내보내기")');
  await click('button:has-text("표 복사")');
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("표 복사함"));
  const tsv = await page.evaluate(() => navigator.clipboard.readText());
  const rows = tsv.trim().split("\n").map(r => r.split("\t"));
  assert.equal(rows.length, 9); assert.equal(rows[0][2], "제안 등급"); assert.equal(rows[1][2], "MAJOR (제안)"); assert.equal(rows[4][7], "필수 항목 누락: 발견자");
  await click('button:has-text("CSV 저장")');
  await page.waitForFunction(() => window.__saved.length === 1);
  assert.ok((await page.evaluate(() => window.__saved[0].filename)).endsWith(".csv"));
  await click('table.summary tr:nth-child(1) button:has-text("내보내기")'); await click('.menu button:has-text("메일용 요약 복사")');
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("메일용 요약"));
  assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes("도구 제안 등급: MAJOR (제안, QA 확정 전)"));
  await ctx.close();
});

await browser.close();
for (const [s, n, note] of results) console.log((s === "ok" ? "ok   " : "FAIL ") + n + (note ? "  — " + note : ""));
if (bad.length) console.log("PROBLEMS\n" + [...new Set(bad)].join("\n"));
const failed = results.filter(r => r[0] !== "ok").length;
console.log(`${results.length - failed}/${results.length} jobs ok · console errors and outside requests: ${bad.length}`);
process.exit(failed || bad.length ? 1 : 0);
