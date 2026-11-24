from datetime import date
from pathlib import Path

import pytest
import yaml

from devdraft.classify import find_recurrence, investigation_plan, load_history, propose_class
from devdraft.cli import build, run_batch
from devdraft.summary import FormResult, render_summary
from devdraft.draft import render_markdown
import subprocess

from devdraft.intake import Deviation, IntakeError, RulesError, load

ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / "config/rules.yaml").read_text(encoding="utf-8"))
HISTORY = load_history(ROOT / "data/synthetic/history.csv")
INTAKE = ROOT / "data/synthetic/intake"
TEMPLATE = ROOT / "templates/intake_template.yaml"
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


# --- risk flag validation -------------------------------------------------

FLAGS = RULES["required_flags"]


def write_form(tmp_path, **changes):
    base = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    for k, v in changes.items():
        if v is _DROP:
            base.pop(k, None)
        else:
            base[k] = v
    p = tmp_path / "form.yaml"
    p.write_text(yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
    return p


_DROP = object()


@pytest.mark.parametrize("flag", FLAGS)
def test_omitted_flag_is_rejected_not_read_as_false(tmp_path, flag):
    with pytest.raises(IntakeError) as e:
        load(write_form(tmp_path, **{flag: _DROP}), RULES)
    assert flag in str(e.value)


@pytest.mark.parametrize("flag", FLAGS)
def test_blank_flag_is_rejected(tmp_path, flag):
    with pytest.raises(IntakeError) as e:
        load(write_form(tmp_path, **{flag: None}), RULES)
    assert "미응답" in str(e.value) and flag in str(e.value)


@pytest.mark.parametrize("value", ["yes", "예", "true", "false", "아니오", 1, 0, "Y"])
def test_non_boolean_flag_is_rejected(tmp_path, value):
    with pytest.raises(IntakeError) as e:
        load(write_form(tmp_path, sterility_assurance_impacted=value), RULES)
    assert "sterility_assurance_impacted" in str(e.value)


def test_explicit_false_flags_are_accepted(tmp_path):
    d = load(write_form(tmp_path, **{f: False for f in FLAGS}), RULES)
    assert all(d.get(f) is False for f in FLAGS)


def test_all_problems_reported_together(tmp_path):
    p = write_form(tmp_path, detected_by="", spec_oos=_DROP, cpp_excursion="yes")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    msg = str(e.value)
    assert "detected_by" in msg and "spec_oos" in msg and "cpp_excursion" in msg


def test_every_class_trigger_is_a_required_flag():
    for triggers in RULES["classes"].values():
        for t in triggers:
            if "equals" in t:
                assert t["field"] in FLAGS, t["field"]


def test_rules_with_unguarded_trigger_stop_the_run(tmp_path):
    bad = yaml.safe_load(yaml.safe_dump(RULES))
    bad["required_flags"].remove("sterility_assurance_impacted")
    with pytest.raises(RulesError) as e:
        load(INTAKE / "DEV-2026-2202.yaml", bad)
    assert "sterility_assurance_impacted" in str(e.value)


def test_rules_flag_must_be_boolean_field():
    bad = yaml.safe_load(yaml.safe_dump(RULES))
    bad["required_flags"].append("title")
    with pytest.raises(RulesError):
        load(INTAKE / "DEV-2026-2201.yaml", bad)


# --- blank intake template ------------------------------------------------

def _template():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def test_template_has_only_known_fields_and_no_judgement_fields():
    t = _template()
    known = set(Deviation.__dataclass_fields__)
    assert set(t) <= known
    for f in ("root_cause", "impact_assessment", "capa", "final_class"):
        assert f not in t


def test_template_covers_all_required_fields_and_flags():
    t = _template()
    for f in RULES["required_fields"] + FLAGS:
        assert f in t, f


def test_template_is_blank():
    """Nothing pre-filled: every value is empty, so QA must type each fact."""
    for k, v in _template().items():
        assert v in ("", None, []), f"{k} is pre-filled: {v!r}"


def test_unfilled_template_is_rejected_with_every_missing_item():
    with pytest.raises(IntakeError) as e:
        load(TEMPLATE, RULES)
    msg = str(e.value)
    for f in RULES["required_fields"] + FLAGS:
        assert f in msg, f


def test_filled_template_is_accepted(tmp_path):
    filled = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    t = _template()
    t.update({k: v for k, v in filled.items() if k in t})
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(t, allow_unicode=True), encoding="utf-8")
    assert load(p, RULES).id == "DEV-2026-2203"


