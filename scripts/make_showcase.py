"""Build the portfolio showcase: drafts, Word -> PDF, page images.

    python scripts/make_showcase.py

Inputs:  data/synthetic/showcase/*.yaml (synthetic, realistic cases)
Outputs: sample_output/showcase/
           <id>_draft.md        what the tool writes (Markdown)
           <id>_draft.pdf       the Word draft rendered to PDF
           <id>_p<N>.png        page images for the README (no install needed)
           _summary_<date>.md   batch summary (+ .pdf, _p<N>.png)

Needs LibreOffice (soffice) and poppler (pdftoppm) for the PDF/PNG step.
The .docx files are not kept (*.docx is gitignored on purpose).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/synthetic/showcase"
OUT = ROOT / "sample_output/showcase"
TODAY = "2026-11-24"
DPI = "60"


def main() -> None:
    for tool in ("soffice", "pdftoppm"):
        if not shutil.which(tool):
            sys.exit(f"{tool} 가 필요합니다 (LibreOffice / poppler-utils).")
    forms = sorted(SRC.glob("*.yaml"))
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        old.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run([sys.executable, "-m", "devdraft.cli", *map(str, forms), "--docx", "--summary",
                        "--today", TODAY, "--out", str(tmp)], cwd=ROOT, check=True)
        for md in tmp.glob("*.md"):
            shutil.copy(md, OUT / md.name)
        for docx in sorted(tmp.glob("*.docx")):  # drafts + batch summary
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(OUT), str(docx)],
                           check=True, capture_output=True, timeout=180)
            pdf = OUT / docx.with_suffix(".pdf").name
            stem = docx.name.removesuffix(".docx").removesuffix("_draft")
            subprocess.run(["pdftoppm", "-r", DPI, "-png", str(pdf), str(OUT / f"{stem}_p")], check=True)
    for png in sorted(OUT.glob("*.png")):  # pdftoppm names pages -1.png / -01.png; normalize
        stem, page = png.stem.rsplit("-", 1)
        png.rename(OUT / f"{stem}{int(page)}.png")
    print("\n".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
