"""Load and validate a deviation intake form.

The form is plain YAML so that a QA member can fill it in without any tool,
and so that the same file can be produced by an existing QMS export.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from .rules import RulesError, check_rules as _check_rules, strict_load  # noqa: F401  (re-exported)


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
    patient_safety_impact: bool = False
    regulatory_report_required: bool = False
    synthetic: bool = False

    def get(self, name: str):
        return getattr(self, name, None)


def _bool_fields() -> set[str]:
    return {f.name for f in Deviation.__dataclass_fields__.values() if f.type in ("bool", bool)}


def check_rules(rules: dict) -> None:
    _check_rules(rules, _bool_fields())


TEMPLATE = Path(__file__).resolve().parents[1] / "templates/intake_template.yaml"
_COMMENT_LINE = re.compile(r"^(\w+):[^#\n]*#\s*(\S.*)$")


def _template_comments() -> dict[str, str]:
    """key -> inline comment text in the blank template."""
    if not TEMPLATE.exists():
        return {}
    out = {}
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        m = _COMMENT_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


_ANY_COMMENT = re.compile(r"(?:^|\s)#\s*(?:↓\s*\w+:\s*)?(\S.*)$")


def _template_phrases() -> list[str]:
    """Every guidance sentence in the blank template's comments.

    Kept in the same wording when the template is reorganised, so forms copied
    from an older template layout are still recognised.
    """
    if not TEMPLATE.exists():
        return []
    phrases = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        m = _ANY_COMMENT.search(line)
        if m:
            text = m.group(1).strip()
            if len(text) >= 10 and not set(text) <= set("─=-# "):
                phrases.append(text)
    return phrases


def _glued_template_comments(raw: dict) -> list[str]:
    """Keys whose value swallowed template guidance text.

    Two ways this happens, both copying the template's words into the draft
    as if the reporter had written them:
    - YAML only starts a comment at '#' preceded by whitespace, so
      `title: 제목# [필수] 한 줄 제목...` keeps the comment inside the value;
    - inside a multi-line `|` block, a more-indented "# ..." line is text,
      not a comment.
    """
    own = _template_comments()
    phrases = _template_phrases()
    hits = []
    for key, val in raw.items():
        if not isinstance(val, str):
            continue
        if (key in own and own[key][:8] in val) or any(p in val for p in phrases):
            hits.append(key)
    return sorted(hits)


_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")


def detected_datetime(value) -> datetime | None:
    """The discovery time as a datetime, or None if it is not an exact,
    valid date and time. "어제 새벽", "2026/11/25" or "2026-13-40T99:99" are
    not acceptable in a deviation record."""
    s = str(value).strip()
    if not _WHEN.match(s):
        return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError:
        return None


def _short(v, n: int = 20) -> str:
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def load(path: str | Path, rules: dict) -> Deviation:
    check_rules(rules)
    try:
        raw = strict_load(Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" ({mark.line + 1}행)" if mark else ""
        raise IntakeError(f"YAML 문법 오류{where}: 들여쓰기·콜론·따옴표를 확인하십시오.") from None
    except FileNotFoundError:
        raise IntakeError(f"파일이 없습니다: {path} — 경로와 파일 이름을 확인하십시오.") from None
    except UnicodeDecodeError:
        raise IntakeError("UTF-8이 아닙니다 — 메모장 등에서 'UTF-8'로 다시 저장하십시오.") from None
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
    glued = _glued_template_comments(raw)
    if glued:
        problems.append(
            "값에 양식 주석이 붙어 값의 일부로 읽힘 ('#' 앞에 공백을 두고, 여러 줄(|) 블록 안에는 "
            f"'#' 줄을 두지 마십시오): {', '.join(glued)}"
        )
    not_bool = [
        f"{f}={_short(raw[f])!r}" for f in sorted(_bool_fields())
        if raw.get(f) is not None and not isinstance(raw[f], bool) and f not in glued
    ]
    if not_bool:
        problems.append(f"true/false가 아닌 값: {', '.join(not_bool)}")

    multiline_ok = {"description", "immediate_actions"}
    broken = sorted(
        k for k, v in raw.items()
        if k not in multiline_ok and isinstance(v, str) and ("\n" in v.strip() or "\r" in v)
    )
    if broken:
        problems.append(f"한 줄로 적어야 하는 항목에 줄바꿈이 있음: {', '.join(broken)}")
    for n, prm in enumerate(raw.get("parameters") or [], 1):
        if isinstance(prm, dict) and any(isinstance(v, str) and "\n" in v.strip() for v in prm.values()):
            problems.append(f"parameters {n}번째 항목에 줄바꿈이 있음 — 한 줄로 적으십시오")

    when = raw.get("detected_at")
    if when and detected_datetime(when) is None:
        problems.append(
            f"detected_at '{_short(when)}' 는 실제 날짜·시각이어야 합니다 (YYYY-MM-DD HH:MM, 예: 2026-11-21T14:20)"
        )

    cat = raw.get("category")
    if cat and cat not in rules["categories"]:
        problems.append(f"category는 {rules['categories']} 중 하나여야 합니다: {cat}")

    if problems:
        raise IntakeError(" / ".join(problems))
    return Deviation(**raw)
