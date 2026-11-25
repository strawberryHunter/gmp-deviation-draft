// Screenshots of every screen at 1280 and 390, light and dark, plus the two checks that must stay at zero:
// console errors and requests that leave the page's own files.
// node tools/shots.mjs [filter]   ->  shots/<screen>-<width>-<theme>.png
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { CHROME } from "./browser.mjs";

const only = process.argv[2] || "";
const page_url = new URL("../dist/local.html", import.meta.url).href;
const out = new URL("../shots/", import.meta.url);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const problems = [];

// Each screen: how to get there from a fresh page.
const SCREENS = {
  empty: async () => {},
  home: async p => { await p.click("#loadExamples"); await p.waitForSelector(".card"); },
  "home-filter": async p => { await SCREENS.home(p); await p.evaluate(() => { const D = window.__desk; D.S.ui.filter.level = "critical"; D.render(); }); },
  editor: async p => { await SCREENS.home(p); await p.evaluate(() => { const D = window.__desk; D.openEditor(D.S.drafts[3].uid); }); },
  "editor-flags": async p => { await SCREENS.home(p); await p.evaluate(() => { const D = window.__desk; D.openEditor(D.S.drafts[4].uid, 5); }); },
  "editor-recur": async p => { await SCREENS.home(p); await p.evaluate(() => { const D = window.__desk; D.openEditor(D.S.drafts[0].uid, 6); }); },
  preview: async p => { await SCREENS.home(p); await p.evaluate(async () => { const D = window.__desk; D.openEditor(D.S.drafts[4].uid, 0); await D.openPreview(D.S.drafts[4].uid); }); await p.waitForSelector(".doc"); },
  "preview-missing": async p => { await SCREENS.home(p); await p.evaluate(async () => { const D = window.__desk; D.openEditor(D.S.drafts[3].uid, 0); await D.openPreview(D.S.drafts[3].uid); }); await p.waitForSelector(".drawer .alert"); },
  recurrence: async p => { await SCREENS.home(p); await p.evaluate(() => { location.hash = "recurrence"; }); await p.waitForSelector(".kv"); },
  export: async p => { await SCREENS.home(p); await p.evaluate(() => { location.hash = "export"; }); await p.waitForSelector("table"); },
  guide: async p => { await p.evaluate(() => { location.hash = "guide"; }); await p.waitForSelector(".guide"); },
};

for (const [name, go] of Object.entries(SCREENS)) {
  if (only && !name.includes(only)) continue;
  for (const width of [1280, 390]) {
    for (const theme of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, deviceScaleFactor: width === 390 ? 2 : 1, colorScheme: theme, isMobile: width === 390, hasTouch: width === 390 });
      const page = await ctx.newPage();
      const tag = `${name}-${width}-${theme}`;
      page.on("console", m => { if (m.type() === "error") problems.push(`${tag}: console error: ${m.text()}`); });
      page.on("pageerror", e => problems.push(`${tag}: page error: ${e.message}`));
      page.on("request", r => { if (!/^(file|data|blob):/.test(r.url())) problems.push(`${tag}: outside request: ${r.url()}`); });
      await page.goto(page_url, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      await go(page);
      await page.waitForTimeout(150);
      const m = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        font: document.fonts.check('15px "Pretendard"'),
        sizes: [...new Set([...document.querySelectorAll("body *")].filter(e => e.offsetParent && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => getComputedStyle(e).fontSize))].sort(),
        weights: [...new Set([...document.querySelectorAll("body *")].filter(e => e.offsetParent && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => getComputedStyle(e).fontWeight))].sort(),
      }));
      if (m.overflow > 0) problems.push(`${tag}: page scrolls sideways by ${m.overflow}px`);
      if (!m.font) problems.push(`${tag}: Pretendard not loaded`);
      const badSize = m.sizes.filter(s => !["13px", "15px", "17px", "19px", "24px", "32px"].includes(s));
      if (badSize.length) problems.push(`${tag}: font sizes outside the scale: ${badSize.join(" ")}`);
      const badWeight = m.weights.filter(w => !["400", "700"].includes(w));
      if (badWeight.length) problems.push(`${tag}: font weights outside 400/700: ${badWeight.join(" ")}`);
      await page.screenshot({ path: new URL(tag + ".png", out).pathname, fullPage: false });
      await ctx.close();
    }
  }
}
await browser.close();
console.log(problems.length ? "PROBLEMS\n" + problems.join("\n") : "screens ok: console errors 0 · outside requests 0 · no sideways scroll · type scale ok");
process.exit(problems.length ? 1 : 0);
