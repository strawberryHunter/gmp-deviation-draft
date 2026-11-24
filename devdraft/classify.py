"""Propose an initial classification and look for recurrence.

The output is a PROPOSAL. Nothing here decides a classification: the QA
reviewer confirms or overrides it, and the draft records both.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .intake import Deviation
from .rules import RECURRENCE_FIELD, level_ids


def load_history(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_recurrence(dev: Deviation, history: list[dict], rules: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    cfg = rules["recurrence"]
    cutoff = today - timedelta(days=cfg["window_days"])
    keys = cfg["match_on"]
    hits = []
    for row in history:
        if datetime.fromisoformat(row["opened"]).date() < cutoff:
            continue
        if all(row.get(k) and row[k] == (dev.get(k) or "") for k in keys):
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
