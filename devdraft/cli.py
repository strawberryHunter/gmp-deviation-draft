"""python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx"""
from __future__ import annotations

import argparse
import glob
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

from .classify import (find_recurrence, investigation_plan, lower_triggers, propose_class,
                       has_recurrence_trigger, qualify_for_unchecked_recurrence, unmatched_keys,
                       unused_yes_answers)
from .draft import FLAG_LABELS, render_markdown
from . import __version__
from .history import HistoryError, check_history, is_synthetic, load_checked_history, render_report
from .intake import TEMPLATE, IntakeError, check_rules, detected_datetime, load
from .rules import RulesError, load_rules
from .summary import FormResult, render_summary

ROOT = Path(__file__).resolve().parents[1]

# 0: every form drafted (or --check-history found no errors).
# 1: at least one form rejected, others still drafted (or history has errors in --check-history).
# 2: rules.yaml or history file unusable, nothing drafted.
EXIT_REJECTED = 1
EXIT_CONFIG_ERROR = 2
EXIT_RULES_ERROR = EXIT_CONFIG_ERROR  # kept for callers of the earlier name


def shown(path) -> str:
    """A path as the user should see it: relative to the current folder when
    the file is inside it (drafts\\x.md instead of C:\\Users\\...\\drafts\\x.md)."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


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
    reasons = qualify_for_unchecked_recurrence(dev, rules, level, reasons)
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
                      recurrence_checked=not unmatched_keys(dev, rules),
                      recurrence_evaluated=not (unmatched_keys(dev, rules) and has_recurrence_trigger(rules)),
                      unused_yes=[dict(FLAG_LABELS).get(f, f) for f in unused_yes_answers(dev, rules)],
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
            made = shown(r.draft) + (f", {shown(Path(r.draft).with_suffix('.docx'))}" if want_docx else "")
            print(f"OK  {f.name} -> {made}")
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
        extra = [summary_path.with_suffix(x) for x, on in ((".docx", want_docx), (".xlsx", want_xlsx)) if on]
        print("SUM " + ", ".join(shown(x) for x in [summary_path, *extra]))
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


# Every non-ASCII kind of character the CLI prints (messages, help, reports).
_PRINTED_SYMBOLS = "한글☐—·→…✅⚠↓─"


def _hangul_safe_output() -> None:
    """Keep Korean messages from crashing the CLI on a non-Korean console.

    On English Windows a pipe or redirect uses cp1252, which cannot encode
    Hangul: every message would raise UnicodeEncodeError and exit 1, the
    same code as a rejected form. Such streams are switched to UTF-8;
    encodings that can show everything the CLI prints are left alone.

    Hangul alone is not enough: Korean Windows writes redirected output as
    cp949, which has Hangul but not "☐" or "—", and both appear in the
    messages. So the probe includes them.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            _PRINTED_SYMBOLS.encode(stream.encoding or "ascii")
        except (LookupError, UnicodeEncodeError):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")


_FORM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def new_form(dev_id: str, out_dir: Path) -> Path:
    """Copy the blank template to <out_dir>/<dev_id>.yaml with the id filled in.

    The same on every OS (no mkdir/cp/copy). Never overwrites: a form may
    already hold facts someone typed.
    """
    if not _FORM_ID.match(dev_id):
        raise ValueError(f"deviation 번호에는 영문·숫자·'-'·'_'·'.'만 쓸 수 있습니다: {dev_id!r} (예: DEV-2026-2301)")
    target = out_dir / f"{dev_id}.yaml"
    if target.exists():
        raise FileExistsError(f"이미 있는 파일입니다: {target} — 덮어쓰지 않습니다. 그 파일을 열어 이어서 쓰십시오.")
    text = TEMPLATE.read_text(encoding="utf-8")
    filled = re.sub(r"^id: ''", f"id: '{dev_id}'", text, count=1, flags=re.M)
    assert filled != text, "템플릿의 id 줄을 찾지 못했습니다"
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(filled, encoding="utf-8", newline="\n")
    return target


def batch_footer(results: list[FormResult], out_dir: Path) -> str:
    """Last lines of a run: counts, where the files are, what to do next."""
    done = sum(r.ok for r in results)
    lines = [f"완료: 입력 {len(results)}건 · 초안 {done}건 · 거부 {len(results) - done}건 (저장 위치: {shown(out_dir)})"]
    if done < len(results):
        lines.append("  → ERR 줄의 양식을 보완한 뒤 다시 실행하십시오. 거부된 양식은 초안을 만들지 않았습니다.")
    if done:
        lines.append("  → 초안의 '☐ 작성 필요' 칸과 등급 확정은 담당자가 작성합니다.")
    return "\n".join(lines)


