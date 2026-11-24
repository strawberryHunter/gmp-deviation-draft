"""Batch summary table for several intake forms processed in one run.

The summary only lists what the run produced: which forms became drafts,
the PROPOSED class and its trigger reasons, how many recurrence hits were
found, and why a form was rejected. It does not rank, prioritise or
confirm anything, and it never repeats root causes from history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
    draft: str = ""
    error: str = ""


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def render_summary(results: list[FormResult], generated_on: str, window_days: int,
                   rules: dict | None = None) -> str:
    done = [r for r in results if r.ok]
    rejected = [r for r in results if not r.ok]
    lines = [
        f"# 일탈 초안 일괄 처리 요약 — {generated_on}",
        "",
        "> **작업 목록입니다 — 판단·승인 문서가 아닙니다.**  ",
        "> 등급은 규칙에 따른 **제안**이며, 확정은 각 초안의 \"QA 검토자 확정 등급\"란에서 검토자가 직접 기재합니다.  ",
        "> 이 표는 처리 순서나 우선순위를 정하지 않습니다.",
        "",
        f"입력 {len(results)}건 · 초안 생성 {len(done)}건 · 거부 {len(rejected)}건",
        "",
        "## 초안 생성",
        "",
    ]
    if done:
        lines += [
            f"| 일탈 번호 | 제목 | 제안 등급 | 제안 근거 | 반복 건 (최근 {window_days}일) | 초안 | 입력 파일 |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {_cell(r.dev_id)} | {_cell(r.title)} | {_cell(level_label(rules, r.proposed))} (제안) | "
            f"{_cell('; '.join(r.reasons))} | {r.recurrence_count} | {_cell(Path(r.draft).name)} | {_cell(r.file)} |"
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
