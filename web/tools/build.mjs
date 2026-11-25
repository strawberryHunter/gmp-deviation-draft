// Build the published page: one HTML file (inline CSS, icons, JS) + fonts/, vendor/, licenses/ beside it.
// node tools/build.mjs  ->  dist/index.html (to publish), dist/local.html (same page with a viewport tag, for tests)
import { readFileSync, writeFileSync, mkdirSync, cpSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";

const root = new URL("../", import.meta.url);
const read = p => readFileSync(new URL(p, root), "utf8");

// --- CSS: the dark palette is written once and applied for system-dark, the viewer's dark choice, and the in-page toggle.
let css = read("src/style.css");
const dark = css.match(/\/\*DARK\{\*\/([\s\S]*?)\/\*\}DARK\*\//);
if (!dark) throw new Error("style.css: DARK block not found");
css = css.replace(dark[0],
  `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]):not([data-app-theme="light"]) {${dark[1]}} }\n` +
  `:root[data-theme="dark"]:not([data-app-theme="light"]) {${dark[1]}}\n:root[data-app-theme="dark"] {${dark[1]}}`);

// --- JS: engine.js and sample.js become objects; app.js keeps using E.name.
function exportNames(src) {
  const names = [...src.matchAll(/^export\s+(?:async\s+)?(?:const|function|class)\s+([A-Za-z_$][\w$]*)/gm)].map(m => m[1]);
  if (!names.length) throw new Error("no exports found");
  return names;
}
function moduleToObject(src) {
  const names = exportNames(src);
  return "(() => {\n" + src.replace(/^export\s+/gm, "") + "\nreturn { " + names.join(", ") + " };\n})()";
}
const app = read("src/app.js");
const imports = [...app.matchAll(/^import .*$/gm)].map(m => m[0]);
if (imports.length !== 2) throw new Error("app.js: expected exactly the engine and sample imports, found " + imports.length);
const js = '"use strict";\nconst E = ' + moduleToObject(read("src/engine.js")) + ";\n" +
  "const { " + exportNames(read("src/sample.js")).join(", ") + " } = " + moduleToObject(read("src/sample.js")) + ";\n" +
  app.replace(/^import .*$/gm, "");
if (js.includes("</script")) throw new Error("bundle contains </script");

// --- icons: one set (Lucide), only the ones the page uses.
const html = read("src/index.html");
const used = new Set();
for (const m of (app + html).matchAll(/(?:ic|mItem)\("([a-z0-9-]+)"|#i-([a-z0-9-]+)/g)) used.add(m[1] || m[2]);
for (const m of app.match(/CAT_ICON = \{([^}]*)\}/)[1].matchAll(/"([a-z0-9-]+)"/g)) used.add(m[1]);
const iconDir = new URL("assets/icons/", root);   // the Lucide icons the page uses (ISC, licenses/Lucide-LICENSE.txt)
const sprite = [...used].sort().map(name => {
  const svg = readFileSync(new URL(name + ".svg", iconDir), "utf8");
  const inner = svg.replace(/<!--[\s\S]*?-->/g, "").replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "").replace(/\s*\n\s*/g, " ").trim();
  return `<symbol id="i-${name}" viewBox="0 0 24 24">${inner}</symbol>`;
}).join("\n");

const page = html.replace("/*{{CSS}}*/", () => css).replace("<!--{{ICONS}}-->", () => sprite).replace("/*{{JS}}*/", () => js);
if (/\{\{[A-Z]+\}\}/.test(page)) throw new Error("unfilled placeholder");
const external = [...page.matchAll(/(?:src|href)=["'](https?:)?\/\/[^"']+/g)].map(m => m[0]).filter(u => !u.includes("www.w3.org"));
if (external.length) throw new Error("page loads something from outside: " + external.join(", "));

rmSync(new URL("dist/", root), { recursive: true, force: true });
mkdirSync(new URL("dist/", root), { recursive: true });
writeFileSync(new URL("dist/app.bundle.js", root), js);
execFileSync(process.execPath, ["--check", new URL("dist/app.bundle.js", root).pathname], { stdio: "inherit" });
writeFileSync(new URL("dist/index.html", root), page);
writeFileSync(new URL("dist/local.html", root), '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' +
  "<style>:root{color-scheme:light;box-sizing:border-box}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>\n" + page + "\n</body></html>");
for (const dir of ["fonts", "licenses"]) cpSync(new URL(dir + "/", root), new URL("dist/" + dir + "/", root), { recursive: true });
mkdirSync(new URL("dist/vendor/", root), { recursive: true });
cpSync(new URL("vendor/docx-8.5.0.umd.js", root), new URL("dist/vendor/docx-8.5.0.umd.js", root));
console.log(`built dist/index.html  ${(page.length / 1024).toFixed(0)} KB · ${used.size} icons · css ${(css.length / 1024).toFixed(0)} KB · js ${(js.length / 1024).toFixed(0)} KB`);
