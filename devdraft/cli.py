"""python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx"""
from __future__ import annotations

import argparse
import glob
import hashlib
import sys
from datetime import date
from pathlib import Path

from .classify import find_recurrence, investigation_plan, lower_triggers, propose_class
from .draft import render_markdown
from . import __version__
from .history import HistoryError, check_history, is_synthetic, load_checked_history, render_report
from .intake import IntakeError, check_rules, detected_datetime, load
from .rules import RulesError, load_rules
from .summary import FormResult, render_summary

ROOT = Path(__file__).resolve().parents[1]

# 0: every form drafted (or --check-history found no errors).
# 1: at least one form rejected, others still drafted (or history has errors in --check-history).
# 2: rules.yaml or history file unusable, nothing drafted.
EXIT_REJECTED = 1
EXIT_CONFIG_ERROR = 2
EXIT_RULES_ERROR = EXIT_CONFIG_ERROR  # kept for callers of the earlier name


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_sources(rules: dict, rules_path: Path, history: list[dict], history_path: Path,
                today: date | None) -> dict:
    """Run-level provenance shared by every draft of one run."""
    return {
        "rules": Path(rules_path).name, "rules_sha": _sha256(rules_path),
        "sop": rules.get("sop_reference") or "",
        "history": Path(history_path).name, "history_sha": _sha256(history_path),
        "history_rows": len(history), "history_synthetic": is_synthetic(history),
        "today": (today or date.today()).isoformat(), "version": __version__,
    }


def draft_one(form: Path, rules: dict, history: list[dict], out_dir: Path,
              today: date | None = None, want_docx: bool = False,
              seen_ids: set[str] | None = None, sources: dict | None = None) -> FormResult:
    """Draft one form. Raises IntakeError if the form is rejected."""
    dev = load(form, rules)
    when = detected_datetime(dev.detected_at)
    if when and when.date() > (today or date.today()):
        raise IntakeError(
            f"발견 일시 {dev.detected_at} 가 기준일({(today or date.today()).isoformat()})보다 미래입니다 — "
            "날짜를 확인하십시오 (재현용으로 --today 를 쓰는 경우 그 날짜 이후는 받지 않습니다)."
        )
    if not dev.synthetic and is_synthetic(history):
        raise IntakeError(
            "반복성 조회 이력이 합성(가짜) 데이터입니다 — 실제 양식에 가짜 반복 건이 붙습니다. "
            "--history 로 실제 이력 CSV를 지정하십시오. (연습용 양식이면 양식에 synthetic: true)"
        )
    if seen_ids is not None:
        if dev.id in seen_ids:
            raise IntakeError(f"같은 deviation 번호({dev.id})의 양식이 이번 실행에 이미 있습니다 — 덮어쓰지 않습니다.")
        seen_ids.add(dev.id)
    rec = find_recurrence(dev, history, rules, today)
    level, reasons = propose_class(dev, rules, len(rec))
    plan = investigation_plan(dev, rules)
    md = render_markdown(dev, level, reasons, rec, plan,
                         generated_on=(today or date.today()).isoformat(),
                         rules=rules, also=lower_triggers(dev, rules, len(rec)),
                         self_in_history=any((h.get("dev_id") or "").strip() == dev.id for h in history),
                         sources={**(sources or {}), "form": form.name, "form_sha": _sha256(form)} if sources else None)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{dev.id}_draft.md"
    md_path.write_text(md, encoding="utf-8")
    if want_docx:
        from .docx_out import markdown_to_docx
        markdown_to_docx(md, out_dir / f"{dev.id}_draft.docx")
    return FormResult(file=form.name, ok=True, dev_id=dev.id, title=dev.title,
                      proposed=level, reasons=reasons, recurrence_count=len(rec),
                      draft=str(md_path), synthetic=dev.synthetic)


def _history(history_path: Path, rules: dict, today: date | None, quiet: bool = True) -> list[dict]:
    rep = load_checked_history(history_path, rules, today)
    if rep.warnings and not quiet:
        print(f"HISTORY WARN {history_path.name}: 경고 {len(rep.warnings)}건 — "
              f"--check-history 로 상세 확인 (초안은 계속 생성)")
    return rep.rows


def build(form: Path, rules_path: Path, history_path: Path, out_dir: Path,
          today: date | None = None, want_docx: bool = False) -> Path:
    rules = load_rules(rules_path)
    check_rules(rules)
    history = _history(history_path, rules, today)
    src = run_sources(rules, rules_path, history, history_path, today)
    return Path(draft_one(form, rules, history, out_dir, today, want_docx, sources=src).draft)


