// app.js — the screens. Every check, proposal and document comes from engine.js; nothing here decides a grade.
import * as E from "./engine.js";
import { SAMPLE_FORMS, SAMPLE_HISTORY, TEMPLATE_COMMENTS } from "./sample.js";

(function () {
  const SVG = "http://www.w3.org/2000/svg";
  const $ = (sel, root) => (root || document).querySelector(sel);
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    kids.flat(Infinity).forEach(c => { if (c !== null && c !== undefined && c !== false) el.append(c); });
    return el;
  }
  // Replace an element's children; like h(), skips null/false and flattens arrays.
  function add(el, ...kids) {
    kids.flat(Infinity).forEach(c => { if (c !== null && c !== undefined && c !== false) el.append(c); });
    return el;
  }
  function fill(el, ...kids) { el.replaceChildren(); return add(el, ...kids); }
  function ic(name) {
    const s = document.createElementNS(SVG, "svg"); s.setAttribute("class", "ic"); s.setAttribute("aria-hidden", "true");
    const u = document.createElementNS(SVG, "use"); u.setAttribute("href", "#i-" + name); s.appendChild(u); return s;
  }
  const CAT_ICON = { equipment: "wrench", environmental_monitoring: "wind", documentation: "file-text", process_parameter: "sliders-horizontal",
    material: "package", personnel: "users", utilities: "droplets", none: "tag" };
  const VIEWS = ["drafts", "recurrence", "export", "guide"];
  const PLACEHOLDER = { id: "DEV-2026-2301", title: "무엇이 기준과 달랐는지", site: "Plant A", area: "QC Lab", product: "제품명 또는 N/A", batch: "배치 번호 또는 N/A",
    equipment_id: "HPLC-07", process_step: "Release testing", detected_by: "QC 분석원", description: "관찰한 사실, 기록된 수치, 시각", immediate_actions: "수행한 조치, 통보 대상과 시각" };
  // Why each field is needed (one line) and what it rests on.
  const HELP = {
    synthetic: ["연습용 표시", "초안 모든 쪽에 '합성 데이터' 표시 · 예시 이력 사용 가능"],
    id: ["QMS 번호와 초안 연결", "이력에 같은 번호가 있으면 반복 건에서 제외"],
    category: ["조사 계획(6M) 순서와 반복성 조회 기준", "비우면 반복성 조회 안 함"],
    title: ["무엇이 기준과 달랐는지 한 줄", "원인은 제목에 넣지 않음"],
    site: ["반복성 조회 기준", "사업장·설비·유형이 모두 같은 건만 조회"],
    area: ["발생 위치 식별", "초안 상단 표에 그대로 표시"],
    product: ["영향 범위 식별", "제품 무관이면 N/A"],
    batch: ["영향 범위 식별", "배치 무관이면 N/A"],
    equipment_id: ["반복성 조회 기준", "설비 대장 번호 그대로 · 비우면 조회 안 함"],
    process_step: ["어느 공정에서 생긴 일인지", "초안 상단 표에 그대로 표시"],
    detected_at: ["보고 기한 계산 기준", "초안 생성일 이후 일시는 거부"],
    detected_by: ["발견 경로 기록", "이름 대신 직무·소속"],
    description: ["확인된 사실·수치·시각만", "원인 추정은 적지 않음 · 근본원인은 담당자 작성"],
    immediate_actions: ["이미 한 조치와 통보 시각", "계획만 있는 조치는 '예정' 표기"],
    parameters: ["초안의 수치는 이 표에서만 나옴", "기준·실측은 기록의 표기 그대로 · Excel 범위 붙여넣기 가능 (항목·기준·실측·비고 순)"],
    flags: ["등급 제안의 입력", "미응답은 '아니오'로 처리 안 함 · 8개 모두 필요"],
    recurrence: ["같은 사업장·설비·유형의 과거 건 목록", "목록만 표시 · 원인 연관성은 판단 안 함"],
    today: ["반복성 조회 기간과 미래 일시 검사의 기준일", "초안 머리글에 표시 · 새 초안은 오늘 날짜 자동, 직접 바꾸면 고정"],
  };

  /* ---------- state ---------- */
  const S = {
    drafts: [],            // {uid, form, exported, done, savedAt}
    history: null,         // the user's QMS history file
    sampleHistory: null,   // bundled synthetic history, used by synthetic drafts only
    histError: null,
    settings: { persist: false, dueDays: 30 },
    ui: { view: "drafts", filter: { status: "all", category: "", level: "", site: "", quick: "" }, sort: "due", theme: "system" },
    query: "", hero: 0, edit: null, navOpen: false,
  };
  let downloads = null, uidSeq = 0, persistTimer = 0, toastTimer = 0, closeMenu = null, closeDrawer = null;
  const UI_KEY = "deviation-desk-ui-v1", DATA_KEY = "deviation-desk-data-v1";

  // Browser storage can be missing or blocked. A failure is remembered and shown where saving is offered.
  const store = {
    ok: true, why: "",
    fail(e) { store.ok = false; store.why = String((e && e.message) || e); },
    get(k) { try { const s = localStorage.getItem(k); return s ? JSON.parse(s) : null; } catch (e) { store.fail(e); return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { store.fail(e); return false; } },
    del(k) { try { localStorage.removeItem(k); return true; } catch (e) { store.fail(e); return false; } },
  };
  function saveUI() { store.set(UI_KEY, { filter: S.ui.filter, sort: S.ui.sort, theme: S.ui.theme, dueDays: S.settings.dueDays }); }
  function persistNow() {
    clearTimeout(persistTimer);
    if (!S.settings.persist) return;
    const ok = store.set(DATA_KEY, { v: 1, drafts: S.drafts, sample: !!S.sampleHistory,
      history: S.history ? { name: S.history.name, text: S.history.text, warning: S.history.warning } : null });
    if (!ok) { S.settings.persist = false; toast("브라우저 저장 실패 · 탭에만 보관"); }
  }
  function persist() { clearTimeout(persistTimer); persistTimer = setTimeout(persistNow, 300); }
  async function loadState() {
    const ui = store.get(UI_KEY);
    if (ui) {
      Object.assign(S.ui.filter, ui.filter || {});
      if (["due", "saved", "id"].includes(ui.sort)) S.ui.sort = ui.sort;
      if (["light", "dark", "system"].includes(ui.theme)) S.ui.theme = ui.theme;
      if (Number.isInteger(ui.dueDays) && ui.dueDays >= 0 && ui.dueDays <= 365) S.settings.dueDays = ui.dueDays;
    }
    const data = store.get(DATA_KEY);
    if (data && Array.isArray(data.drafts)) {
      S.settings.persist = true;
      S.drafts = data.drafts.filter(E.isDraftShape);
      S.dropped = data.drafts.length - S.drafts.length;
      uidSeq = S.drafts.length;
      if (data.sample) S.sampleHistory = await E.parseHistory("예시 이력 (합성).csv", SAMPLE_HISTORY);
      if (data.history) {
        try { S.history = await E.parseHistory(data.history.name, data.history.text, data.history.warning); }
        catch (e) { if (!(e instanceof E.HistoryError)) throw e; S.histError = { cause: e.message, next: e.next }; }
      }
    }
  }

  /* ---------- derived ---------- */
  function item(d) {
    if (d.autoToday) d.form.today = E.todayISO();
    const hist = E.pickHistory(d.form, S.history, S.sampleHistory);
    const x = E.inspect(d.form, hist, S.settings.dueDays, E.todayISO());
    return Object.assign(x, { d, form: d.form, hist, savedAt: d.savedAt, status: E.statusOf(d, x.errs) });
  }
  const items = () => S.drafts.map(item);
  const draftOf = uid => S.drafts.find(d => d.uid === uid);
  function newDraft(form, autoToday) {
    const d = { uid: "d" + Date.now().toString(36) + (uidSeq++), form, exported: false, done: false, savedAt: Date.now(), autoToday: !!autoToday };
    S.drafts.push(d); return d;
  }
  function touched(d) { d.savedAt = Date.now(); d.exported = false; d.done = false; persist(); }
  const catLabel = c => E.CAT_LABEL[c] || "분류 미정";
  const whereOf = f => f.equipment_id.trim() || f.area.trim() || "위치 미입력";
  function ddClass(dd) { return dd === null ? "" : dd <= 0 ? "late" : dd <= 7 ? "soon" : ""; }
  // A grade is shown as a proposal only for a complete form (the CLI makes none for an incomplete one).
  // live: inside the editor, show what the answers so far would give, marked as not yet a proposal.
  function gradeChip(i, suffix, live) {
    const waiting = E.missingLabel(i.form) || (i.errs.length ? "입력 오류 " + i.errs.length + "건" : "제안 전");
    if (!i.prop) return h("span", { class: "chip none", text: live ? "질문 " + i.comp.flags.length + "개 남음" : waiting });
    if (i.errs.length) return h("span", { class: "chip none", text: live ? E.levelLabel(i.prop.level) + " · 입력 완료 전" : waiting });
    return h("span", { class: "chip " + i.prop.level, text: E.levelLabel(i.prop.level) + (suffix || " 제안") });
  }

  /* ---------- toast, menu, drawer ---------- */
  function toast(msg, action) {
    const t = $("#toast"); clearTimeout(toastTimer);
    fill(t, h("span", { text: msg }));
    if (action) t.append(h("button", { type: "button", text: action.label, onclick: () => { t.hidden = true; action.run(); } }));
    t.classList.toggle("up", !!S.edit); t.hidden = false;
    toastTimer = setTimeout(() => { t.hidden = true; }, action ? 7000 : 3200);
  }
  function openMenu(anchor, build) {
    if (closeMenu) closeMenu();
    const m = h("div", { class: "menu", role: "menu" });
    const close = () => { m.remove(); document.removeEventListener("pointerdown", away, true); closeMenu = null; anchor.setAttribute("aria-expanded", "false"); };
    const away = e => { if (!m.contains(e.target) && !anchor.contains(e.target)) close(); };
    build(m, close);
    m.style.position = "fixed"; m.style.visibility = "hidden";
    $("#layer").append(m);
    const r = anchor.getBoundingClientRect(), w = m.offsetWidth, ht = m.offsetHeight;
    const left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8));
    const top = r.bottom + 6 + ht > innerHeight - 8 ? Math.max(8, r.top - ht - 6) : r.bottom + 6;
    m.style.left = left + "px"; m.style.top = top + "px"; m.style.visibility = "";
    anchor.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", away, true);
    closeMenu = close;
    const first = m.querySelector("button, input"); if (first) first.focus({ preventScroll: true });
  }
  const mItem = (icon, label, run, cls) => h("button", { type: "button", role: "menuitem", class: cls || "", onclick: run }, ic(icon), label);
  function openDrawer(title, headRight, body) {
    if (closeDrawer) closeDrawer();
    const back = document.activeElement;
    const dim = h("div", { class: "dim", onclick: () => close() });
    const panel = h("section", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("header", {}, h("h2", { text: title }), h("div", { class: "right" }, headRight || [],
        h("button", { type: "button", class: "btn icon quiet", "aria-label": "닫기", onclick: () => close() }, ic("x")))),
      h("div", { class: "scroll" }, body));
    function close() { dim.remove(); panel.remove(); closeDrawer = null; if (back && back.isConnected) back.focus({ preventScroll: true }); }
    // Tab stays inside the panel (it is a modal dialog): from the last control to the first, and back with Shift.
    panel.addEventListener("keydown", e => {
      if (e.key !== "Tab") return;
      const stops = [...panel.querySelectorAll("button, a[href], input, select, textarea, [tabindex]")].filter(x => !x.disabled && x.tabIndex >= 0 && x.getClientRects().length);
      if (!stops.length) return;
      const first = stops[0], last = stops[stops.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    $("#layer").append(dim, panel); closeDrawer = close;
    panel.querySelector("header .btn.icon").focus({ preventScroll: true });
    return panel;
  }
  async function copyText(text, okMsg) {
    try { await navigator.clipboard.writeText(text); toast(okMsg); return true; }
    catch (e) {
      const ta = h("textarea", { readonly: true, "aria-label": "복사할 내용" }); ta.value = text;
      openDrawer("복사 실패 · 직접 선택", null, h("div", { class: "copybox" }, h("p", { class: "muted small", text: "아래 내용을 선택해 복사 (" + ((e && e.name) || "오류") + ")" }), ta));
      ta.focus(); ta.select(); return false;
    }
  }
  async function saveFile(filename, data, okMsg) {
    if (!downloads) { toast("이 화면에서는 파일 저장 불가 · 복사 사용"); return false; }
    try { await downloads.save({ filename, data }); toast(okMsg); return true; }
    catch (e) {
      const c = e && e.code;
      toast(c === "declined" ? "저장 취소함" : c === "rate_limited" ? "잠시 후 다시 시도" : c === "host_unavailable" ? "이 앱에서는 저장 불가 · 브라우저에서 열기"
        : "저장 실패" + (e && e.message ? " · " + e.message : ""));
      return false;
    }
  }

  /* ---------- actions ---------- */
  function setView(view) {
    S.edit = null; S.ui.view = view; S.navOpen = false;
    if (location.hash.slice(1) !== view) { try { history.replaceState(null, "", "#" + view); } catch (e) { location.hash = view; } }
    render(); scrollTo(0, 0);
  }
  function clearFilters() { S.ui.filter = { status: "all", category: "", level: "", site: "", quick: "" }; S.query = ""; $("#q").value = ""; saveUI(); render(); }
  function setFilter(key, value) {
    S.ui.filter[key] = S.ui.filter[key] === value && key !== "status" ? "" : value;
    S.ui.view = "drafts"; S.edit = null; S.navOpen = false; S.hero = 0; saveUI(); render();
  }
  function createDraft() { const d = newDraft(E.blankForm(E.todayISO()), true); persist(); openEditor(d.uid, 0); }
  async function loadExamples() {
    S.sampleHistory = await E.parseHistory("예시 이력 (합성).csv", SAMPLE_HISTORY);
    const have = new Set(S.drafts.map(d => d.form.id));
    let n = 0;
    SAMPLE_FORMS.forEach(f => { if (!have.has(f.id)) { newDraft(JSON.parse(JSON.stringify(f))); n++; } });
    persist(); render(); toast(n ? "합성 예시 " + n + "건 불러옴" : "합성 예시는 이미 있음");
  }
  // Intake forms written for the CLI (.yaml). A file the CLI would refuse is not taken; the reason is shown.
  async function importYAML(files) {
    const results = [];
    for (const file of files) {
      const res = { name: file.name, errors: [], notes: [], id: "" };
      results.push(res);
      let text;
      try { text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
      catch (e) { res.errors.push("UTF-8이 아님 · 'UTF-8'로 다시 저장 (" + e.name + ")"); continue; }
      let parsed;
      try { parsed = E.formFromRaw(E.parseFormYAML(text), E.todayISO(), TEMPLATE_COMMENTS); }
      catch (e) { if (!(e instanceof E.YamlError)) throw e; res.errors.push("YAML 문법 오류 (" + e.line + "행): " + e.message); continue; }
      res.errors = parsed.errors; res.notes = parsed.notes;
      if (!parsed.form) continue;
      const id = parsed.form.id.trim();
      if (id && S.drafts.some(d => d.form.id.trim() === id)) { res.errors = ["같은 번호의 초안이 이미 있음: " + id]; continue; }
      if (parsed.form.synthetic && !S.sampleHistory) S.sampleHistory = await E.parseHistory("예시 이력 (합성).csv", SAMPLE_HISTORY);
      newDraft(parsed.form, true); res.id = id;
    }
    persist(); render();
    const ok = results.filter(r => !r.errors.length).length;
    if (results.every(r => !r.errors.length && !r.notes.length)) { toast("YAML " + ok + "건 가져옴"); return; }
    openDrawer("가져오기 결과", null, [
      h("div", { class: "sumline" }, h("span", { text: "가져옴 " + ok + "건" }), h("span", { text: "거부 " + (results.length - ok) + "건" })),
      results.map(r => h("section", { class: "panel" }, h("p", {}, h("b", { text: r.name }), " · " + (r.errors.length ? "거부" : "가져옴")),
        r.errors.length ? h("div", { class: "alert", role: "alert" }, r.errors.map(t => h("span", { text: t }))) : null,
        r.notes.length ? h("ul", { class: "notes" }, r.notes.map(t => h("li", { text: t }))) : null))]);
  }
  function removeDraft(uid) {
    const idx = S.drafts.findIndex(d => d.uid === uid); if (idx < 0) return;
    const [gone] = S.drafts.splice(idx, 1);
    if (S.edit && S.edit.uid === uid) S.edit = null;
    persist(); render();
    toast("삭제함", { label: "되돌리기", run: () => { S.drafts.splice(Math.min(idx, S.drafts.length), 0, gone); persist(); render(); } });
  }
  function cloneDraft(uid) {
    const src = draftOf(uid); if (!src) return;
    const d = newDraft(E.cloneForNew(src.form, E.todayISO()), true); persist();
    openEditor(d.uid, 0); toast("복제함 · 사건 내용과 위험 질문은 비움");
  }
  function setDone(uid, done) {
    const d = draftOf(uid); if (!d) return;
    if (done && item(d).errs.length) { toast("필수 항목이 빠진 초안은 완료로 표시 불가"); return; }
    d.done = done; if (done) d.exported = true; persist(); render();
    toast(done ? "완료로 표시함" : "작성 중으로 되돌림");
  }
  function draftMenu(anchor, uid) {
    const i = item(draftOf(uid));
    openMenu(anchor, (m, close) => {
      m.append(mItem("copy-plus", "복제해서 새 초안", () => { close(); cloneDraft(uid); }));
      if (i.status === "done") m.append(mItem("undo-2", "작성 중으로 되돌림", () => { close(); setDone(uid, false); }));
      else if (!i.errs.length) m.append(mItem("circle-check", "완료로 표시", () => { close(); setDone(uid, true); }));
      m.append(h("hr"), mItem("trash-2", "삭제", () => { close(); removeDraft(uid); }, "danger"));
    });
  }
  async function pickHistoryFile(file) {
    const buf = await file.arrayBuffer(); let text, warning = "";
    try { text = new TextDecoder("utf-8", { fatal: true }).decode(buf); }
    catch (e1) {
      try { text = new TextDecoder("euc-kr", { fatal: true }).decode(buf); warning = "CP949로 읽음 · 'CSV UTF-8' 저장 권장"; }
      catch (e2) { S.histError = { cause: "UTF-8도 CP949도 아닌 파일", next: "Excel에서 'CSV UTF-8'로 다시 저장" }; render(); return; }
    }
    try { S.history = await E.parseHistory(file.name, text, warning); S.histError = null; toast("이력 " + S.history.rows.length + "건 불러옴"); }
    catch (e) { if (!(e instanceof E.HistoryError)) throw e; S.histError = { cause: e.message, next: e.next }; }
    persist(); render();
  }
  function historyInput() {
    const input = h("input", { type: "file", accept: ".csv,text/csv", hidden: true, "aria-label": "이력 CSV 파일",
      onchange: e => { const f = e.target.files && e.target.files[0]; if (f) pickHistoryFile(f); e.target.value = ""; } });
    return [input, h("button", { type: "button", class: "btn", onclick: () => input.click() }, ic("upload"), "이력 CSV 선택")];
  }
  // "빠진 항목 3개" while everything stopping the draft is just unfilled; "고칠 곳 1개" once something has to be corrected.
  function blockedText(errs) { const b = E.blockCount(errs); return (b.missingOnly ? "빠진 항목 " : "고칠 곳 ") + b.n + "개"; }
  // A draft with something to fill or correct is not exported in any form: show what stops it instead. true = stopped.
  function blocked(uid) {
    const i = item(draftOf(uid));
    if (!i.errs.length) return false;
    openPreview(uid); toast(blockedText(i.errs) + " · 초안 안 만듦"); return true;
  }
  async function exportDraft(uid, kind) {
    const d = draftOf(uid), i = item(d);
    if (blocked(uid)) return;
    if (kind === "mail") { await copyText(E.mailSummary(i, S.settings.dueDays), "메일용 요약 복사함"); return; }
    const model = await E.buildModel(d.form, i.hist), base = E.fileBase(d.form.id);
    let ok = false;
    if (kind === "docx") {
      if (!window.docx) { toast("Word 변환 모듈 로드 실패 · Markdown 사용"); return; }
      ok = await saveFile(base + ".docx", await window.docx.Packer.toBlob(E.buildDocx(model, window.docx)), "Word 저장함 · 검토 대기로 옮김");
    } else if (kind === "md") ok = await saveFile(base + ".md", E.toMarkdown(model), "Markdown 저장함 · 검토 대기로 옮김");
    else ok = await copyText(E.toMarkdown(model), "본문 복사함 · 검토 대기로 옮김");
    if (ok) { d.exported = true; persist(); render(); }
  }
  function exportMenu(anchor, uid) {
    if (blocked(uid)) return;   // no format to choose while nothing can be made: one click to what is missing
    openMenu(anchor, (m, close) => {
      const run = kind => () => { close(); exportDraft(uid, kind); };
      if (downloads) m.append(mItem("file-type", "Word (.docx)", run("docx")), mItem("file-down", "Markdown (.md)", run("md")));
      m.append(mItem("copy", "본문 복사", run("copy")), mItem("mail", "메일용 요약 복사", run("mail")));
      if (!downloads) m.append(h("p", { class: "note", text: "파일 저장은 claude.ai 화면에서 가능" }));
    });
  }

  /* ---------- sidebar and top bar ---------- */
  function navItem(label, count, current, run, cls) {
    return h("button", { type: "button", class: "nav-item" + (cls ? " " + cls : "") + (count === 0 ? " zero" : ""), "aria-current": current ? "true" : null, onclick: run },
      h("span", { class: "t", text: label }), count === null ? null : h("span", { class: "n", text: String(count) }));
  }
  function renderSide(list) {
    const F = S.ui.filter, onDrafts = S.ui.view === "drafts" && !S.edit;
    const n = fn => list.filter(fn).length;
    const cats = E.RULES.categories.map(c => [c, E.CAT_LABEL[c]]);
    if (n(i => !i.form.category)) cats.push(["none", "분류 미정"]);
    const levels = E.RULES.levels.map(l => [l.id, l.label]);
    if (n(i => i.level === "none")) levels.push(["none", "제안 전"]);
    fill($("#side"), 
      h("div", { class: "name", text: "Deviation 초안 데스크" }),
      h("button", { type: "button", class: "btn new", onclick: createDraft }, ic("plus"), "새 초안"),
      h("h2", { text: "초안" }),
      h("nav", { class: "nav", "aria-label": "초안 상태" }, ["drafting", "review", "done", "all"].map(s =>
        navItem(E.STATUS_LABEL[s], s === "all" ? list.length : n(i => i.status === s), onDrafts && F.status === s, () => setFilter("status", s)))),
      h("h2", { text: "분류" }),
      h("nav", { class: "nav", "aria-label": "분류" }, cats.map(([c, name]) =>
        navItem(name, n(i => (i.form.category || "none") === c), onDrafts && F.category === c, () => setFilter("category", c)))),
      h("h2", { text: "도구 제안 등급" }),
      h("nav", { class: "nav", "aria-label": "도구 제안 등급" }, levels.map(([l, name]) =>
        navItem(name, n(i => i.level === l), onDrafts && F.level === l, () => setFilter("level", l)))),
      h("h2", { text: "도구" }),
      h("nav", { class: "nav", "aria-label": "도구" },
        navItem("반복성 조회", null, S.ui.view === "recurrence" && !S.edit, () => setView("recurrence")),
        navItem("내보내기", null, S.ui.view === "export" && !S.edit, () => setView("export"))),
      h("div", { class: "foot" },
        navItem("사용법", null, S.ui.view === "guide" && !S.edit, () => setView("guide")),
        h("p", { text: "개인 프로젝트 · 셀트리온과 무관" })));
  }
  function applyTheme() {
    const root = document.documentElement;
    if (S.ui.theme === "system") root.removeAttribute("data-app-theme"); else root.setAttribute("data-app-theme", S.ui.theme);
    document.querySelectorAll("[data-theme-pick]").forEach(b => b.setAttribute("aria-checked", String(b.dataset.themePick === S.ui.theme)));
  }
  function moreMenu(anchor) {
    openMenu(anchor, (m, close) => {
      const sw = h("button", { type: "button", class: "switch", role: "switch", "aria-checked": String(S.settings.persist), "aria-label": "브라우저 저장", disabled: !store.ok,
        onclick: () => {
          S.settings.persist = !S.settings.persist;
          if (S.settings.persist) { persistNow(); if (S.settings.persist) toast("브라우저 저장 켬"); } else { store.del(DATA_KEY); toast("브라우저 저장 끔 · 저장분 지움"); }
          sw.setAttribute("aria-checked", String(S.settings.persist)); render();
        } });
      const days = h("input", { type: "number", min: "0", max: "365", step: "1", value: String(S.settings.dueDays), "aria-label": "보고 기한 일수",
        onchange: () => { const v = Number(days.value); if (Number.isInteger(v) && v >= 0 && v <= 365) { S.settings.dueDays = v; saveUI(); render(); } else days.value = String(S.settings.dueDays); } });
      let armed = false;
      const wipe = mItem("trash-2", "전체 지움", () => {
        if (!armed) { armed = true; wipe.lastChild.textContent = "한 번 더 누르면 전체 지움"; return; }
        S.drafts = []; S.history = null; S.sampleHistory = null; S.histError = null; store.del(DATA_KEY); if (S.settings.persist) persistNow(); close(); clearFilters(); toast("전체 지움");
      }, "danger");
      const themeHidden = getComputedStyle($("#themeSeg")).display === "none";
      const themeRow = themeHidden ? h("div", { class: "mrow" }, h("span", { text: "테마" }), h("div", { class: "seg", role: "radiogroup", "aria-label": "화면 테마" },
        [["light", "라이트"], ["dark", "다크"], ["system", "시스템"]].map(([val, text]) => h("button", { type: "button", role: "radio", "data-theme-pick": val, "aria-checked": String(S.ui.theme === val), text,
          onclick: () => { S.ui.theme = val; saveUI(); applyTheme(); } })))) : null;
      add(m,
        themeRow,
        h("div", { class: "mrow" }, h("span", { text: "브라우저 저장" }), sw),
        store.ok ? null : h("p", { class: "note", text: "브라우저 저장소 사용 불가" }),
        h("div", { class: "mrow" }, h("span", { text: "보고 기한 · 발견일 +" }), h("span", {}, days, " 일")),
        h("hr"),
        mItem("upload", "YAML 양식 가져오기", () => { close(); $("#yamlFile").click(); }),
        mItem("clipboard-list", "예시 불러오기 (합성 8건)", () => { close(); loadExamples(); }),
        wipe);
    });
  }

  /* ---------- home ---------- */
  // filtered: the list is narrowed by a search or filter. The card then shows the most urgent of what is listed, or nothing.
  function heroCard(list, filtered) {
    const hero = E.heroItems(list, 3);
    if (!hero.length && filtered) return null;
    if (!hero.length) {
      return h("section", { class: "hero empty" }, h("h2", { text: "열린 초안 없음" }), h("div", { class: "acts" },
        h("button", { type: "button", class: "btn primary lg", onclick: createDraft }, ic("plus"), "새 초안")));
    }
    S.hero = Math.min(S.hero, hero.length - 1);
    const i = hero[S.hero], f = i.form, miss = i.comp.total - i.comp.done;
    const meta = [f.id || "번호 미입력", whereOf(f), catLabel(f.category)];
    return h("section", { class: "hero", "aria-label": "먼저 볼 초안" },
      h("div", {},
        h("div", { class: "badges" },
          h("span", { class: "dday " + ddClass(i.dd), text: i.dd === null ? "기한 미정" : E.ddayLabel(i.dd) }),
          i.dd !== null && i.dd < 0 ? h("span", { class: "chip critical", text: "기한 지남" }) : null,
          gradeChip(i), f.synthetic ? h("span", { class: "chip info", text: "합성" }) : null),
        h("h2", { text: f.title || "제목 없음" }),
        h("p", { class: "why", text: i.due ? "보고 기한 " + E.shortDate(i.due) + " · 발견일 " + E.shortDate(f.detected_at.slice(0, 10)) + " + " + S.settings.dueDays + "일" : "발견 일시 입력 전 · 기한 계산 안 됨" }),
        h("p", { class: "meta" }, meta.map((t, k) => h("span", { text: (k ? "· " : "") + t })),
          miss ? h("span", { class: "miss", text: "· 필수 항목 " + miss + "개 빠짐" }) : null)),
      h("button", { type: "button", class: "btn primary lg go", onclick: () => openEditor(i.d.uid) }, i.status === "drafting" ? "이어서 작성" : "열기", ic("arrow-right")),
      hero.length > 1 ? h("div", { class: "pager" },
        h("button", { type: "button", class: "btn sm icon", "aria-label": "이전", onclick: () => { S.hero = (S.hero + hero.length - 1) % hero.length; render(); } }, ic("chevron-left")),
        h("button", { type: "button", class: "btn sm icon", "aria-label": "다음", onclick: () => { S.hero = (S.hero + 1) % hero.length; render(); } }, ic("chevron-right")),
        h("span", { class: "dots", "aria-hidden": "true" }, hero.map((_, k) => h("i", { class: k === S.hero ? "on" : "" }))),
        h("span", { text: (S.hero + 1) + "/" + hero.length })) : null);
  }
  function card(i) {
    const f = i.form, uid = i.d.uid;
    return h("article", { class: "card", "data-uid": uid },
      h("div", { class: "head" }, ic(CAT_ICON[f.category || "none"]), h("span", { class: "where", text: whereOf(f) }),
        f.synthetic ? h("span", { class: "chip info", text: "합성" }) : null,
        h("button", { type: "button", class: "btn sm icon quiet more", "aria-label": "초안 메뉴", "aria-haspopup": "menu", onclick: e => draftMenu(e.currentTarget, uid) }, ic("ellipsis"))),
      h("h3", {}, h("button", { type: "button", class: "open", text: f.title || "제목 없음", onclick: () => openEditor(uid) })),
      // A finished draft has no countdown: its due date stays, the red "D+n" does not.
      h("p", { class: "line" }, i.status === "done" ? [h("b", { class: "done", text: "완료" }), i.due ? " · 기한 " + E.shortDate(i.due) : ""]
        : i.dd === null ? "기한 미정" : [h("b", { class: ddClass(i.dd), text: E.ddayLabel(i.dd) }), " · " + E.shortDate(i.due)], " · " + catLabel(f.category)),
      h("div", { class: "foot" }, gradeChip(i), h("div", { class: "bar", role: "img", "aria-label": "완성도 " + i.comp.done + "/" + i.comp.total }, h("i", { style: "width:" + Math.round(100 * i.comp.done / i.comp.total) + "%" })),
        h("span", { class: "small muted", text: i.comp.done + "/" + i.comp.total })),
      h("p", { class: "saved" }, h("span", {}, h("span", { class: "id", text: f.id || "번호 미입력" }), " · " + E.STATUS_LABEL[i.status]), h("span", { text: E.agoLabel(i.savedAt, Date.now()) })));
  }
  function viewHome(list) {
    const v = $("#view");
    if (!S.drafts.length) {
      fill(v, h("section", { class: "hero empty" },
        h("h1", { text: "초안 없음", style: "font-size:24px" }),
        h("p", { class: "muted", text: "새 초안을 만들거나 합성 예시 8건으로 시작" }),
        h("div", { class: "acts" },
          h("button", { type: "button", class: "btn primary lg", onclick: createDraft }, ic("plus"), "새 초안"),
          h("button", { type: "button", class: "btn lg", id: "loadExamples", onclick: loadExamples }, "예시 불러오기"),
          h("button", { type: "button", class: "btn lg quiet", onclick: () => $("#yamlFile").click() }, ic("upload"), "YAML 가져오기"))));
      return;
    }
    const F = S.ui.filter, matched = E.filterItems(list, F, S.query), shown = E.sortItems(matched, S.ui.sort);
    const open = list.filter(i => i.status !== "done");
    const stat = (label, count, pressed, run, cls) => h("button", { type: "button", class: "stat" + (cls ? " " + cls : ""), "aria-pressed": String(pressed), onclick: run }, h("span", { text: label }), h("b", { text: String(count) }));
    const overdue = open.filter(i => i.dd !== null && i.dd < 0).length;
    const last = Math.max(...list.map(i => i.savedAt));
    const sites = [...new Set(list.map(i => i.form.site).filter(Boolean))].sort();
    const sel = (label, value, options, run) => h("select", { "aria-label": label, onchange: e => run(e.target.value) },
      options.map(([val, text]) => { const o = h("option", { value: val, text }); o.selected = val === value; return o; }));
    const active = F.status !== "all" || F.category || F.level || F.site || F.quick || S.query;
    const title = (F.status === "all" ? "전체 초안" : E.STATUS_LABEL[F.status]);
    fill(v, 
      heroCard(active ? matched : list, !!active),
      h("div", { class: "title-row" }, h("h1", { text: title }), h("span", { class: "count", text: shown.length + "건" })),
      h("div", { class: "stats" },
        stat("작성 중", list.filter(i => i.status === "drafting").length, F.status === "drafting", () => setFilter("status", F.status === "drafting" ? "all" : "drafting")),
        overdue ? stat("기한 지남", overdue, F.quick === "overdue", () => setFilter("quick", "overdue"), "alert") : null,
        stat("오늘 기한", open.filter(i => i.dd === 0).length, F.quick === "today", () => setFilter("quick", "today")),
        stat("7일 안 기한", open.filter(i => i.dd !== null && i.dd >= 0 && i.dd <= 7).length, F.quick === "week", () => setFilter("quick", "week")),
        stat("필수 항목 빠짐", list.filter(i => i.comp.done < i.comp.total).length, F.quick === "missing", () => setFilter("quick", "missing")),
        stat("반복 건 있음", list.filter(i => i.look.checked && i.look.rec.length).length, F.quick === "recur", () => setFilter("quick", "recur")),
        h("span", { class: "updated", text: "마지막 저장 " + new Date(last).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) + (S.settings.persist ? "" : " · 탭에만 보관") })),
      h("div", { class: "filters" },
        sel("분류", F.category, [["", "전체 분류"]].concat(E.RULES.categories.map(c => [c, E.CAT_LABEL[c]])), val => setFilter("category", val || F.category)),
        sites.length > 1 ? sel("사업장", F.site, [["", "전체 사업장"]].concat(sites.map(s => [s, s])), val => setFilter("site", val || F.site)) : null,
        h("div", { class: "seg", role: "group", "aria-label": "도구 제안 등급" },
          [["", "전체", list.length]].concat(E.RULES.levels.map(l => [l.id, l.label, list.filter(i => i.level === l.id).length])).map(([id, label, count]) =>
            h("button", { type: "button", "aria-pressed": String(F.level === id), onclick: () => { F.level = id; S.hero = 0; saveUI(); render(); } }, label, h("span", { class: "n", text: String(count) })))),
        active && shown.length ? h("button", { type: "button", class: "btn quiet", onclick: clearFilters }, ic("x"), "필터 지움") : null,   // with nothing listed, the empty state below has the one button
        h("div", { class: "sort" }, sel("정렬", S.ui.sort, [["due", "기한순"], ["saved", "최근 저장순"], ["id", "번호순"]], val => { S.ui.sort = val; saveUI(); render(); }))),
      shown.length ? h("div", { class: "grid" }, shown.map(card))
        : h("div", { class: "blankstate" }, h("p", { text: "조건에 맞는 초안 없음" }), h("button", { type: "button", class: "btn", onclick: clearFilters }, "필터 지움")));
  }

  /* ---------- tool pages ---------- */
  function historyPanel() {
    const H = S.history;
    return h("section", { class: "panel" }, h("h2", { text: "QMS 이력" }),
      S.histError ? h("div", { class: "alert", role: "alert" }, h("b", { text: S.histError.cause }), h("span", { class: "next", text: "다음: " + S.histError.next })) : null,
      h("dl", { class: "kv" },
        h("dt", { text: "파일" }), h("dd", { text: H ? H.name : "선택 안 함" }),
        H ? [h("dt", { text: "건수" }), h("dd", { text: H.rows.length + "건" + (H.synthetic ? " · 합성 데이터" : "") })] : null,
        H && H.warning ? [h("dt", { text: "주의" }), h("dd", { text: H.warning })] : null,
        S.sampleHistory ? [h("dt", { text: "예시 이력" }), h("dd", { text: S.sampleHistory.rows.length + "건 · 합성 초안에만 사용" })] : null,
        h("dt", { text: "조회 기준" }), h("dd", { text: "사업장·설비·유형 일치 · 최근 " + E.RULES.recurrence.window_days + "일" }),
        h("dt", { text: "필요한 열" }), h("dd", { text: "dev_id, opened, site, equipment_id, category, final_class" })),
      h("div", { class: "row" }, historyInput(),
        H ? h("button", { type: "button", class: "btn quiet", onclick: () => { S.history = null; S.histError = null; persist(); render(); toast("이력 지움"); } }, ic("x"), "이력 지움") : null));
  }
  function viewRecurrence(list) {
    const rows = list.map(i => h("tr", { class: "click", tabindex: "0", onclick: () => openEditor(i.d.uid, 6), onkeydown: e => { if (e.key === "Enter") openEditor(i.d.uid, 6); } },
      h("td", { class: "num key", text: i.form.id || "번호 미입력" }), h("td", { "data-label": "설비", text: i.form.equipment_id || "—" }), h("td", { "data-label": "분류", text: catLabel(i.form.category) }),
      h("td", { "data-label": "이력", text: i.hist ? i.hist.name : "없음" }),
      h("td", { "data-label": "결과" }, i.look.checked ? (i.look.rec.length ? h("b", { text: i.look.rec.length + "건" }) : "없음") : "조회 안 함 · " + i.look.why)));
    fill($("#view"), 
      h("div", { class: "title-row" }, h("h1", { text: "반복성 조회" }), h("span", { class: "count", text: "반복 건 있음 " + list.filter(i => i.look.checked && i.look.rec.length).length + "건" })),
      historyPanel(),
      h("section", { class: "panel" }, h("h2", { text: "초안별 결과" }),
        list.length ? h("div", { class: "tw" }, h("table", { class: "stack" }, h("thead", {}, h("tr", {}, ["번호", "설비", "분류", "이력", "결과"].map(t => h("th", { text: t })))), h("tbody", {}, rows)))
          : h("p", { class: "muted", text: "초안 없음" })));
  }
  function viewExport(list) {
    const rows = E.summaryRows(list);
    // On screen the eight copied values sit in six columns so the row and its button fit without sideways scrolling:
    // reasons (or what is missing) under the title, detection time under the due date. Copy and CSV keep the CLI's eight columns.
    const table = h("table", { class: "summary stack" }, h("thead", {}, h("tr", {}, ["Deviation 번호", "제목 · 제안 근거", "제안 등급", "반복 건", "보고 기한 · 발견", "파일"].map(t => h("th", { text: t })))),
      h("tbody", {}, rows.map((r, k) => { const i = list[k], [id, title, , why, rec, found, due, fix] = r;
        return h("tr", {},
          h("td", { class: "num key" + (id ? "" : " muted"), text: id || "번호 미입력" }),
          h("td", { "data-label": "제목" }, h("span", { class: title ? "" : "muted", text: title || "제목 없음" }),
            fix ? h("span", { class: "sub fix", text: "보완 필요 · " + fix }) : why ? h("span", { class: "sub", text: why }) : null),
          h("td", { "data-label": "제안 등급" }, gradeChip(i), i.prop && !i.errs.length && i.prop.note ? h("span", { class: "sub", text: "반복 기준 미평가" }) : null),
          h("td", { class: "num", "data-label": "반복 건", text: rec === "" ? "" : /^\d+$/.test(rec) ? rec + "건" : rec }),
          h("td", { class: "num", "data-label": "보고 기한" }, due ? h("span", {}, i.status !== "done" && i.dd !== null ? h("b", { class: ddClass(i.dd), text: E.ddayLabel(i.dd) + " · " }) : null, due) : h("span", { class: "muted", text: "기한 미정" }),
            found ? h("span", { class: "sub", text: "발견 " + found }) : null),
          h("td", { class: "num act" }, i.errs.length ? h("button", { type: "button", class: "btn sm", onclick: () => openEditor(i.d.uid) }, "보완")
            : h("button", { type: "button", class: "btn sm", "aria-haspopup": "menu", onclick: e => exportMenu(e.currentTarget, i.d.uid) }, ic("download"), "내보내기"))); })));
    const name = "deviation_summary_" + E.todayISO();
    fill($("#view"), 
      h("div", { class: "title-row" }, h("h1", { text: "내보내기" }), h("span", { class: "count", text: list.length + "건" })),
      h("section", { class: "panel" }, h("h2", { text: "요약표" }),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn primary", disabled: !list.length, onclick: () => copyText(E.toTSV(E.SUMMARY_HEAD, rows), "표 복사함 · Excel에 붙여넣기") }, ic("table"), "표 복사"),
          downloads ? h("button", { type: "button", class: "btn", disabled: !list.length, onclick: () => saveFile(name + ".csv", E.toCSV(E.SUMMARY_HEAD, rows), "CSV 저장함") }, ic("file-down"), "CSV 저장") : null,
          h("span", { class: "chip none", text: "확정 등급·우선순위 없음" }),
          h("span", { class: "muted", text: "복사·CSV " + E.SUMMARY_HEAD.length + "열 · CLI 요약표와 같은 내용" })),
        list.length ? h("div", { class: "tw" }, table) : h("p", { class: "muted", text: "초안 없음" })));
  }
  function viewGuide() {
    const li = arr => h("ul", {}, arr.map(t => h("li", { text: t })));
    const P = (title, ...body) => h("section", { class: "panel" }, h("h2", { text: title }), body);
    const lic = (text, file) => h("li", {}, text + " · ", h("a", { href: "licenses/" + file, target: "_blank", rel: "noopener", text: "라이선스" }));
    fill($("#view"), 
      h("div", { class: "title-row" }, h("h1", { text: "사용법" })),
      h("div", { class: "guide" },
        P("순서", li(["새 초안 → 8단계 입력", "빨간 점이 있는 단계 = 빠진 항목", "미리보기에서 초안 확인", "내보내기: Word · Markdown · 복사", "받은 파일의 노란 칸을 담당자가 작성 → QMS 등록",
          "CLI 양식(.yaml)은 더보기 → YAML 양식 가져오기 · 값은 적힌 그대로 읽음"])),
        P("도구가 비워 두는 칸", li(E.JUDGEMENT_FIELDS.concat(["6M 조사 결과"])), h("p", { class: "muted small", text: "초안과 근거 정리까지만. 승인 문서 아님 · 서명과 승인은 검증된 QMS에서" })),
        P("등급 제안 기준", h("div", { class: "tw" }, h("table", {}, h("tbody", {}, E.RULES.levels.map(l => h("tr", {}, h("td", { class: "num" }, h("span", { class: "chip " + l.id, text: l.label })),
          h("td", { text: (E.RULES.classes[l.id] || []).map(t => t.reason).join(" · ") || "위 기준에 해당 없음" })))))),
          h("p", { class: "muted small", text: "기본 규칙의 예시 값 · 사내 SOP 대조 전 · 확정은 QA 검토자" })),
        P("반복성 조회", li(["사업장·설비·유형이 모두 같은 과거 건 · 최근 " + E.RULES.recurrence.window_days + "일", "이력 CSV가 없거나 설비·유형이 비면 '조회 안 함' (반복 없음 아님)", "목록만 표시 · 원인 연관성은 판단 안 함"])),
        P("보고 기한", li(["발견일 + " + S.settings.dueDays + "일 (더보기 메뉴에서 변경)", "작업 관리용 설정값 · SOP 규칙 아님 · 초안 문서에는 안 들어감"])),
        P("저장과 전송", li(["입력과 파일은 이 브라우저 안에서만 처리 · 외부 전송 없음", "기본은 탭에만 보관 · 새로고침하면 사라짐", "더보기 → 브라우저 저장을 켜면 이 기기에 보관", "공용 PC에서는 저장을 켜지 않음"])),
        P("단축키", h("dl", { class: "kv" }, h("dt", {}, h("kbd", { text: "/" })), h("dd", { text: "검색" }), h("dt", {}, h("kbd", { text: "Esc" })), h("dd", { text: "닫기 · 목록으로" }))),
        P("구성 요소", h("ul", {}, lic("Word 변환 docx 8.5.0 (MIT)", "docx-LICENSE.txt"), lic("글꼴 Pretendard 1.3.9 (SIL OFL 1.1)", "Pretendard-LICENSE.txt"), lic("아이콘 Lucide 1.70.0 (ISC)", "Lucide-LICENSE.txt")),
          h("p", { class: "muted small", text: E.VERSION + " · CLI(devdraft)와 같은 판정 규칙" }))));
  }

  /* ---------- editor: one scrolling form. The step list jumps to a section and shows what is still missing ---------- */
  const finePointer = () => matchMedia("(pointer: fine)").matches;
  function openEditor(uid, step, focus) {
    const d = draftOf(uid); if (!d) return;
    S.edit = { uid, step: step || 0, focus: focus || null, checked: false };
    S.navOpen = false; render(); scrollTo(0, 0);
    if (focus) { focusField(focus); return; }
    if (step) { scrollToStep(step); return; }
    // Continue where something is missing: the cursor goes to the first empty required item.
    const first = item(d).errs.flatMap(e => e.targets)[0];
    if (first && finePointer()) focusField(first); else if (first) scrollToStep(E.stepOfTarget(first));
  }
  function closeEditor() { S.edit = null; render(); scrollTo(0, 0); }
  function markStep() {
    const nav = $("#e-steps"); if (!nav) return;
    nav.querySelectorAll(".nav-item").forEach((b, n) => { if (n === S.edit.step) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current"); });
    const cur = nav.querySelector("[aria-current]");
    if (cur && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: cur.offsetLeft - (nav.clientWidth - cur.offsetWidth) / 2 });
  }
  function scrollToStep(n) {
    const el = $("#step-" + E.STEPS[n].id); if (!el) return;
    el.scrollIntoView({ block: "start" }); S.edit.step = n; markStep();
  }
  function focusField(target) {
    if (target.startsWith("step-")) { scrollToStep(E.stepOfTarget(target)); return; }
    const el = document.getElementById(target.startsWith("flag-") ? target : "f-" + target);
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    const t = el.matches("input,select,textarea") ? el : el.querySelector("input");
    if (t) t.focus({ preventScroll: true });
  }
  function goTo(target) { if (closeDrawer) closeDrawer(); focusField(target); }
  // After a preview or export attempt, show which items are missing; the marks clear as they are filled.
  function markInvalid(d) {
    if (!S.edit || !S.edit.checked) return;
    const bad = new Set(item(d).errs.flatMap(e => e.targets));
    E.TEXT_FIELDS.concat(["today"]).forEach(k => { const el = document.getElementById("f-" + k); if (!el) return; if (bad.has(k)) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid"); });
    E.RULES.required_flags.forEach(k => { const el = document.getElementById("flag-" + k); if (el) el.classList.toggle("unanswered", bad.has("flag-" + k)); });
  }
  function edited(d) { touched(d); refreshEditor(); fill($("#step-s7 .sbody"), stepBody(d, 6)); markInvalid(d); }
  function focused(d, key, stepIndex) { S.edit.focus = key; if (S.edit.step !== stepIndex) { S.edit.step = stepIndex; markStep(); } renderAside(d); }
  function field(d, k, opt) {
    opt = opt || {};
    const f = d.form, id = "f-" + k, req = E.RULES.required_fields.includes(k);
    let input;
    const common = { id, onfocus: () => focused(d, k, E.stepOfTarget(k)) };
    if (opt.type === "select") {
      input = h("select", Object.assign({ onchange: e => { f[k] = e.target.value; edited(d); } }, common),
        [["", "선택 안 함"]].concat(E.RULES.categories.map(c => [c, E.CAT_LABEL[c]])).map(([val, text]) => { const o = h("option", { value: val, text }); o.selected = f[k] === val; return o; }));
    } else if (opt.type === "textarea") {
      input = h("textarea", Object.assign({ placeholder: PLACEHOLDER[k], oninput: e => { f[k] = e.target.value; edited(d); } }, common)); input.value = f[k] || "";
    } else {
      input = h("input", Object.assign({ type: opt.type || "text", placeholder: PLACEHOLDER[k] || null, autocomplete: "off", list: opt.list ? "dl-" + k : null,
        oninput: e => { f[k] = e.target.value; if (k === "today") d.autoToday = false; edited(d); } }, common));
      input.value = f[k] || "";
    }
    return h("div", { class: "field" + (opt.wide ? " wide" : "") }, h("label", { for: id }, E.FIELD_LABEL[k], req ? h("span", { class: "req", "aria-hidden": "true", text: "*" }) : null, req ? h("span", { class: "sr", text: "필수" }) : null), input);
  }
  function stepBody(d, n) {
    const f = d.form, s = E.STEPS[n], i = item(d);
    if (s.id === "s1") {
      const c = h("input", { type: "checkbox", id: "f-synthetic", onchange: e => { f.synthetic = e.target.checked; edited(d); }, onfocus: () => focused(d, "synthetic", 0) }); c.checked = !!f.synthetic;
      return [h("div", { class: "fields" }, field(d, "id"), field(d, "category", { type: "select" }), field(d, "title", { wide: true })), h("label", { class: "check" }, c, "연습용(합성) 양식")];
    }
    if (s.id === "s2") return [h("div", { class: "fields" }, field(d, "site", { list: true }), field(d, "area", { list: true }), field(d, "product", { list: true }), field(d, "batch"),
      field(d, "equipment_id", { list: true }), field(d, "process_step", { list: true }))];
    if (s.id === "s3") return [h("div", { class: "fields" }, field(d, "detected_at", { type: "datetime-local" }), field(d, "detected_by", { list: true }))];
    if (s.id === "s4") return [h("div", { class: "fields" }, field(d, "description", { type: "textarea", wide: true }), field(d, "immediate_actions", { type: "textarea", wide: true }))];
    if (s.id === "s5") {
      const box = h("div", { class: "params", id: "f-parameters", onfocusin: () => focused(d, "parameters", 4) });
      const collect = () => { f.parameters = [...box.querySelectorAll(".prow")].map(r => Object.fromEntries([...r.querySelectorAll("input")].map(x => [x.dataset.k, x.value]))).filter(p => Object.values(p).some(v => v.trim())); edited(d); };
      let seq = 0;
      const row = p => {
        const id = seq++;
        const r = h("div", { class: "prow" }, [["name", "항목", "pname"], ["spec", "기준", ""], ["actual", "실측", ""], ["duration", "비고", ""]].map(([k, label, cls]) => {
          const inp = h("input", { type: "text", id: "p-" + id + "-" + k, "data-k": k, autocomplete: "off", oninput: collect }); inp.value = (p && p[k]) || "";
          return h("div", { class: "field " + cls }, h("label", { for: inp.id, text: label }), inp);
        }), h("button", { type: "button", class: "btn icon", "aria-label": "이 측정값 삭제", onclick: () => { r.remove(); collect(); } }, ic("trash-2")));
        box.append(r); return r;
      };
      f.parameters.forEach(row);
      // A copied spreadsheet range fills rows in one paste.
      box.addEventListener("paste", e => {
        const rows = E.parseParamPaste((e.clipboardData || { getData: () => "" }).getData("text/plain"));
        if (!rows.length) return;
        e.preventDefault();
        [...box.querySelectorAll(".prow")].forEach(r => { if ([...r.querySelectorAll("input")].every(x => !x.value.trim())) r.remove(); });
        rows.forEach(row); collect(); toast("측정값 " + rows.length + "행 붙여넣음");
      });
      return [box, h("div", {}, h("button", { type: "button", class: "btn", onclick: () => { const r = row(null); r.querySelector("input").focus(); } }, ic("plus"), "측정값 추가"))];
    }
    if (s.id === "s6") return [h("div", { id: "f-flags" }, E.FLAGS.map(([key, name, q]) => {
      const lvl = E.RULES.levels.find(l => (E.RULES.classes[l.id] || []).some(t => t.field === key && t.equals === true));
      return h("div", { class: "flag", id: "flag-" + key },
        h("div", { class: "q" }, h("span", { text: q }), lvl ? h("span", { class: "chip " + lvl.id, text: lvl.label + " 기준" }) : h("span", { class: "chip none", text: "등급과 별개" })),
        h("div", { class: "yn", role: "radiogroup", "aria-label": name }, [[true, "예"], [false, "아니오"]].map(([val, text]) => {
          const r = h("input", { type: "radio", name: key, id: key + "-" + val, onchange: () => { f.flags[key] = val; edited(d); }, onfocus: () => focused(d, "flag:" + key, 5) });
          r.checked = f.flags[key] === val;
          return h("label", {}, r, h("span", { text: text }));
        })));
    }))];
    if (s.id === "s7") {
      const L = i.look, bad = i.errs.find(e => e.code === "synthetic-history");
      return [
        bad ? h("div", { class: "alert", role: "alert" }, h("b", { text: bad.text }), h("span", { class: "next", text: "다음: 실제 이력 CSV 선택, 또는 01에서 연습용(합성) 표시" })) : null,
        h("dl", { class: "kv", id: "f-recurrence" },
          h("dt", { text: "이력" }), h("dd", { text: i.hist ? i.hist.name + " · " + i.hist.rows.length + "건" + (i.hist.synthetic ? " · 합성" : "") : "없음" }),
          h("dt", { text: "기준" }), h("dd", { text: [f.site || "사업장 미기재", f.equipment_id || "설비 미기재", f.category ? catLabel(f.category) : "유형 미기재"].join(" · ") + " · 최근 " + E.RULES.recurrence.window_days + "일" }),
          h("dt", { text: "결과" }), h("dd", {}, h("b", { text: L.checked ? (L.rec.length ? "반복 건 " + L.rec.length + "건" : "같은 건 없음") : "조회 안 함 · " + L.why }))),
        L.rec.length ? h("div", { class: "tw" }, h("table", {}, h("thead", {}, h("tr", {}, ["번호", "개설일", "등급"].map(t => h("th", { text: t })))),
          h("tbody", {}, L.rec.map(r => h("tr", {}, h("td", { class: "num", text: r.dev_id }), h("td", { class: "num", text: r.opened }), h("td", { text: r.final_class })))))) : null,
        h("div", { class: "row" }, historyInput(), h("button", { type: "button", class: "btn quiet", onclick: () => setView("recurrence") }, "이력 관리"))];
    }
    return [h("div", { class: "fields" }, field(d, "today", { type: "date" }))];
  }
  function renderAside(d) {
    const box = $("#e-aside"); if (!box) return;
    const i = item(d), s = E.STEPS[S.edit.step];
    const key = S.edit.focus || s.fields[0] || { s5: "parameters", s6: "flags", s7: "recurrence" }[s.id];
    let name = E.FIELD_LABEL[key] || { parameters: "측정값", flags: "위험 확인 질문", recurrence: "반복성 조회", synthetic: "연습용(합성) 양식" }[key], help = HELP[key];
    if (key.startsWith("flag:")) {
      const fk = key.slice(5), lvl = E.RULES.levels.find(l => (E.RULES.classes[l.id] || []).some(t => t.field === fk));
      name = E.FLAG_NAME[fk]; help = [lvl ? "'예'이면 " + lvl.label + " 제안 근거" : "등급과 별개 · '예'이면 초안에 신고 검토 항목 표시", HELP.flags[1]];
    }
    if (key === "detected_at" && i.due) help = [help[0], "발견일 + " + S.settings.dueDays + "일 = " + i.due + " · " + help[1]];
    const p = i.prop;
    fill(box,
      h("div", { class: "acard" }, h("h3", { text: "이 칸" }), h("p", { class: "fname", text: name }), h("p", { text: help[0] }), h("p", { class: "muted small", text: "근거 · " + help[1] })),
      h("div", { class: "acard" }, h("h3", { text: "도구 제안 등급" }), h("div", {}, gradeChip(i, " (제안)", true)),
        p ? [h("ul", {}, p.reasons.map(r => h("li", { text: r }))),
          p.lower.length ? h("p", { class: "muted small", text: "그 밖에 해당: " + p.lower.map(x => "[" + E.levelLabel(x[0]) + "] " + x[1]).join(" · ") }) : null]
          : h("p", { class: "muted small", text: "질문 8개 응답 후 표시" })),
      h("div", { class: "acard" }, h("h3", { text: "판단 칸" }), E.JUDGEMENT_FIELDS.map(t => h("div", { class: "jrow" }, h("span", { text: t }), h("span", { class: "chip human", text: "담당자 작성" })))));
  }
  function refreshEditor() {
    const d = draftOf(S.edit.uid), i = item(d), f = d.form;
    const issues = E.stepIssues(f, i.hist);
    fill($("#e-title"), h("b", { text: f.id || "새 초안" }), h("span", { text: f.title || "제목 없음" }));
    fill($("#e-chips"), h("span", { class: "chip", text: E.STATUS_LABEL[i.status] }), f.synthetic ? h("span", { class: "chip info", text: "합성" }) : null,
      h("span", { class: "chip tint", title: "입력과 파일은 이 브라우저 안에서만 처리됨. 외부 전송 없음" }, ic("lock"), "로컬 처리"));
    fill($("#e-steps"), E.STEPS.map((s, n) => h("button", { type: "button", class: "nav-item", "aria-current": n === S.edit.step ? "true" : null, onclick: () => { S.edit.focus = null; scrollToStep(n); renderAside(d); } },
      h("span", { class: "no", text: s.no }), h("span", { class: "t", text: s.name }),
      issues[n] ? h("span", { class: "cnt" }, h("i", { class: "dot", "aria-hidden": "true" }), String(issues[n]), h("span", { class: "sr", text: "개 빠짐" })) : null)));
    fill($("#e-prog"),
      h("span", { class: "txt", text: "필수 " + i.comp.fieldsDone + "/" + E.RULES.required_fields.length + " · 질문 " + i.comp.flagsDone + "/" + E.RULES.required_flags.length }),
      h("div", { class: "bar", role: "img", "aria-label": "완성도 " + i.comp.done + "/" + i.comp.total }, h("i", { style: "width:" + Math.round(100 * i.comp.done / i.comp.total) + "%" })),
      gradeChip(i, null, true));
    renderAside(d);
  }
  function renderEditor() {
    const d = draftOf(S.edit.uid);
    const sug = E.suggestions(S.drafts.filter(x => x.uid !== d.uid).map(x => x.form));
    const saveNow = () => {
      d.savedAt = Date.now(); persistNow(); refreshEditor();
      if (S.settings.persist) toast("저장함");
      else toast("탭에만 보관 · 새로고침하면 사라짐", store.ok ? { label: "브라우저 저장 켜기", run: () => { S.settings.persist = true; persistNow(); if (S.settings.persist) toast("브라우저 저장 켬"); } } : null);
    };
    fill($("#editor"),
      h("header", { class: "etop" },
        h("button", { type: "button", class: "btn icon quiet", "aria-label": "목록으로", onclick: closeEditor }, ic("arrow-left")),
        h("div", { class: "ttl", id: "e-title" }),
        h("div", { class: "right" }, h("span", { id: "e-chips", class: "chips" }),
          h("button", { type: "button", class: "btn icon", "aria-label": "초안 메뉴", "aria-haspopup": "menu", onclick: e => draftMenu(e.currentTarget, d.uid) }, ic("ellipsis")))),
      h("div", { class: "ebody" },
        h("nav", { class: "steps", id: "e-steps", "aria-label": "입력 단계" }),
        h("div", { class: "eform", id: "e-form" },
          E.SUGGEST_FIELDS.map(k => h("datalist", { id: "dl-" + k }, sug[k].map(v => h("option", { value: v })))),
          E.STEPS.map((s, n) => h("section", { class: "estep", id: "step-" + s.id, "aria-labelledby": "h-" + s.id },
            h("h2", { id: "h-" + s.id }, h("span", { class: "no", text: s.no }), s.name), h("div", { class: "sbody" }, stepBody(d, n))))),
        h("aside", { class: "aside", id: "e-aside", "aria-label": "근거와 제안" })),
      h("div", { class: "ebar" },
        h("div", { class: "prog", id: "e-prog" }),
        h("div", { class: "acts" },
          h("button", { type: "button", class: "btn", "aria-label": "임시 저장", onclick: saveNow }, ic("save"), h("span", { class: "lbl", text: "임시 저장" })),
          h("button", { type: "button", class: "btn", "aria-label": "미리보기", onclick: () => openPreview(d.uid) }, ic("eye"), h("span", { class: "lbl", text: "미리보기" })),
          h("button", { type: "button", class: "btn primary", "aria-label": "내보내기", "aria-haspopup": "menu", onclick: e => exportMenu(e.currentTarget, d.uid) }, ic("download"), h("span", { class: "lbl", text: "내보내기" })))));
    refreshEditor(); markInvalid(d);
  }
  // The step list follows the scroll position.
  let spyQueued = false;
  addEventListener("scroll", () => {
    if (!S.edit || spyQueued) return;
    spyQueued = true;
    requestAnimationFrame(() => {
      spyQueued = false;
      if (!S.edit) return;
      let cur = 0;
      E.STEPS.forEach((s, n) => { const el = $("#step-" + s.id); if (el && el.getBoundingClientRect().top <= 150) cur = n; });
      if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) cur = E.STEPS.length - 1;
      if (cur === S.edit.step) return;
      S.edit.step = cur; markStep();
      if (!document.activeElement || !document.activeElement.matches("input,select,textarea")) { S.edit.focus = null; renderAside(draftOf(S.edit.uid)); }
    });
  }, { passive: true });

  /* ---------- preview ---------- */
  function runs(rs, el) {
    rs.forEach(r => { el.append(r.blank ? h("span", { class: "blank", text: r.t }) : r.b ? h("strong", { text: r.t }) : r.t); });
    return el;
  }
  function docView(m) {
    const body = h("div", { class: "body" });
    m.blocks.forEach(b => {
      if (b.k === "h1" || b.k === "h2" || b.k === "h3") body.append(runs(b.runs, h(b.k)));
      else if (b.k === "p") body.append(runs(b.runs, h("p")));
      else if (b.k === "pre") body.append(runs(b.runs, h("p", { class: "pre" })));
      else if (b.k === "ul") body.append(h("ul", {}, b.items.map(it => runs(it, h("li")))));
      else if (b.k === "banner") body.append(h("div", { class: "banner" }, b.lines.map(l => runs(l, h("div")))));
      else if (b.k === "table") body.append(h("div", { class: "tw" }, h("table", {}, h("thead", {}, h("tr", {}, b.head.map(t => h("th", { text: t })))),
        h("tbody", {}, b.rows.map(r => h("tr", {}, r.map(c => runs(c, h("td")))))))));
    });
    return h("article", { class: "doc" },
      h("div", { class: "band" }, [m.synthetic ? "합성 데이터 — 실제 문서 아님" : null, "초안 — 승인 문서 아님", m.id, "초안 생성일 " + m.today].filter(Boolean).map(t => h("span", { text: t }))), body);
  }
  async function openPreview(uid) {
    const d = draftOf(uid), i = item(d);
    if (i.errs.length) {
      if (S.edit) { S.edit.checked = true; markInvalid(d); }
      const label = t => t.startsWith("flag-") ? E.FLAG_NAME[t.slice(5)] : t === "step-s7" ? "반복성 조회" : E.FIELD_LABEL[t];
      openDrawer("미리보기", null, [
        h("div", { class: "alert", role: "alert" }, h("b", { text: "초안 안 만듦 · " + blockedText(i.errs) }), h("span", { class: "next", text: "다음: 아래 항목을 눌러 " + (E.blockCount(i.errs).missingOnly ? "채우기" : "고치기") })),
        i.errs.map(e => h("section", { class: "panel" }, h("p", { text: e.text }),
          h("div", { class: "row" }, e.targets.map(t => h("button", { type: "button", class: "btn sm", onclick: () => { if (!S.edit) openEditor(uid, E.stepOfTarget(t), t); else goTo(t); } }, label(t), ic("arrow-right"))))))]);
      return;
    }
    const m = await E.buildModel(d.form, i.hist);
    const exp = h("button", { type: "button", class: "btn primary", "aria-haspopup": "menu", onclick: e => exportMenu(e.currentTarget, uid) }, ic("download"), "내보내기");
    openDrawer("미리보기", exp, [
      h("div", { class: "sumline" }, gradeChip(i, " (제안)"), h("span", { text: "판단 칸 " + m.blanks + "곳 비움" }), h("span", { class: "chip human", text: "담당자 작성" }),
        h("span", { text: i.look.checked ? "반복 건 " + i.look.rec.length + "건" : "반복성 조회 안 함" }), i.due ? h("span", { text: "보고 기한 " + i.due }) : null),
      docView(m)]);
  }

  /* ---------- render ---------- */
  function render() {
    if (closeMenu) closeMenu();
    const list = items();
    renderSide(list);
    const editing = !!(S.edit && draftOf(S.edit.uid));
    if (!editing) S.edit = null;
    $("#shell").hidden = editing; $("#editor").hidden = !editing;
    $("#shell").classList.toggle("nav-open", S.navOpen);
    const dim = $("#navDim");
    if (S.navOpen && !dim) $("#layer").append(h("div", { class: "dim", id: "navDim", onclick: () => { S.navOpen = false; render(); } }));
    if (!S.navOpen && dim) dim.remove();
    applyTheme();
    $("#toast").classList.toggle("up", editing);
    if (editing) { renderEditor(); return; }
    ({ drafts: viewHome, recurrence: viewRecurrence, export: viewExport, guide: viewGuide })[S.ui.view](list);
  }

  /* ---------- wiring ---------- */
  $("#q").addEventListener("input", e => { S.query = e.target.value; S.ui.view = "drafts"; S.hero = 0; viewHome(items()); renderSide(items()); });
  $("#menuBtn").addEventListener("click", () => { S.navOpen = !S.navOpen; render(); });
  $("#moreBtn").addEventListener("click", e => moreMenu(e.currentTarget));
  $("#yamlFile").addEventListener("change", e => { const files = [...e.target.files]; e.target.value = ""; if (files.length) importYAML(files); });
  document.querySelectorAll("[data-theme-pick]").forEach(b => b.addEventListener("click", () => { S.ui.theme = b.dataset.themePick; saveUI(); applyTheme(); }));
  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || ""));
    if (e.key === "/" && !typing && !S.edit && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); $("#q").focus(); return; }
    if (e.key !== "Escape") return;
    if (closeMenu) closeMenu(); else if (closeDrawer) closeDrawer(); else if (S.navOpen) { S.navOpen = false; render(); }
    else if (typing) e.target.blur();
    else if (S.edit) closeEditor();
  });
  window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (VIEWS.includes(v) && (v !== S.ui.view || S.edit)) setView(v); });
  window.addEventListener("pagehide", persistNow);
  if (window.claude && typeof window.claude.use === "function") {
    window.claude.use("downloads").then(dl => { downloads = dl; if (!S.edit) render(); }, () => { downloads = null; });
  }
  window.__desk = { S, E, render, items, openEditor, loadExamples, createDraft, exportDraft, openPreview };
  (async () => {
    await loadState();
    const v = location.hash.slice(1); if (VIEWS.includes(v)) S.ui.view = v;
    render();
    if (S.dropped) toast("저장된 초안 " + S.dropped + "건은 형식이 달라 불러오지 않음");
  })();
})();