def test_template_trigger_comments_match_rules():
    """The '→ major/critical' hints in the template must follow rules.yaml."""
    level_of = {t["field"]: lvl for lvl, ts in RULES["classes"].items() for t in ts if "equals" in t}
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        key = line.split(":", 1)[0]
        if key in level_of and "→" in line:
            assert f"→ {level_of[key]} " in line, line


# --- repository hygiene ---------------------------------------------------

@pytest.mark.parametrize("path", ["drafts/DEV-1_draft.md", "x/DEV-1_draft.docx", "sample_output/a.docx"])
def test_real_outputs_are_gitignored(path):
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    if r.returncode == 128:
        pytest.skip("not a git checkout")
    assert r.returncode == 0, f"{path} is not ignored"


# --- batch summary (--summary) --------------------------------------------

def _batch(tmp_path, forms, **kw):
    return run_batch(forms, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
                     tmp_path, TODAY, want_summary=True, **kw)


def test_summary_lists_every_form_drafted_or_rejected(tmp_path):
    forms = sorted(INTAKE.glob("*.yaml"))
    results, path = _batch(tmp_path, forms)
    md = path.read_text(encoding="utf-8")
    assert path.name == "_summary_2026-11-24.md"
    assert "입력 4건 · 초안 생성 3건 · 거부 1건" in md
    for f in forms:
        assert f.name in md
    rejected = md.split("## 거부", 1)[1]
    assert "DEV-2026-2204.yaml" in rejected and "detected_by" in rejected


def test_summary_marks_class_as_proposal_only(tmp_path):
    _, path = _batch(tmp_path, sorted(INTAKE.glob("*.yaml")))
    md = path.read_text(encoding="utf-8")
    assert "판단·승인 문서가 아닙니다" in md
    for lvl in ("MAJOR", "CRITICAL", "MINOR"):
        assert f"{lvl} (제안)" in md
    assert "확정 등급:" not in md  # confirmation lives only in each draft


def test_summary_never_repeats_historical_root_causes(tmp_path):
    _, path = _batch(tmp_path, [INTAKE / "DEV-2026-2201.yaml"])
    md = path.read_text(encoding="utf-8")
    assert "| 6 |" in md  # recurrence count only
    for rc in {r["root_cause"] for r in HISTORY}:
        assert rc not in md, rc
    assert "근본원인" not in md


def test_summary_contains_no_numbers_beyond_input_and_counts(tmp_path):
    _, path = _batch(tmp_path, [INTAKE / "DEV-2026-2201.yaml"])
    md = path.read_text(encoding="utf-8")
    assert "3.62" not in md and "3.40-3.60" not in md  # parameters stay in the draft


def test_summary_header_follows_rules_window(tmp_path):
    md = render_summary([FormResult(file="a.yaml", ok=False, error="x")], "2026-11-24", 180)
    assert "최근 180일" not in md  # no drafted rows -> no table header
    md = render_summary([FormResult(file="a.yaml", ok=True, dev_id="D", proposed="minor")], "2026-11-24", 180)
    assert "최근 180일" in md


def test_summary_escapes_pipes_in_cells():
    r = FormResult(file="a.yaml", ok=True, dev_id="D-1", title="A | B", proposed="minor", reasons=["x"])
    row = [l for l in render_summary([r], "2026-11-24", 365).splitlines() if l.startswith("| D-1")][0]
    assert "A \\| B" in row


def test_duplicate_id_in_one_run_is_rejected_not_overwritten(tmp_path):
    f = INTAKE / "DEV-2026-2203.yaml"
    results, path = _batch(tmp_path / "out", [f, f])
    assert [r.ok for r in results] == [True, False]
    assert "이미 있습니다" in results[1].error


def test_malformed_yaml_is_a_rejection_not_a_crash(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: DEV-1\ntitle: [unclosed\n", encoding="utf-8")
    results, path = _batch(tmp_path / "out", [bad, INTAKE / "DEV-2026-2203.yaml"])
    assert [r.ok for r in results] == [False, True]
    assert "YAML 문법 오류" in results[0].error


def test_no_summary_file_without_flag(tmp_path):
    run_batch([INTAKE / "DEV-2026-2203.yaml"], ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY)
    assert not list(tmp_path.glob("_summary_*"))