def run_batch(forms: list[Path], rules_path: Path, history_path: Path, out_dir: Path,
              today: date | None = None, want_docx: bool = False,
              want_summary: bool = False, want_xlsx: bool = False) -> tuple[list[FormResult], Path | None]:
    rules = load_rules(rules_path)
    check_rules(rules)
    history = _history(history_path, rules, today, quiet=False)
    src = run_sources(rules, rules_path, history, history_path, today)
    results, seen = [], set()
    for f in forms:
        try:
            r = draft_one(f, rules, history, out_dir, today, want_docx, seen, src)
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
        summary_md = render_summary(results, stamp, rules["recurrence"]["window_days"], rules)
        summary_path.write_text(summary_md, encoding="utf-8")
        print(f"SUM {summary_path}")
        if want_docx:
            from .docx_out import markdown_to_docx
            markdown_to_docx(summary_md, summary_path.with_suffix(".docx"),
                             label="일괄 처리 요약", generated=stamp, landscape=True)
        if want_xlsx:
            from .summary_xlsx import write_summary_xlsx
            write_summary_xlsx(results, stamp, rules["recurrence"]["window_days"], rules,
                               summary_path.with_suffix(".xlsx"))
    return results, summary_path


def expand_forms(forms: list[Path], ap: argparse.ArgumentParser | None = None) -> list[Path]:
    """Expand wildcards the shell left alone.

    bash expands `drafts/*.yaml` before Python sees it; Windows cmd and
    PowerShell pass the `*` through, so the run used to crash with
    FileNotFoundError. A pattern that matches nothing is a usage error.
    """
    out: list[Path] = []
    for f in forms:
        s = str(f)
        if not f.exists() and any(ch in s for ch in "*?["):
            hits = sorted(glob.glob(s))
            if not hits:
                msg = f"일치하는 양식 파일이 없습니다: {s}"
                if ap:
                    ap.error(msg)
                raise ValueError(msg)
            out.extend(Path(h) for h in hits)
        else:
            out.append(f)
    return out


def _hangul_safe_output() -> None:
    """Keep Korean messages from crashing the CLI on a non-Korean console.

    On English Windows a pipe or redirect uses cp1252, which cannot encode
    Hangul: every message would raise UnicodeEncodeError and exit 1, the
    same code as a rejected form. Such streams are switched to UTF-8;
    encodings that can show Hangul (UTF-8, cp949) are left alone.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            "한글".encode(stream.encoding or "ascii")
        except (LookupError, UnicodeEncodeError):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")


def main() -> None:
    _hangul_safe_output()
    ap = argparse.ArgumentParser(description="GMP deviation report drafting assistant (draft only)")
    ap.add_argument("form", type=Path, nargs="*", help="intake YAML file(s)")
    ap.add_argument("--rules", type=Path, default=ROOT / "config/rules.yaml")
    ap.add_argument("--history", type=Path, default=ROOT / "data/synthetic/history.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "drafts")
    ap.add_argument("--docx", action="store_true", help="also write a Word file")
    ap.add_argument("--summary", action="store_true",
                    help="write _summary_<date>.md listing every form: proposed class or rejection reason")
    ap.add_argument("--xlsx", action="store_true",
                    help="with --summary: also write the summary as an Excel workbook")
    ap.add_argument("--check-history", action="store_true",
                    help="only check the --history CSV against rules.yaml; no drafts are written")
    ap.add_argument("--today", help="YYYY-MM-DD, for reproducible output")
    args = ap.parse_args()

    try:
        today = date.fromisoformat(args.today) if args.today else None
    except ValueError:
        ap.error(f"--today 는 YYYY-MM-DD 형식이어야 합니다: {args.today}")

    if args.check_history:
        try:
            rules = load_rules(args.rules)
            check_rules(rules)
            rep = check_history(args.history, rules, today)
        except (RulesError, HistoryError) as e:
            print(f"CONFIG ERR: {e}")
            raise SystemExit(EXIT_CONFIG_ERROR)
        print(render_report(args.history, rep))
        raise SystemExit(0 if rep.ok else EXIT_REJECTED)

    if not args.form:
        ap.error("입력 양식(.yaml)을 1개 이상 지정하십시오 (또는 --check-history)")
    args.form = expand_forms(args.form, ap)
    if args.xlsx and not args.summary:
        ap.error("--xlsx 는 --summary 와 함께 쓰십시오 (요약표를 Excel로 만드는 옵션)")

    try:
        results, _ = run_batch(args.form, args.rules, args.history, args.out, today, args.docx, args.summary,
                               args.xlsx)
    except RulesError as e:
        print(f"RULES ERR {args.rules}: {e}")
        raise SystemExit(EXIT_CONFIG_ERROR)
    except HistoryError as e:
        print(f"HISTORY ERR {e}")
        print("  → --check-history 로 전체 오류 목록을 확인하십시오. 초안은 만들지 않았습니다.")
        raise SystemExit(EXIT_CONFIG_ERROR)
    if any(not r.ok for r in results):
        raise SystemExit(EXIT_REJECTED)


if __name__ == "__main__":
    main()
