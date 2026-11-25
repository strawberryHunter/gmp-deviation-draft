// List every sentence and label the screens show (not the entered data, not the draft document), to cut and shorten.
// node tools/strings.mjs  ->  docs/ui-strings.md
import { chromium } from "playwright-core";
import { writeFileSync, mkdirSync } from "node:fs";
import { CHROME } from "./browser.mjs";

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(new URL("../dist/local.html", import.meta.url).href);
const grab = () => page.evaluate(() => {
  const out = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const el = n.parentElement;
    if (!el || el.closest("script,style,.doc,datalist,select") || !el.getClientRects().length) continue;
    const t = n.textContent.replace(/\s+/g, " ").trim();
    if (t) out.push(t);
  }
  document.querySelectorAll("[placeholder]").forEach(e => { if (e.getClientRects().length) out.push("(입력 예) " + e.placeholder); });
  document.querySelectorAll("[title]").forEach(e => { if (e.getClientRects().length) out.push("(툴팁) " + e.title); });
  return out;
});
const screens = {};
screens["빈 화면"] = await grab();
await page.click("#loadExamples"); await page.waitForSelector(".card");
await page.click("#moreBtn"); screens["홈 + 더보기 메뉴"] = await grab(); await page.keyboard.press("Escape");
await page.evaluate(() => { const D = window.__desk; D.openEditor(D.S.drafts[3].uid); });
screens["작성 화면"] = await grab();
await page.click('.ebar button:has-text("미리보기")'); await page.waitForSelector(".drawer"); screens["미리보기 (빠진 항목)"] = await grab(); await page.keyboard.press("Escape");
await page.click(".ebar .btn.primary"); screens["내보내기 메뉴"] = (await grab()).filter(t => /Word|Markdown|복사|저장/.test(t)); await page.keyboard.press("Escape");
for (const [hash, name] of [["recurrence", "반복성 조회"], ["export", "내보내기"], ["guide", "사용법"]]) {
  await page.evaluate(h => { location.hash = h; }, hash); await page.waitForTimeout(100); screens[name] = await grab();
}
await browser.close();

// Entered sample data is not UI copy.
const data = /^(DEV-\d|Plant |SYN-|DS-|RM-|[A-Z]{2,4}-[A-Z0-9]|N\/A|\d{4}-\d{2}-\d{2}|\d+$|\d+\/\d+$|major$|minor$)/;
const seen = new Set();
let md = "# 화면 문구 목록\n\n`node tools/strings.mjs`로 다시 만듦. 입력 데이터와 초안 문서 본문은 제외.\n";
let count = 0, sentences = [];
for (const [name, list] of Object.entries(screens)) {
  const fresh = [...new Set(list)].filter(t => !seen.has(t) && !data.test(t));
  fresh.forEach(t => seen.add(t));
  md += `\n## ${name}\n\n` + fresh.map(t => "- " + t).join("\n") + "\n";
  count += fresh.length;
  sentences.push(...fresh.filter(t => /(니다|세요|십시오|해요|!)/.test(t)));
}
mkdirSync(new URL("../docs/", import.meta.url), { recursive: true });
writeFileSync(new URL("../docs/ui-strings.md", import.meta.url), md);
console.log(`${count} strings -> docs/ui-strings.md`);
console.log(sentences.length ? "설명체·느낌표가 남은 문구:\n" + sentences.join("\n") : "설명체(~니다/~세요)·느낌표 문구 0건");
