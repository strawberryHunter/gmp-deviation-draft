"""Propose an initial classification and look for recurrence.

The output is a PROPOSAL. Nothing here decides a classification: the QA
reviewer confirms or overrides it, and the draft records both.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .intake import Deviation


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


def propose_class(dev: Deviation, rules: dict, recurrence_count: int = 0) -> tuple[str, list[str]]:
    for level in ("critical", "major", "minor"):
        reasons = []
        for trig in rules["classes"][level]:
            fld = trig["field"]
            if fld == "_default":
                reasons.append(trig["reason"])
            elif "equals" in trig and dev.get(fld) == trig["equals"]:
                reasons.append(trig["reason"])
            elif "min" in trig and fld == "recurrence_12m" and recurrence_count >= trig["min"]:
                reasons.append(f"{trig['reason']} — 유사 건 {recurrence_count}건")
        if reasons:
            return level, reasons
    return "minor", ["분류 근거 없음 (검토자 확인 필요)"]


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
