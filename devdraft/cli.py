"""python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


from .classify import find_recurrence, investigation_plan, load_history, lower_triggers, propose_class
from .draft import render_markdown
from .intake import IntakeError, check_rules, load
from .rules import RulesError, load_rules
from .summary import FormResult, render_summary

ROOT = Path(__file__).resolve().parents[1]

# 0: every form drafted. 1: at least one form rejected (others still drafted).
# 2: rules.yaml invalid, nothing drafted.
EXIT_REJECTED = 1
EXIT_RULES_ERROR = 2


def draft_one(form: Path, rules: dict, history: list[dict], out_dir: Path,
              today: date | None = None, want_docx: bool = False,
              seen_ids: set[str] | None = None) -> FormResult:
    """Draft one form. Raises IntakeError if the form is rejected."""
    dev = load(form, rules)
    if seen_ids is not None:
        if dev.id in seen_ids:
            raise IntakeError(f"같은 일탈 번호({dev.id})의 양식이 이번 실행에 이미 있습니다 — 덮어쓰지 않습니다.")
        seen_ids.add(dev.id)
    rec = find_recurrence(dev, history, rules, today)
    level, reasons = propose_class(dev, rules, len(rec))
    plan = investigation_plan(dev, rules)
    md = render_markdown(dev, level, reasons, rec, plan,
                         generated_on=(today or date.today()).isoformat(),
                         rules=rules, also=lower_triggers(dev, rules, len(rec)))
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{dev.id}_draft.md"
    md_path.write_text(md, encoding="utf-8")
    if want_docx:
        from .docx_out import markdown_to_docx
        markdown_to_docx(md, out_dir / f"{dev.id}_draft.docx")
    return FormResult(file=form.name, ok=True, dev_id=dev.id, title=dev.title,
                      proposed=level, reasons=reasons, recurrence_count=len(rec),
                      draft=str(md_path))


def build(form: Path, rules_path: Path, history_path: Path, out_dir: Path,
          today: date | None = None, want_docx: bool = False) -> Path:
    rules = load_rules(rules_path)
    check_rules(rules)
    history = load_history(history_path)
    return Path(draft_one(form, rules, history, out_dir, today, want_docx).draft)


def run_batch(forms: list[Path], rules_path: Path, history_path: Path, out_dir: Path,
              today: date | None = None, want_docx: bool = False,
              want_summary: bool = False) -> tuple[list[FormResult], Path | None]:
    rules = load_rules(rules_path)
    check_rules(rules)
    history = load_history(history_path)
    results, seen = [], set()
    for f in forms:
        try:
            r = draft_one(f, rules, history, out_dir, today, want_docx, seen)
            print(f"OK  {f.name} -> {r.draft}")
        except IntakeError as e:
            r = FormResult(file=f.name, ok=False, error=str(e))
            print(f"ERR {f.name}: {e}")
        results.append(r)
    summary_path = None
    if want_summary:
        stamp = (today or date.today()).isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        summary_path = out_dir / f"_summary_{stamp}.md"
        summary_path.write_text(render_summary(results, stamp, rules["recurrence"]["window_days"], rules), encoding="utf-8")
        print(f"SUM {summary_path}")
    return results, summary_path


def main() -> None:
    ap = argparse.ArgumentParser(description="GMP deviation report drafting assistant (draft only)")
    ap.add_argument("form", type=Path, nargs="+", help="intake YAML file(s)")
    ap.add_argument("--rules", type=Path, default=ROOT / "config/rules.yaml")
    ap.add_argument("--history", type=Path, default=ROOT / "data/synthetic/history.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "drafts")
    ap.add_argument("--docx", action="store_true", help="also write a Word file")
    ap.add_argument("--summary", action="store_true",
                    help="write _summary_<date>.md listing every form: proposed class or rejection reason")
    ap.add_argument("--today", help="YYYY-MM-DD, for reproducible output")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else None
    try:
        results, _ = run_batch(args.form, args.rules, args.history, args.out, today, args.docx, args.summary)
    except RulesError as e:
        print(f"RULES ERR {args.rules}: {e}")
        raise SystemExit(EXIT_RULES_ERROR)
    if any(not r.ok for r in results):
        raise SystemExit(EXIT_REJECTED)


if __name__ == "__main__":
    main()
