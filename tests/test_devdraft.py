from datetime import date
from pathlib import Path

import pytest
import yaml

from devdraft.classify import find_recurrence, investigation_plan, load_history, propose_class
from devdraft.cli import build
from devdraft.draft import render_markdown
from devdraft.intake import IntakeError, load

ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / "config/rules.yaml").read_text(encoding="utf-8"))
HISTORY = load_history(ROOT / "data/synthetic/history.csv")
INTAKE = ROOT / "data/synthetic/intake"
TODAY = date(2026, 11, 24)


def dev(name):
    return load(INTAKE / f"{name}.yaml", RULES)


def test_missing_required_field_is_rejected():
    with pytest.raises(IntakeError) as e:
        dev("DEV-2026-2204")  # detected_by deliberately left blank
    assert "detected_by" in str(e.value)


def test_unknown_field_is_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    base = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    base["root_cause"] = "human error"  # must not be enterable at intake
    p.write_text(yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
    with pytest.raises(IntakeError):
        load(p, RULES)


def test_sterility_flag_proposes_critical():
    d = dev("DEV-2026-2202")
    level, reasons = propose_class(d, RULES)
    assert level == "critical"
    assert any("무균" in r for r in reasons)


def test_cpp_excursion_proposes_major():
    d = dev("DEV-2026-2201")
    level, _ = propose_class(d, RULES, len(find_recurrence(d, HISTORY, RULES, TODAY)))
    assert level == "major"


def test_documentation_only_stays_minor():
    d = dev("DEV-2026-2203")
    level, _ = propose_class(d, RULES, 0)
    assert level == "minor"


def test_recurrence_window_excludes_old_records():
    d = dev("DEV-2026-2201")
    hits = find_recurrence(d, HISTORY, RULES, TODAY)
    assert hits
    assert all(h["opened"] >= "2025-11-24" for h in hits)
    assert all(h["equipment_id"] == "CHR-03" for h in hits)


def test_plan_puts_relevant_6m_first():
    plan = [k for k, _ in investigation_plan(dev("DEV-2026-2202"), RULES)]
    assert plan[:2] == ["Milieu", "Man"]


def test_draft_never_fills_judgement_sections():
    d = dev("DEV-2026-2201")
    md = render_markdown(d, "major", ["x"], [], investigation_plan(d, RULES), "2026-11-24")
    for section in ["## 6. 근본원인", "## 7. 제품 품질 영향 평가"]:
        body = md.split(section, 1)[1].split("##", 1)[0]
        assert "작성 필요" in body
    assert "승인 문서가 아닙니다" in md
    assert "서명란을 두지 않습니다" in md


def test_draft_contains_no_invented_numbers():
    """Every figure in the draft must come from the intake form."""
    d = dev("DEV-2026-2201")
    md = render_markdown(d, "major", [], [], investigation_plan(d, RULES), "2026-11-24")
    for token in ["3.62", "3.40-3.60", "6 min", "DS-26-0412"]:
        assert token in md
    assert "3.55" not in md and "7 min" not in md


def test_end_to_end_writes_md_and_docx(tmp_path):
    p = build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_docx=True)
    assert p.exists()
    docx = tmp_path / "DEV-2026-2201_draft.docx"
    assert docx.exists() and docx.stat().st_size > 10_000
