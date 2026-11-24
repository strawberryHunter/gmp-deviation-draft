"""Load and check config/rules.yaml.

QA edits rules.yaml without touching code, so every mistake that would
silently change a proposed class must stop the run with a clear message
instead: an unknown level, a trigger on a flag the reporter is not forced
to answer, a typo in a trigger key, and so on.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that treats only true/false as booleans.

    PyYAML follows YAML 1.1, where unquoted yes/no/on/off are booleans too.
    In a GxP form a habitual "no" must not silently become False, so those
    stay strings and fail the true/false check.
    """


StrictLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:bool"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def strict_load(text: str):
    return yaml.load(text, Loader=StrictLoader)  # SafeLoader subclass: no object construction


# Trigger on the number of matching deviations found in history.
RECURRENCE_FIELD = "recurrence_count"

_LEGACY = {
    "_default": "minor의 `_default` 트리거 대신 최상위의 default_level / default_reason 을 사용하십시오.",
    "recurrence_12m": f"`recurrence_12m` 대신 `{RECURRENCE_FIELD}` 를 사용하십시오 (기간은 recurrence.window_days).",
}


class RulesError(ValueError):
    """config/rules.yaml is inconsistent. Stops the whole run, not one form."""


def load_rules(path: str | Path) -> dict:
    try:
        rules = strict_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" ({mark.line + 1}행)" if mark else ""
        raise RulesError(f"rules.yaml YAML 문법 오류{where}") from None
    check_rules(rules)
    return rules


def level_ids(rules: dict) -> list[str]:
    return [lv["id"] for lv in rules["levels"]]


def level_label(rules: dict | None, level: str) -> str:
    if rules:
        for lv in rules["levels"]:
            if lv["id"] == level:
                return lv.get("label") or level.upper()
    return level.upper()


def check_rules(rules: dict, bool_fields: set[str] | None = None) -> None:
    if not isinstance(rules, dict):
        raise RulesError("rules.yaml 형식 오류: '항목: 값' 형태여야 합니다.")
    problems: list[str] = []

    for key in ("required_fields", "required_flags", "levels", "default_level",
                "default_reason", "classes", "recurrence", "categories", "ishikawa"):
        if key not in rules:
            problems.append(f"'{key}' 항목이 없습니다")
    if problems:
        raise RulesError("rules.yaml: " + " / ".join(problems))

    levels = rules["levels"] or []
    ids = [lv.get("id") for lv in levels if isinstance(lv, dict)]
    if not ids or len(ids) != len(levels) or any(not i for i in ids):
        problems.append("levels는 '- id: ...' 목록이어야 합니다 (높은 등급부터)")
    if len(set(ids)) != len(ids):
        problems.append("levels에 중복된 id가 있습니다")

    if rules["default_level"] not in ids:
        problems.append(f"default_level '{rules['default_level']}' 이(가) levels에 없습니다")
    if not str(rules.get("default_reason") or "").strip():
        problems.append("default_reason 이 비어 있습니다")

    flags = rules["required_flags"] or []
    if bool_fields is not None:
        bad = [f for f in flags if f not in bool_fields]
        if bad:
            problems.append(f"required_flags에 예/아니오 항목이 아닌 것이 있습니다: {', '.join(bad)}")

    for lvl, triggers in (rules["classes"] or {}).items():
        if lvl not in ids:
            problems.append(f"classes의 '{lvl}' 이(가) levels에 없습니다")
        for n, trig in enumerate(triggers or [], 1):
            where = f"classes.{lvl} {n}번째"
            if not isinstance(trig, dict):
                problems.append(f"{where}: 형식 오류")
                continue
            fld = trig.get("field")
            if fld in _LEGACY:
                problems.append(f"{where}: {_LEGACY[fld]}")
                continue
            extra = set(trig) - {"field", "equals", "min", "reason"}
            if extra:
                problems.append(f"{where}: 알 수 없는 키 {sorted(extra)}")
            if not fld or not str(trig.get("reason") or "").strip():
                problems.append(f"{where}: field 와 reason 이 모두 필요합니다")
            if ("equals" in trig) == ("min" in trig):
                problems.append(f"{where}: equals 또는 min 중 하나만 지정하십시오")
            elif "equals" in trig:
                if trig["equals"] is not True and trig["equals"] is not False:
                    problems.append(f"{where}: equals 는 true 또는 false 여야 합니다")
                if fld not in flags:
                    problems.append(
                        f"분류 트리거로 쓰이지만 required_flags에 없는 항목: {fld} — required_flags에 추가하십시오"
                    )
            elif "min" in trig:
                if fld != RECURRENCE_FIELD:
                    problems.append(f"{where}: min 은 {RECURRENCE_FIELD} 에만 쓸 수 있습니다")
                if not isinstance(trig["min"], int) or isinstance(trig["min"], bool) or trig["min"] < 1:
                    problems.append(f"{where}: min 은 1 이상의 정수여야 합니다")

    rec = rules["recurrence"] or {}
    wd = rec.get("window_days")
    if not isinstance(wd, int) or isinstance(wd, bool) or wd < 1:
        problems.append("recurrence.window_days 는 1 이상의 정수여야 합니다")
    if "show_root_cause" in rec and not isinstance(rec["show_root_cause"], bool):
        problems.append("recurrence.show_root_cause 는 true 또는 false 여야 합니다")
    allowed_match = {"equipment_id", "category", "site"}  # columns of history.csv
    bad_match = [k for k in rec.get("match_on") or [] if k not in allowed_match]
    if not rec.get("match_on") or bad_match:
        problems.append(f"recurrence.match_on 은 {sorted(allowed_match)} 중에서 1개 이상이어야 합니다")

    if problems:
        raise RulesError("rules.yaml: " + " / ".join(dict.fromkeys(problems)))
