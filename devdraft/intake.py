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


def load(path: str | Path, rules: dict) -> Deviation:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    missing = [f for f in rules["required_fields"] if not raw.get(f)]
    if missing:
        raise IntakeError(f"필수 항목 누락: {', '.join(missing)}")
    known = {f.name for f in Deviation.__dataclass_fields__.values()}
    unknown = set(raw) - known
    if unknown:
        raise IntakeError(f"알 수 없는 항목: {', '.join(sorted(unknown))}")
    cat = raw.get("category")
    if cat and cat not in rules["categories"]:
        raise IntakeError(f"category는 {rules['categories']} 중 하나여야 합니다: {cat}")
    return Deviation(**raw)
