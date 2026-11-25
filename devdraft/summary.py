"""Batch summary table for several intake forms processed in one run.

The summary only lists what the run produced: which forms became drafts,
the PROPOSED class and its trigger reasons, how many recurrence hits were
found, and why a form was rejected. It does not rank, prioritise or
confirm anything, and it never repeats root causes from history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .mdtext import inline
from .rules import level_label


@dataclass
class FormResult:
    file: str
    ok: bool
    dev_id: str = ""
    title: str = ""
    proposed: str = ""
    reasons: list[str] = field(default_factory=list)
    recurrence_count: int = 0
    recurrence_checked: bool = True
    recurrence_evaluated: bool = True  # False: rules have a recurrence criterion that was not checked
    unused_yes: list[str] = field(default_factory=list)  # "yes" answers no criterion uses
    draft: str = ""
    error: str = ""
    synthetic: bool = False


# Shared by the Markdown and Excel summaries. Kept out of f-strings: nesting
# quotes inside an f-string needs Python 3.12+ and this project supports 3.10.
def grade_text(r: FormResult, rules: dict | None) -> str:
    caveat = "" if r.recurrence_evaluated else ", 반복 기준 미평가"
    return f"{level_label(rules, r.proposed)} (제안{caveat})"


def reason_lines(r: FormResult) -> list[str]:
    extra = ["※ 규칙에 없는 '예' 답변: " + ", ".join(r.unused_yes)] if r.unused_yes else []
    return [*r.reasons, *extra]


def recurrence_text(r: FormResult):
    return r.recurrence_count if r.recurrence_checked else "조회 안 함"


def _cell(text: str) -> str:
    # Rejection messages may span lines; a table cell may not.
    return inline(" ".join(str(text).split("\n")).strip())


def render_summary(results: list[FormResult], generated_on: str, window_days: int,
                   rules: dict | None = None) -> str:
    done = [r for r in results if r.ok]
    rejected = [r for r in results if not r.ok]
    lines = [
        f"# Deviation 초안 일괄 처리 요약 — {generated_on}",
        "",
        "> **작업 목록입니다 — 판단·승인 문서가 아닙니다.**  ",
        "> 등급은 규칙에 따른 **제안**이며, 확정은 각 초안의 \"QA 검토자 확정 등급\"란에서 검토자가 직접 기재합니다.  ",
        "> 이 표는 처리 순서나 우선순위를 정하지 않습니다.",
        "",
        *(["> **합성(가짜) 데이터로 만든 초안이 포함되어 있습니다 — 실제 deviation 문서로 사용 금지.**", ""]
          if any(r.synthetic for r in done) else []),
        f"입력 {len(results)}건 · 초안 생성 {len(done)}건 · 거부 {len(rejected)}건",
        "",
        "## 초안 생성",
        "",
    ]
    if done:
        lines += [
            f"| Deviation 번호 | 제목 | 제안 등급 | 제안 근거 | 반복 건 (최근 {window_days}일) | 초안 | 입력 파일 |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {_cell(r.dev_id)} | {_cell(r.title)} | {_cell(grade_text(r, rules))} | "
            f"{_cell('; '.join(reason_lines(r)))} | {recurrence_text(r)} | {_cell(Path(r.draft).name)} | {_cell(r.file)} |"
            for r in done
        ]
    else:
        lines.append("없음.")
    lines += ["", "## 거부 — 양식 보완 후 다시 실행", ""]
    if rejected:
        lines += ["| 입력 파일 | 거부 사유 |", "|---|---|"]
        lines += [f"| {_cell(r.file)} | {_cell(r.error)} |" for r in rejected]
    else:
        lines.append("없음.")
    lines.append("")
    return "\n".join(lines)
