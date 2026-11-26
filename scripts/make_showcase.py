"""Build the portfolio showcase: drafts, Word -> PDF, page images.

    python scripts/make_showcase.py            LibreOffice draws the Word files (any OS)
    python scripts/make_showcase.py --word     Microsoft Word draws them (macOS): the fonts and page
                                               breaks a reviewer sees. The committed files are made this way.

Inputs:  data/synthetic/showcase/*.yaml (synthetic, realistic cases)
Outputs: sample_output/showcase/
           <id>_draft.md        what the tool writes (Markdown)
           <id>_draft.pdf       the Word draft rendered to PDF
           <id>_p<N>.png        page images for the README (no install needed)
           _summary_<date>.md   batch summary (+ .pdf, _p<N>.png)

Needs LibreOffice (soffice), or Microsoft Word with --word, for the PDF step.
Needs poppler (pdftoppm) or PyMuPDF (pip install pymupdf) for the PNG step.
The .docx files are not kept (*.docx is gitignored on purpose).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/synthetic/showcase"
OUT = ROOT / "sample_output/showcase"
TODAY = "2026-11-24"
DPI = 60

# Word may only read and write inside its own container, so the files pass through a folder there.
WORD_BOX = Path.home() / "Library/Group Containers/UBF8T346G9.Office"
WORD_SCRIPT = """
on run argv
  with timeout of 120 seconds
    tell application "Microsoft Word"
      open file name (item 1 of argv)
      set d to active document
      save as d file name (item 2 of argv) file format format PDF
      close d saving no
    end tell
  end timeout
end run
"""


def page_image_name(stem: str, page: int) -> str:
    """DEV-2026-2301_draft, 1 -> DEV-2026-2301_p1.png; _summary_2026-11-24, 2 -> _summary_2026-11-24_p2.png"""
    return f"{stem.removesuffix('_draft')}_p{page}.png"


def soffice_to_pdf(docx_files: list[Path], out: Path) -> None:
    if not shutil.which("soffice"):
        sys.exit("soffice 가 필요합니다 (LibreOffice). macOS에서 Microsoft Word로 그리려면 --word")
    for docx in docx_files:
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out), str(docx)],
                       check=True, capture_output=True, timeout=180)


def word_to_pdf(docx_files: list[Path], out: Path) -> None:
    """Microsoft Word on macOS saves each file as PDF. Word is opened in the background and is not brought
    to the front; a Word this function started is quit at the end, one that was already running is left alone."""
    if sys.platform != "darwin" or not WORD_BOX.is_dir():
        sys.exit("--word 는 Microsoft Word가 설치된 macOS에서만 됩니다.")
    running = subprocess.run(["pgrep", "-xq", "Microsoft Word"]).returncode == 0
    box = Path(tempfile.mkdtemp(prefix="showcase-", dir=WORD_BOX))
    try:
        if not running:
            subprocess.run(["open", "-g", "-j", "-a", "Microsoft Word"], check=True)
            time.sleep(6)  # Word answers Apple events a few seconds after it starts
        for docx in docx_files:
            shutil.copy(docx, box / docx.name)
            pdf = box / docx.with_suffix(".pdf").name
            done = subprocess.run(["osascript", "-", str(box / docx.name), str(pdf)], input=WORD_SCRIPT,
                                  text=True, capture_output=True, timeout=180)
            if done.returncode != 0 or not pdf.is_file():
                sys.exit(f"Word가 {docx.name} 을 PDF로 저장하지 못했습니다: {done.stderr.strip()}")
            shutil.copy(pdf, out / pdf.name)
    finally:
        if not running:
            subprocess.run(["osascript", "-e", 'tell application "Microsoft Word" to quit saving no'],
                           capture_output=True)
        shutil.rmtree(box, ignore_errors=True)


def pdf_to_pngs(pdf: Path, out: Path) -> None:
    stem = pdf.stem
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(Path(tmp) / "p")], check=True)
            for png in sorted(Path(tmp).glob("p-*.png")):  # pdftoppm names pages p-1.png or p-01.png
                shutil.copy(png, out / page_image_name(stem, int(png.stem.rsplit("-", 1)[1])))
        return
    try:
        import pymupdf
    except ImportError:
        sys.exit("pdftoppm (poppler) 또는 PyMuPDF (pip install pymupdf) 가 필요합니다.")
    with pymupdf.open(str(pdf)) as doc:
        for n, page in enumerate(doc, 1):
            page.get_pixmap(dpi=DPI).save(str(out / page_image_name(stem, n)))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="포트폴리오 미리보기(sample_output/showcase) 다시 만들기")
    ap.add_argument("--word", action="store_true", help="LibreOffice 대신 Microsoft Word로 PDF 저장 (macOS)")
    args = ap.parse_args(argv)
    forms = sorted(SRC.glob("*.yaml"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        made = tmp / "made"  # everything is made here first: a failed run leaves the committed files as they were
        made.mkdir()
        subprocess.run([sys.executable, "-m", "devdraft.cli", *map(str, forms), "--docx", "--summary",
                        "--today", TODAY, "--out", str(tmp)], cwd=ROOT, check=True)
        for md in tmp.glob("*.md"):
            shutil.copy(md, made / md.name)
        (word_to_pdf if args.word else soffice_to_pdf)(sorted(tmp.glob("*.docx")), made)  # drafts + batch summary
        for pdf in sorted(made.glob("*.pdf")):
            pdf_to_pngs(pdf, made)
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("*"):
            old.unlink()
        for f in made.iterdir():
            shutil.copy(f, OUT / f.name)
    print("\n".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
