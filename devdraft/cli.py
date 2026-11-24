"""python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

from .classify import find_recurrence, investigation_plan, load_history, propose_class
from .draft import render_markdown
from .intake import IntakeError, load

ROOT = Path(__file__).resolve().parents[1]


def build(form: Path, rules_path: Path, history_path: Path, out_dir: Path,
          today: date | None = None, want_docx: bool = False) -> Path:
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    dev = load(form, rules)
    history = load_history(history_path)
    rec = find_recurrence(dev, history, rules, today)
    level, reasons = propose_class(dev, rules, len(rec))
    plan = investigation_plan(dev, rules)
    md = render_markdown(dev, level, reasons, rec, plan,
                         generated_on=(today or date.today()).isoformat())
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{dev.id}_draft.md"
    md_path.write_text(md, encoding="utf-8")
    if want_docx:
        from .docx_out import markdown_to_docx
        markdown_to_docx(md, out_dir / f"{dev.id}_draft.docx")
    return md_path


def main() -> None:
    ap = argparse.ArgumentParser(description="GMP deviation report drafting assistant (draft only)")
    ap.add_argument("form", type=Path, nargs="+", help="intake YAML file(s)")
    ap.add_argument("--rules", type=Path, default=ROOT / "config/rules.yaml")
    ap.add_argument("--history", type=Path, default=ROOT / "data/synthetic/history.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "drafts")
    ap.add_argument("--docx", action="store_true", help="also write a Word file")
    ap.add_argument("--today", help="YYYY-MM-DD, for reproducible output")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else None
    for f in args.form:
        try:
            p = build(f, args.rules, args.history, args.out, today, args.docx)
            print(f"OK  {f.name} -> {p}")
        except IntakeError as e:
            print(f"ERR {f.name}: {e}")


if __name__ == "__main__":
    main()
