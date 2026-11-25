"""Load and check the deviation history CSV used for recurrence lookup.

The history is usually exported from the site QMS. Exports differ (Excel
adds a byte-order mark, dates come as 2026/10/21, IDs repeat across
re-exports), and each of those silently changes the recurrence count or
blanks the table if not caught. So:

- errors   -> the history cannot be trusted; nothing is drafted.
- warnings -> rows that cannot match anything or look odd; listed, run goes on.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .rules import level_ids

REQUIRED_COLUMNS = ["dev_id", "opened", "site", "equipment_id", "category", "final_class"]


class HistoryError(ValueError):
    """History file unusable. Stops the whole run, like a rules.yaml error."""


@dataclass
class HistoryReport:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _read(path: Path) -> tuple[list[str], list[dict], str]:
    """Read the CSV as UTF-8, or else as CP949 (Korean Excel's default "CSV").

    utf-8-sig: Excel's "CSV UTF-8" starts with a BOM that would otherwise
    become part of the first column name. CP949 is decoded strictly, so a
    file in some other encoding is an error rather than garbled site or
    equipment names that silently match nothing.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise HistoryError(f"이력 파일이 없습니다: {path}") from None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _CONTROL.search(text):
            continue
        reader = csv.DictReader(io.StringIO(text, newline=""))
        return list(reader.fieldnames or []), list(reader), encoding
    raise HistoryError(
        f"{path.name}: UTF-8도 CP949도 아닙니다. Excel에서 'CSV UTF-8(쉼표로 분리)'로 다시 저장하십시오."
    )


def check_history(path: str | Path, rules: dict, today: date | None = None) -> HistoryReport:
    path = Path(path)
    today = today or date.today()
    columns, rows, encoding = _read(path)
    rep = HistoryReport()
    if encoding == "cp949":
        rep.warnings.append(
            "CP949(Excel 기본 'CSV')로 읽었습니다 — 한글 사업장·설비 이름이 양식과 같은지 확인하십시오. "
            "'CSV UTF-8'로 저장하면 이 경고가 없어집니다"
        )

    need = REQUIRED_COLUMNS + (["root_cause"] if rules["recurrence"].get("show_root_cause") else [])
    missing = [c for c in need if c not in columns]
    if missing:
        rep.errors.append(f"필수 열 없음: {', '.join(missing)} (현재 열: {', '.join(columns) or '없음'})")
        return rep
    if not rows:
        rep.errors.append("데이터 행이 없습니다")
        return rep

    categories = set(rules["categories"])
    # final_class in history may follow an older or different scheme; rules can list it
    levels = set(level_ids(rules)) | set(rules.get("history_class_labels") or [])
    seen: dict[str, int] = {}
    unknown_cat: dict[str, list[int]] = {}
    unknown_cls: dict[str, list[int]] = {}

    for n, row in enumerate(rows, start=2):  # line 1 is the header
        rid = (row.get("dev_id") or "").strip()
        if not rid:
            rep.errors.append(f"{n}행: dev_id 비어 있음")
        elif rid in seen:
            rep.errors.append(f"{n}행: dev_id {rid} 중복 ({seen[rid]}행과 같음) — 반복 건수가 부풀려짐")
        else:
            seen[rid] = n

        raw_date = (row.get("opened") or "").strip()
        try:
            opened = date.fromisoformat(raw_date)
        except ValueError:
            rep.errors.append(f"{n}행: opened '{raw_date}' 는 YYYY-MM-DD 형식이 아님")
            continue
        if opened > today:
            rep.warnings.append(f"{n}행: opened {raw_date} 가 기준일({today}) 이후 — 반복성 조회에서 제외")

        for col in ("site", "equipment_id"):
            if col in rules["recurrence"]["match_on"] and not (row.get(col) or "").strip():
                rep.warnings.append(f"{n}행: {col} 비어 있음 — 어떤 deviation과도 일치하지 않음")
        cat = (row.get("category") or "").strip()
        if cat and cat not in categories:
            unknown_cat.setdefault(cat, []).append(n)
        cls = (row.get("final_class") or "").strip()
        if cls and cls not in levels:
            unknown_cls.setdefault(cls, []).append(n)

    for cat, lines in sorted(unknown_cat.items()):
        rep.warnings.append(
            f"category '{cat}' 는 rules.yaml categories에 없음 ({len(lines)}행, 예: {lines[0]}행) — 일치하지 않음"
        )
    for cls, lines in sorted(unknown_cls.items()):
        rep.warnings.append(
            f"final_class '{cls}' 는 rules.yaml levels에 없음 ({len(lines)}행, 예: {lines[0]}행) — "
            "표시만 하고 분류에는 쓰지 않음 (SOP 개정 전 등급명일 수 있음)"
        )

    rep.rows = rows if rep.ok else []
    return rep


def is_synthetic(rows: list[dict]) -> bool:
    """True if any history row is marked synthetic (column `synthetic`)."""
    return any(str(r.get("synthetic", "")).strip().lower() in ("true", "1", "yes") for r in rows)


def load_checked_history(path: str | Path, rules: dict, today: date | None = None) -> HistoryReport:
    rep = check_history(path, rules, today)
    if not rep.ok:
        shown = rep.errors[:10]
        more = f" 외 {len(rep.errors) - 10}건" if len(rep.errors) > 10 else ""
        raise HistoryError(f"{Path(path).name}: " + " / ".join(shown) + more)
    return rep


def render_report(path: str | Path, rep: HistoryReport) -> str:
    lines = [f"이력 점검: {path}", f"행 {len(rep.rows) if rep.ok else '-'}개 · 오류 {len(rep.errors)}건 · 경고 {len(rep.warnings)}건"]
    lines += [f"  ERR  {e}" for e in rep.errors]
    lines += [f"  WARN {w}" for w in rep.warnings]
    lines.append("결과: 사용 가능" if rep.ok else "결과: 사용 불가 — 오류를 고친 뒤 다시 점검하십시오")
    return "\n".join(lines)
