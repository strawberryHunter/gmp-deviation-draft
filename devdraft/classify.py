"""Propose an initial classification and look for recurrence.

The output is a PROPOSAL. Nothing here decides a classification: the QA
reviewer confirms or overrides it, and the draft records both.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from .intake import Deviation
from .rules import RECURRENCE_FIELD, level_ids


def load_history(path: str | Path) -> list[dict]:
    """Raw read without checks. The CLI uses history.load_checked_history."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


MATCH_LABEL = {"equipment_id": "설비", "category": "유형", "site": "사업장"}


def unmatched_keys(dev: Deviation, rules: dict) -> list[str]:
    """match_on keys the form leaves empty. With any of them empty no history
    row can match, so recurrence was NOT checked — which must not be reported
    as "no recurrence"."""
    return [k for k in rules["recurrence"]["match_on"] if not str(dev.get(k) or "").strip()]


def has_recurrence_trigger(rules: dict) -> bool:
    return any(t.get("field") == RECURRENCE_FIELD for ts in rules["classes"].values() for t in ts or [])


def qualify_for_unchecked_recurrence(dev: Deviation, rules: dict, level: str,
                                     reasons: list[str]) -> list[str]:
    """If recurrence could not be checked, say so in the proposal's reasons.

    A default reason such as "최근 2년 내 … deviation 없음" would then state
    something nobody checked, so at the default level it is replaced.
    """
    missing = unmatched_keys(dev, rules)
    if not missing or not has_recurrence_trigger(rules):
        return reasons
    labels = "·".join(MATCH_LABEL.get(k, k) for k in missing)
    note = (f"반복성 조회를 하지 않음({labels} 미기재) — 반복 기준은 평가되지 않았습니다. "
            "검토자가 QMS에서 직접 확인 필요")
    if level == rules["default_level"]:
        # The rules' own default wording may assert "no recurrence"; replace it
        # with what is actually known: no other criterion matched.
        return [note, "그 밖의 분류 기준에는 해당 없음 (보고자 입력 기준) — 검토자 확인 필요"]
    return [*reasons, note]


# Reporting is a separate decision with its own ☐ item in the draft.
_NOT_A_GRADE_QUESTION = {"regulatory_report_required"}


def unused_yes_answers(dev: Deviation, rules: dict) -> list[str]:
    """Questions answered "yes" that no classification criterion of these
    rules uses. The tool must not invent a criterion for them, but a serious
    "yes" (e.g. 출하 제품 영향) must not vanish silently from the proposal."""
    used = {t["field"] for ts in rules["classes"].values() for t in ts or [] if "equals" in t}
    return [f for f in rules.get("required_flags") or []
            if dev.get(f) is True and f not in used and f not in _NOT_A_GRADE_QUESTION]


def find_recurrence(dev: Deviation, history: list[dict], rules: dict, today: date | None = None) -> list[dict]:
    """Past deviations in the window that match on every `match_on` key.

    Excluded: rows dated after `today` (not "past"), and the deviation
    itself if the QMS export already contains it — it must not count as its
    own recurrence.
    """
    today = today or date.today()
    cfg = rules["recurrence"]
    cutoff = today - timedelta(days=cfg["window_days"])
    keys = cfg["match_on"]
    hits = []
    for row in history:
        opened = date.fromisoformat(row["opened"].strip())
        if opened < cutoff or opened > today:
            continue
        if (row.get("dev_id") or "").strip() == dev.id:
            continue
        if all((row.get(k) or "").strip() and row[k].strip() == (dev.get(k) or "").strip() for k in keys):
            hits.append(row)
    return sorted(hits, key=lambda r: r["opened"], reverse=True)


def matched_triggers(dev: Deviation, rules: dict, recurrence_count: int = 0) -> list[tuple[str, str]]:
    """Every trigger the form hits, as (level id, reason), highest level first."""
    hits = []
    for level in level_ids(rules):
        for trig in rules["classes"].get(level) or []:
            fld = trig["field"]
            if "equals" in trig and dev.get(fld) == trig["equals"]:
                hits.append((level, trig["reason"]))
            elif "min" in trig and fld == RECURRENCE_FIELD and recurrence_count >= trig["min"]:
                hits.append((level, f"{trig['reason']} — 유사 건 {recurrence_count}건"))
    return hits


def propose_class(dev: Deviation, rules: dict, recurrence_count: int = 0) -> tuple[str, list[str]]:
    hits = matched_triggers(dev, rules, recurrence_count)
    if not hits:
        return rules["default_level"], [rules["default_reason"]]
    top = hits[0][0]
    return top, [r for lvl, r in hits if lvl == top]


def lower_triggers(dev: Deviation, rules: dict, recurrence_count: int = 0) -> list[tuple[str, str]]:
    """Triggers hit below the proposed level — shown so the reviewer sees all of them."""
    hits = matched_triggers(dev, rules, recurrence_count)
    return [h for h in hits if hits and h[0] != hits[0][0]]


def investigation_plan(dev: Deviation, rules: dict) -> list[tuple[str, str]]:
    """6M prompts, with the two most relevant to this category put first."""
    focus = {
        "equipment": ["Machine", "Method"],
        "process_parameter": ["Machine", "Method"],
        "environmental_monitoring": ["Milieu", "Man"],
        "documentation": ["Man", "Method"],
        "material": ["Material", "Measurement"],
        "personnel": ["Man", "Method"],
        "utilities": ["Milieu", "Machine"],
    }.get(dev.category, [])
    items = list(rules["ishikawa"].items())
    items.sort(key=lambda kv: focus.index(kv[0]) if kv[0] in focus else len(focus) + 1)
    return items