HELP_EPILOG = """\
예:
  python -m devdraft.cli --new DEV-2026-2301              빈 양식 만들기 (drafts/DEV-2026-2301.yaml)
  python -m devdraft.cli my_form.yaml                     초안 1건 (drafts/ 에 Markdown)
  python -m devdraft.cli forms/*.yaml --summary --docx    여러 건 + 요약표, Word 파일도
  python -m devdraft.cli --check-history --history qms.csv  이력 CSV만 점검

빈 양식: templates/intake_template.yaml · 사용법: docs/USAGE.md · 따라하기: docs/TUTORIAL.md
종료 코드: 0 모두 생성 / 1 거부된 양식 있음 / 2 규칙·이력 파일 오류"""


def main() -> None:
    _hangul_safe_output()
    ap = argparse.ArgumentParser(
        description="GMP deviation 보고서 초안 도우미 — 초안만 만듭니다. 근본원인·영향 평가·CAPA·등급 확정은 담당자가 씁니다.",
        epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False,
        prog="python -m devdraft.cli")
    inp = ap.add_argument_group("입력")
    opt = ap.add_argument_group("옵션")
    inp.add_argument("form", type=Path, nargs="*", help="입력 양식 YAML 파일 (여러 개 가능, *.yaml 가능)")
    opt.add_argument("--rules", type=Path, default=ROOT / "config/rules.yaml",
                    help="등급 기준 파일 (기본: config/rules.yaml)")
    opt.add_argument("--history", type=Path, default=ROOT / "data/synthetic/history.csv",
                    help="반복성 조회용 QMS 이력 CSV (기본: 합성 예시 — 실제 양식에는 실제 이력을 지정)")
    opt.add_argument("--out", type=Path, default=ROOT / "drafts", help="초안 저장 폴더 (기본: drafts/)")
    opt.add_argument("--docx", action="store_true", help="Word 파일(.docx)도 만듭니다")
    opt.add_argument("--summary", action="store_true",
                    help="여러 건의 제안 등급·거부 사유를 모은 요약표 _summary_<날짜>.md 를 만듭니다")
    opt.add_argument("--xlsx", action="store_true", help="--summary 와 함께: 요약표를 Excel로도 만듭니다")
    opt.add_argument("--new", metavar="번호",
                     help="빈 양식을 --out 폴더(기본 drafts/)에 <번호>.yaml 로 만듭니다 (초안은 만들지 않음)")
    opt.add_argument("--check-history", action="store_true",
                    help="--history CSV만 점검합니다 (초안은 만들지 않음)")
    opt.add_argument("--today", metavar="YYYY-MM-DD", help="기준일을 고정합니다 (같은 결과를 다시 만들 때)")
    opt.add_argument("-h", "--help", action="help", help="이 도움말을 보여 줍니다")
    args = ap.parse_args()

    try:
        today = date.fromisoformat(args.today) if args.today else None
    except ValueError:
        ap.error(f"--today 는 YYYY-MM-DD 형식이어야 합니다: {args.today}")

    if args.new:
        try:
            made = new_form(args.new, args.out)
        except (ValueError, FileExistsError) as e:
            print(f"ERR {e}")
            raise SystemExit(EXIT_REJECTED)
        print(f"NEW {shown(made)}")
        print("  → 이 파일을 메모장·VS Code 등으로 열어 채웁니다 (항목마다 '#' 뒤에 설명이 있습니다).")
        print(f"  → 다 채운 뒤: python -m devdraft.cli {shown(made)} --docx")
        print("  → 연습용(가짜) 내용이면 파일 맨 위에 synthetic: true 를 넣어야 이력 파일 없이 실행됩니다.")
        raise SystemExit(0)

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
        ap.error("입력 양식(.yaml)을 1개 이상 지정하십시오 (빈 양식은 --new 번호, 이력 점검은 --check-history). 사용법: python -m devdraft.cli --help")
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
    print(batch_footer(results, args.out))
    if any(not r.ok for r in results):
        raise SystemExit(EXIT_REJECTED)


if __name__ == "__main__":
    main()
