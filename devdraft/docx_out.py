"""Write the draft to a Word file QA can edit and track changes in.

What matters in Word is that a reviewer cannot mistake the draft for a
finished document and cannot overlook a blank that still needs writing:

- every page carries a "draft — not an approved document" header;
- every "작성 필요" blank keeps its ☐ and is bold + highlighted;
- the warning banner is a shaded box, not body text;
- table header rows repeat on each page.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

FONT = "Arial"
FONT_KO = "Malgun Gothic"  # Arial has no Hangul; Word would otherwise substitute per machine
BLANK = "작성 필요"

# **bold**, `code`, *italic* — in that order of precedence
_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*))")


def _set_fonts(style_or_run_font, size: int | None = None) -> None:
    f = style_or_run_font
    f.name = FONT
    if size:
        f.size = Pt(size)
    rpr = f.element.get_or_add_rPr() if hasattr(f, "element") else None
    if rpr is not None:
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.append(fonts)
        fonts.set(qn("w:eastAsia"), FONT_KO)


def _style(doc: Document) -> None:
    for name, size in (("Normal", 10), ("Heading 1", 15), ("Heading 2", 12), ("Heading 3", 11), ("List Bullet", 10)):
        st = doc.styles[name]
        st.font.name = FONT
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor(0, 0, 0)
        rpr = st.element.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.append(fonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            fonts.set(qn(attr), FONT)
        fonts.set(qn("w:eastAsia"), FONT_KO)
        # The heading styles of the default template also name the theme fonts, and Word follows
        # those over the names above: headings came out in Calibri. Remove them.
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            fonts.attrib.pop(qn(attr), None)


def _mark_blank(run) -> None:
    run.bold = True
    run.font.highlight_color = WD_COLOR_INDEX.YELLOW


# "☐ **작성 필요**" (draft.TBD) and a bare "☐" are kept as one highlighted unit
_BLANK_TOKEN = re.compile(rf"(☐ ?(?:\*\*)?{BLANK}(?:\*\*)?|☐)")


def _add_inline(par, text: str, bold: bool = False, italic: bool = False) -> None:
    """Add text to a paragraph, turning Markdown emphasis into Word runs."""
    for chunk in _BLANK_TOKEN.split(text):
        if not chunk:
            continue
        if _BLANK_TOKEN.fullmatch(chunk):
            run = par.add_run(chunk.replace("**", ""))
            run.italic = italic or None
            _mark_blank(run)
            continue
        for part in _INLINE.split(chunk):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                _add_inline(par, part[2:-2], bold=True, italic=italic)
            elif part.startswith("*") and part.endswith("*") and len(part) > 2 and not part.startswith("**"):
                _add_inline(par, part[1:-1], bold=bold, italic=True)
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                run = par.add_run(part[1:-1])
                run.bold, run.italic = bold or None, italic or None
            else:
                run = par.add_run(part)
                run.bold, run.italic = bold or None, italic or None


def _shade(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def _repeat_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    h = OxmlElement("w:tblHeader")
    h.set(qn("w:val"), "true")
    trpr.append(h)


def _field(par, instr: str) -> None:
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "1"), ("end", None)):
        run = par.add_run()
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        elif text == instr:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        else:
            el = OxmlElement("w:t")
            el.text = text
        run._r.append(el)


def _header_footer(doc: Document, dev_id: str, generated: str, synthetic: bool = False) -> None:
    sec = doc.sections[0]
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if synthetic:
        s = hp.add_run("합성 데이터 — 실제 문서 아님  ·  ")
        s.bold = True
        s.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    r = hp.add_run("초안 — 승인 문서 아님")
    r.bold = True
    r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    hp.add_run(f"  ·  {dev_id}  ·  생성일 {generated}").font.size = Pt(8)
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.add_run("자동 생성 초안 — 검토·승인은 검증된 QMS에서  ·  ").font.size = Pt(8)
    _field(fp, "PAGE")
    fp.add_run(" / ")
    _field(fp, "NUMPAGES")


def _table(doc: Document, rows: list[list[str]]) -> None:
    width = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=width)
    t.style = "Table Grid"
    for n, r in enumerate(rows):
        row = t.add_row()
        if n == 0:
            _repeat_header(row)
        for c, val in enumerate(r + [""] * (width - len(r))):
            cell = row.cells[c]
            par = cell.paragraphs[0]
            _add_inline(par, val, bold=(n == 0))
            if n == 0:
                _shade(cell, "D9D9D9")
    doc.add_paragraph()


def _banner(doc: Document, lines: list[str]) -> None:
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    _shade(cell, "FFF2CC")
    par = cell.paragraphs[0]
    for k, line in enumerate(lines):
        if k:
            par = cell.add_paragraph()
        _add_inline(par, line.rstrip("\\ ").rstrip())
    doc.add_paragraph()


# Both the draft banner and the summary banner start with this phrase.
SYNTHETIC_PHRASE = "합성(가짜) 데이터로 만든 초안"

# Backslash escapes (devdraft.mdtext) mark entered text that must be shown
# as typed. They are swapped for private-use characters before parsing, so
# "\|" can't split a table cell and "\#" can't start a heading, then swapped
# back to the real character in the finished document.
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_PLACEHOLDER = 0xE000
_RESTORE = {_PLACEHOLDER + c: chr(c) for c in range(0x21, 0x7F)}


def _protect(md: str) -> str:
    return _ESCAPED.sub(lambda m: chr(_PLACEHOLDER + ord(m.group(1))), md)


def _restore(doc: Document) -> None:
    def fix(paragraphs):
        for p in paragraphs:
            for run in p.runs:
                if any(_PLACEHOLDER <= ord(ch) < _PLACEHOLDER + 0x80 for ch in run.text):
                    run.text = run.text.translate(_RESTORE)
    fix(doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                fix(cell.paragraphs)
    for sec in doc.sections:
        fix(sec.header.paragraphs)
        fix(sec.footer.paragraphs)


def markdown_to_docx(md: str, out_path: str | Path, *, label: str | None = None,
                     generated: str | None = None, landscape: bool = False) -> Path:
    """Convert a draft (or, with `label`, any other report such as the batch
    summary) to Word. `label` and `generated` go into every page header; for a
    draft they are read from the Markdown (deviation number, 초안 생성일)."""
    md = _protect(md)
    doc = Document()
    _style(doc)
    if landscape:  # wide tables (batch summary) need the width
        sec = doc.sections[0]
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
    if label is None:
        title = re.search(r"^# .*?(\S+)\s*$", md, flags=re.M)
        label = title.group(1) if title else ""
    if generated is None:
        gen = re.search(r"\| 초안 생성일 \| ([^|]+) \|", md)
        generated = gen.group(1).strip() if gen else ""
    _header_footer(doc, label, generated, synthetic=SYNTHETIC_PHRASE in md)

    lines = md.splitlines()
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            p = doc.add_paragraph()
            for k, chunk in enumerate(para):
                if k:
                    p.add_run().add_break()
                _add_inline(p, chunk.rstrip())
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                i += 1
            _table(doc, rows)
            continue
        if line.startswith("> "):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith("> "):
                quote.append(lines[i][2:])
                i += 1
            _banner(doc, quote)
            continue
        if line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            doc.add_heading(line.lstrip("# ").strip(), level=min(level, 4))
        elif line.startswith("- "):
            flush()
            _add_inline(doc.add_paragraph(style="List Bullet"), line[2:])
        elif not line.strip() or line.startswith("---"):
            flush()
        else:
            # Markdown: consecutive lines form one paragraph; a trailing
            # double space is a hard line break.
            if para and not para[-1].endswith("  "):
                para[-1] = para[-1].rstrip() + " " + line.strip()
            else:
                para.append(line)
        i += 1
    flush()
    _restore(doc)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out
