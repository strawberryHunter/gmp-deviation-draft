"""Batch summary as an Excel workbook (--summary --xlsx).

Same content as the Markdown summary — proposed class with its reasons,
recurrence count, rejection reasons — and the same limits: no confirmation
column, no ranking, no past root causes.

Every entered value is written as plain text. openpyxl stores a string that
starts with "=" as a live formula, and Excel evaluates cells starting with
= + - @ when someone edits them, so a title like =HYPERLINK(...) would become
an active link or calculation (formula injection). Such cells are forced to
text and marked with Excel's quote prefix.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .summary import FormResult, grade_text, reason_lines, recurrence_text

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
_NOTE_FILL = PatternFill("solid", fgColor="FFF2CC")
_RED = Font(bold=True, color="C00000")


def _put(ws, row: int, col: int, value, *, bold: bool = False):
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        cell.data_type = "s"  # never a formula
        cell.quotePrefix = True  # and stays text when edited in Excel
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    if bold:
        cell.font = Font(bold=True)
    return cell


def _notes(ws, lines: list[tuple[str, bool]], width: int) -> int:
    for r, (text, red) in enumerate(lines, start=1):
        c = _put(ws, r, 1, text)
        c.fill = _NOTE_FILL
        if red:
            c.font = _RED
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=width)
    return len(lines) + 2  # one blank row, then the header


def _table(ws, header_row: int, header: list[str], rows: list[list], widths: list[int]) -> None:
    for c, h in enumerate(header, start=1):
        _put(ws, header_row, c, h, bold=True).fill = _HEADER_FILL
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    for r, values in enumerate(rows, start=header_row + 1):
        for c, v in enumerate(values, start=1):
            _put(ws, r, c, v)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(header))}{header_row + len(rows)}"


def write_summary_xlsx(results: list[FormResult], generated_on: str, window_days: int,
                       rules: dict | None, path: str | Path) -> Path:
    done = [r for r in results if r.ok]
    rejected = [r for r in results if not r.ok]
    notes = [
        (f"deviation 초안 일괄 처리 요약 — {generated_on}", False),
        ("작업 목록입니다 — 판단·승인 문서가 아닙니다. 등급은 규칙에 따른 제안이며, 확정은 각 초안에서 QA 검토자가 합니다.", False),
        (f"입력 {len(results)}건 · 초안 생성 {len(done)}건 · 거부 {len(rejected)}건", False),
    ]
    if any(r.synthetic for r in done):
        notes.insert(1, ("합성(가짜) 데이터로 만든 초안이 포함되어 있습니다 — 실제 deviation 문서로 사용 금지", True))

    wb = Workbook()
    ws = wb.active
    ws.title = "초안 생성"
    header = ["Deviation 번호", "제목", "제안 등급", "제안 근거", f"반복 건 (최근 {window_days}일)", "초안", "입력 파일"]
    start = _notes(ws, notes, len(header))
    _table(ws, start, header, [
        [r.dev_id, r.title, grade_text(r, rules), "\n".join(reason_lines(r)),
         recurrence_text(r), Path(r.draft).name, r.file]
        for r in done
    ], [16, 40, 18, 50, 14, 26, 24])

    ws2 = wb.create_sheet("거부")
    start2 = _notes(ws2, [("거부된 양식 — 양식을 보완한 뒤 다시 실행하십시오.", False)], 2)
    _table(ws2, start2, ["입력 파일", "거부 사유"], [[r.file, r.error] for r in rejected], [28, 100])

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
