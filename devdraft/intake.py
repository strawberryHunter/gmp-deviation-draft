"""Load and validate a deviation intake form.

The form is plain YAML so that a QA member can fill it in without any tool,
and so that the same file can be produced by an existing QMS export.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class IntakeError(ValueError):
    pass


class RulesError(ValueError):
    """config/rules.yaml is inconsistent. Stops the whole run, not one form."""


@dataclass
class Deviation:
    id: str
    title: str
    site: str
    area: str
    product: str
    batch: str
    detected_at: str
    process_step: str
    description: str
    immediate_actions: str
    detected_by: str = ""
    equipment_id: str = ""
    category: str = ""
    parameters: list[dict] = field(default_factory=list)
    # risk switches - the reviewer confirms each one
    cpp_excursion: bool = False
    spec_oos: bool = False
    other_batches_possibly_affected: bool = False
    sterility_assurance_impacted: bool = False
    released_product_affected: bool = False
    data_integrity_concern: bool = False
    synthetic: bool = False

    def get(self, name: str):
        return getattr(self, name, None)


def _bool_fields() -> set[str]:
    return {f.name for f in Deviation.__dataclass_fields__.values() if f.type in ("bool", bool)}


def check_rules(rules: dict) -> None:
    """Every `equals:` trigger must point at a flag the reporter is forced to answer.

    Otherwise an omitted answer would default to False and silently drop
    the deviation to a lower proposed class.
    """
    flags = rules.get("required_flags") or []
    bad = [f for f in flags if f not in _bool_fields()]
    if bad:
        raise RulesError(f"required_flags에 예/아니오 항목이 아닌 것이 있습니다: {', '.join(bad)}")
    unguarded = sorted({
        trig["field"]
        for triggers in rules["classes"].values()
        for trig in triggers
        if "equals" in trig and trig["field"] not in flags
    })
    if unguarded:
        raise RulesError(
            "분류 트리거로 쓰이지만 required_flags에 없는 항목: "
            f"{', '.join(unguarded)} — required_flags에 추가하십시오."
        )


def load(path: str | Path, rules: dict) -> Deviation:
    check_rules(rules)
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" ({mark.line + 1}행)" if mark else ""
        raise IntakeError(f"YAML 문법 오류{where}: 들여쓰기·콜론·따옴표를 확인하십시오.") from None
    if not isinstance(raw, dict):
        raise IntakeError("양식 형식 오류: '항목: 값' 형태의 YAML이어야 합니다.")
    problems = []

    known = {f.name for f in Deviation.__dataclass_fields__.values()}
    unknown = set(raw) - known
    if unknown:
        problems.append(f"알 수 없는 항목: {', '.join(sorted(unknown))}")

    missing = [f for f in rules["required_fields"] if not raw.get(f)]
    if missing:
        problems.append(f"필수 항목 누락: {', '.join(missing)}")

    flags = rules.get("required_flags") or []
    unanswered = [f for f in flags if raw.get(f) is None]
    if unanswered:
        problems.append(f"예/아니오 미응답 (true 또는 false로 기재): {', '.join(unanswered)}")
    not_bool = [
        f"{f}={raw[f]!r}" for f in sorted(_bool_fields())
        if raw.get(f) is not None and not isinstance(raw[f], bool)
    ]
    if not_bool:
        problems.append(f"true/false가 아닌 값: {', '.join(not_bool)}")

    cat = raw.get("category")
    if cat and cat not in rules["categories"]:
        problems.append(f"category는 {rules['categories']} 중 하나여야 합니다: {cat}")

    if problems:
        raise IntakeError(" / ".join(problems))
    return Deviation(**raw)
