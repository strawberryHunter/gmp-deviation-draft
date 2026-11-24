"""Write the draft to a Word file QA can edit and track changes in."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor


def _style(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)


def markdown_to_docx(md: str, out_path: str | Path) -> Path:
    doc = Document()
    _style(doc)
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            rows, i = [], i
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                i += 1
            width = max(len(r) for r in rows)
            t = doc.add_table(rows=0, cols=width)
            t.style = "Table Grid"
            for n, r in enumerate(rows):
                cells = t.add_row().cells
                for c, val in enumerate(r + [""] * (width - len(r))):
                    cells[c].text = re.sub(r"\*\*|☐ ", "", val)
                    if n == 0:
                        for p in cells[c].paragraphs:
                            for run in p.runs:
                                run.bold = True
            doc.add_paragraph()
            continue
        if line.startswith("> "):
            p = doc.add_paragraph(re.sub(r"\*\*|\\$", "", line[2:]).strip())
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            doc.add_heading(line.lstrip("# ").strip(), level=min(level, 4))
        elif line.startswith("- "):
            doc.add_paragraph(re.sub(r"\*\*", "", line[2:]), style="List Bullet")
        elif line.strip() and not line.startswith("---"):
            doc.add_paragraph(re.sub(r"\*\*|☐ ", "", line))
        i += 1
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out
