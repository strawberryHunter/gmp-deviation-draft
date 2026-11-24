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
    assert "| 5 |" in md  # recurrence count only (same site)
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


# --- rules.yaml structure (levels / SOP mapping) -----------------------------

import copy  # noqa: E402

from devdraft.classify import lower_triggers  # noqa: E402
from devdraft.rules import load_rules  # noqa: E402
from devdraft.intake import check_rules  # noqa: E402


def rules_with(**changes):
    r = copy.deepcopy(RULES)
    r.update(changes)
    return r


def test_shipped_rules_file_is_valid():
    load_rules(ROOT / "config/rules.yaml")


def test_custom_levels_and_labels_from_sop():
    """A 4-level SOP with Korean labels needs only rules.yaml changes."""
    r = rules_with(
        levels=[{"id": "l1", "label": "중대(1등급)"}, {"id": "l2", "label": "주요(2등급)"},
                {"id": "l3", "label": "경미(3등급)"}, {"id": "l4", "label": "사건(Event)"}],
        default_level="l4",
        default_reason="트리거 해당 없음",
        classes={
            "l1": [{"field": "sterility_assurance_impacted", "equals": True, "reason": "무균"}],
            "l2": [{"field": "cpp_excursion", "equals": True, "reason": "CPP"}],
            "l3": [{"field": "recurrence_count", "min": 1, "reason": "반복"}],
        },
        sop_reference="QA-SOP-000 Rev.00 (test)",
    )
    check_rules(r)
    d = dev("DEV-2026-2201")
    n = len(find_recurrence(d, HISTORY, r, TODAY))
    level, reasons = propose_class(d, r, n)
    assert level == "l2" and reasons == ["CPP"]
    md = render_markdown(d, level, reasons, [], [], "2026-11-24", rules=r,
                         also=lower_triggers(d, r, n))
    assert "제안 등급: 주요(2등급)" in md
    assert "[경미(3등급)] 반복" in md
    assert "QA-SOP-000 Rev.00 (test)" in md
    level, _ = propose_class(dev("DEV-2026-2203"), r, 0)
    assert level == "l4"


def test_missing_sop_reference_is_flagged_in_draft():
    d = dev("DEV-2026-2203")
    md = render_markdown(d, "minor", ["x"], [], [], "2026-11-24", rules=rules_with(sop_reference=""))
    line = [l for l in md.splitlines() if l.startswith("분류 기준 출처")][0]
    assert "작성 필요" in line


def test_lower_level_triggers_are_not_hidden():
    d = dev("DEV-2026-2202")  # critical, but also other_batches_possibly_affected (major)
    assert lower_triggers(d, RULES, 0) == [("major", "다른 배치 영향 가능성")]
    md = (ROOT / "sample_output/DEV-2026-2202_draft.md").read_text(encoding="utf-8")
    assert "[MAJOR] 다른 배치 영향 가능성" in md


def test_recurrence_text_follows_window_days():
    r = rules_with(recurrence={"window_days": 180, "match_on": ["equipment_id", "category"]})
    d = dev("DEV-2026-2201")
    md = render_markdown(d, "major", ["x"], [], [], "2026-11-24", rules=r)
    assert "최근 180일" in md and "12개월" not in md


def test_match_on_site_excludes_other_site_same_equipment_id():
    d = dev("DEV-2026-2201")  # Plant A
    any_site = rules_with(recurrence={"window_days": 365, "match_on": ["equipment_id", "category"]})
    both = find_recurrence(d, HISTORY, any_site, TODAY)
    same_site = find_recurrence(d, HISTORY, RULES, TODAY)
    assert {h["site"] for h in both} == {"Plant A", "Plant B"}
    assert {h["site"] for h in same_site} == {"Plant A"}
    assert len(same_site) == len(both) - 1


def test_recurrence_trigger_can_sit_at_any_level():
    r = copy.deepcopy(RULES)
    r["classes"]["critical"].append({"field": "recurrence_count", "min": 5, "reason": "5회 이상 반복"})
    level, reasons = propose_class(dev("DEV-2026-2201"), r, 6)
    assert level == "critical" and any("5회 이상" in x for x in reasons)


@pytest.mark.parametrize("mutate, needle", [
    (lambda r: r["classes"].__setitem__("minor", [{"field": "_default", "reason": "x"}]), "default_level"),
    (lambda r: r["classes"]["major"][-1].__setitem__("field", "recurrence_12m"), "recurrence_count"),
    (lambda r: r["classes"].__setitem__("severe", []), "severe"),
    (lambda r: r.__setitem__("default_level", "low"), "default_level"),
    (lambda r: r.__setitem__("default_reason", ""), "default_reason"),
    (lambda r: r["classes"]["major"][0].__setitem__("equals", "true"), "true 또는 false"),
    (lambda r: r["classes"]["major"][0].__setitem__("equal", True), "알 수 없는 키"),
    (lambda r: r["classes"]["major"][0].__setitem__("min", 1), "하나만"),
    (lambda r: r["classes"]["major"].append({"field": "cpp_excursion", "min": 2, "reason": "x"}), "min 은"),
    (lambda r: r["classes"]["major"][-1].__setitem__("min", 0), "1 이상"),
    (lambda r: r["recurrence"].__setitem__("window_days", 0), "window_days"),
    (lambda r: r["recurrence"].__setitem__("match_on", ["batch"]), "match_on"),
    (lambda r: r["levels"].append({"id": "major"}), "중복"),
    (lambda r: r.pop("levels"), "levels"),
])
def test_rules_mistakes_stop_the_run(mutate, needle):
    r = copy.deepcopy(RULES)
    mutate(r)
    with pytest.raises(RulesError) as e:
        check_rules(r)
    assert needle in str(e.value)


def test_cli_exits_on_bad_rules(tmp_path):
    bad = tmp_path / "rules.yaml"
    r = copy.deepcopy(RULES)
    r["default_level"] = "nope"
    bad.write_text(yaml.safe_dump(r, allow_unicode=True), encoding="utf-8")
    p = subprocess.run(["python", "-m", "devdraft.cli", str(INTAKE / "DEV-2026-2203.yaml"),
                        "--rules", str(bad), "--out", str(tmp_path / "o")],
                       cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 2 and "RULES ERR" in p.stdout
    assert not (tmp_path / "o").exists()


# --- guard rails not covered earlier ----------------------------------------

import ast  # noqa: E402

ALLOWED_IMPORTS = {"__future__", "argparse", "ast", "csv", "dataclasses", "datetime",
                   "hashlib", "pathlib", "re", "yaml", "docx"}


def test_package_imports_nothing_that_can_reach_a_network_or_llm():
    for py in (ROOT / "devdraft").glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [node.module.split(".")[0]]
            else:
                continue
            for m in mods:
                assert m in ALLOWED_IMPORTS, f"{py.name}: import {m}"


def test_capa_and_review_fields_stay_blank():
    d = dev("DEV-2026-2201")
    md = render_markdown(d, "major", ["x"], [], investigation_plan(d, RULES), "2026-11-24", rules=RULES)
    capa = md.split("## 8. CAPA", 1)[1].split("##", 1)[0]
    assert capa.count("작성 필요") == 3
    plan = md.split("## 5. 조사 계획", 1)[1].split("##", 1)[0]
    assert plan.count("작성 필요") == len(RULES["ishikawa"])
    assert "QA 검토자 확정 등급:** ☐ **작성 필요" in md


def test_docx_keeps_placeholders(tmp_path):
    from docx import Document
    build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml",
          ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_docx=True)
    doc = Document(tmp_path / "DEV-2026-2201_draft.docx")
    text = [p.text for p in doc.paragraphs] + [c.text for t in doc.tables for row in t.rows for c in row.cells]
    joined = "\n".join(text)
    assert joined.count("작성 필요") >= 3 + len(RULES["ishikawa"]) + 4
    assert "승인 문서가 아닙니다" in joined


# --- strict booleans (YAML 1.1 yes/no/on/off are NOT booleans here) ---------

import re  # noqa: E402

from devdraft.rules import strict_load  # noqa: E402


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "Yes", "NO", "y", "n"])
def test_unquoted_yes_no_flag_is_rejected(tmp_path, word):
    text = (INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8")
    text = text.replace("spec_oos: false", f"spec_oos: {word}")
    p = tmp_path / "f.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "spec_oos" in str(e.value) and "true/false" in str(e.value)


@pytest.mark.parametrize("word, value", [("true", True), ("True", True), ("TRUE", True),
                                         ("false", False), ("False", False), ("FALSE", False)])
def test_true_false_spellings_are_booleans(word, value):
    assert strict_load(f"x: {word}")["x"] is value


def test_strict_loader_keeps_other_scalars():
    d = strict_load("a: no\nb: '3.62'\nc: 2026-11-21T14:20\nd: N/A\n")
    assert d == {"a": "no", "b": "3.62", "c": "2026-11-21T14:20", "d": "N/A"}


def test_rules_equals_yes_is_rejected(tmp_path):
    text = (ROOT / "config/rules.yaml").read_text(encoding="utf-8")
    assert "\n      equals: true\n" in text
    text = text.replace("\n      equals: true\n", "\n      equals: yes\n", 1)
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(RulesError) as e:
        load_rules(p)
    assert "true 또는 false" in str(e.value)


# --- exit codes -------------------------------------------------------------

def _cli(*args, cwd=ROOT):
    return subprocess.run(["python", "-m", "devdraft.cli", *map(str, args)],
                          cwd=cwd, capture_output=True, text=True)


def test_exit_code_0_when_every_form_drafted(tmp_path):
    p = _cli(INTAKE / "DEV-2026-2201.yaml", INTAKE / "DEV-2026-2203.yaml", "--out", tmp_path, "--today", "2026-11-24")
    assert p.returncode == 0, p.stdout


def test_exit_code_1_when_any_form_rejected_but_others_still_drafted(tmp_path):
    p = _cli(*sorted(INTAKE.glob("*.yaml")), "--out", tmp_path, "--today", "2026-11-24")
    assert p.returncode == 1
    assert len(list(tmp_path.glob("*_draft.md"))) == 3


# (exit code 2 for invalid rules: test_cli_exits_on_bad_rules)


# --- past root causes hidden by default ---------------------------------------

def test_recurrence_table_hides_root_cause_by_default():
    assert RULES["recurrence"]["show_root_cause"] is False
    md = (ROOT / "sample_output/DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    sec = md.split("## 4. 반복성 검토", 1)[1].split("##", 1)[0]
    assert "DEV-2026-1100" in sec
    for rc in {r["root_cause"] for r in HISTORY}:
        assert rc not in sec, rc
    assert "근본원인" not in sec


def test_recurrence_table_shows_root_cause_when_enabled():
    r = copy.deepcopy(RULES)
    r["recurrence"]["show_root_cause"] = True
    d = dev("DEV-2026-2201")
    rec = find_recurrence(d, HISTORY, r, TODAY)
    md = render_markdown(d, "major", ["x"], rec, [], "2026-11-24", rules=r)
    assert "근본원인 (당시 기록)" in md and "procedure gap" in md


def test_history_without_root_cause_column_works_when_hidden():
    rows = [{k: v for k, v in h.items() if k != "root_cause"} for h in HISTORY]
    d = dev("DEV-2026-2201")
    rec = find_recurrence(d, rows, RULES, TODAY)
    md = render_markdown(d, "major", ["x"], rec, [], "2026-11-24", rules=RULES)
    assert "DEV-2026-1100" in md


def test_show_root_cause_must_be_boolean():
    r = copy.deepcopy(RULES)
    r["recurrence"]["show_root_cause"] = "no"
    with pytest.raises(RulesError):
        check_rules(r)


# --- decision log format ------------------------------------------------------

DECISION_LINE = re.compile(r"^- \[\d{4}-\d{2}-\d{2}\] .+ — .+ — .+ — \((확인 필요|확인 불필요)\)$")


def test_decisions_log_format():
    lines = [l for l in (ROOT / "DECISIONS.md").read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    assert lines
    bad = [l for l in lines if not DECISION_LINE.match(l)]
    assert not bad, "\n".join(bad)


# --- template comment glued to a value ---------------------------------------

def _filled_template_text():
    t = TEMPLATE.read_text(encoding="utf-8")
    src = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    for k, v in src.items():
        if k in ("synthetic", "parameters"):
            continue
        val = ("true" if v else "false") if isinstance(v, bool) else f"'{v}'"
        t = re.sub(rf"^{k}:( *)(''|)( *)#", lambda m: f"{k}: {val}  #", t, count=1, flags=re.M)
    return t


def test_template_filled_with_spaces_before_comments_is_accepted(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(_filled_template_text(), encoding="utf-8")
    d = load(p, RULES)
    assert d.title == "배치 기록서 서명 누락 (원료 칭량 단계)"


@pytest.mark.parametrize("key, glued", [
    ("title", "title: 서명 누락# [필수] 한 줄 제목. 무엇이 기준과 달랐는지."),
    ("spec_oos", "spec_oos: false# 규격 이탈(OOS) 시험 결과가 있는가"),
])
def test_comment_glued_to_value_is_rejected(tmp_path, key, glued):
    text = re.sub(rf"^{key}:.*$", glued, _filled_template_text(), count=1, flags=re.M)
    p = tmp_path / "f.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "양식 주석이 붙어" in str(e.value) and key in str(e.value)


def test_hash_inside_real_value_is_not_flagged(tmp_path):
    text = re.sub(r"^description:.*$", "description: 'lot#5531 사용, 포트#4 확인'", _filled_template_text(),
                  count=1, flags=re.M)
    p = tmp_path / "f.yaml"
    p.write_text(text, encoding="utf-8")
    assert "lot#5531" in load(p, RULES).description


def test_shipped_rules_match_recurrence_within_same_site():
    assert "site" in RULES["recurrence"]["match_on"]
    hits = find_recurrence(dev("DEV-2026-2201"), HISTORY, RULES, TODAY)
    assert hits and {h["site"] for h in hits} == {"Plant A"}
    assert "DEV-2026-1023" not in {h["dev_id"] for h in hits}  # Plant B, same equipment ID


# --- history CSV checks (QMS exports) ----------------------------------------

from devdraft.history import HistoryError, check_history, load_checked_history  # noqa: E402

HIST_SRC = (ROOT / "data/synthetic/history.csv").read_text(encoding="utf-8")


def _hist(tmp_path, text, encoding="utf-8", name="h.csv"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def test_synthetic_history_is_clean():
    rep = check_history(ROOT / "data/synthetic/history.csv", RULES, TODAY)
    assert rep.ok and not rep.warnings and len(rep.rows) == len(HISTORY)


def test_excel_bom_keeps_dev_id(tmp_path):
    """Excel 'CSV UTF-8' adds a BOM; IDs must not silently go blank."""
    p = _hist(tmp_path, HIST_SRC, encoding="utf-8-sig")
    rep = check_history(p, RULES, TODAY)
    assert rep.ok
    md = build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml", p, tmp_path / "o", TODAY).read_text(encoding="utf-8")
    assert "| DEV-2026-1100 |" in md


def test_non_utf8_history_is_an_error(tmp_path):
    p = tmp_path / "h.csv"
    p.write_bytes(HIST_SRC.replace("Plant A", "공장 A").encode("cp949"))
    with pytest.raises(HistoryError) as e:
        check_history(p, RULES, TODAY)
    assert "UTF-8" in str(e.value)


def test_missing_column_is_an_error(tmp_path):
    p = _hist(tmp_path, HIST_SRC.replace("equipment_id", "equipment", 1))
    rep = check_history(p, RULES, TODAY)
    assert not rep.ok and "equipment_id" in rep.errors[0]


def test_root_cause_column_required_only_when_shown(tmp_path):
    lines = [",".join(c for i, c in enumerate(l.split(",")) if i != 6) for l in HIST_SRC.splitlines()]
    p = _hist(tmp_path, "\n".join(lines) + "\n")
    assert check_history(p, RULES, TODAY).ok
    r = copy.deepcopy(RULES)
    r["recurrence"]["show_root_cause"] = True
    assert not check_history(p, r, TODAY).ok


@pytest.mark.parametrize("bad", ["2026/10/21", "21-10-2026", "", "2026-13-01"])
def test_bad_date_is_an_error_with_line_number(tmp_path, bad):
    p = _hist(tmp_path, HIST_SRC.replace("2026-10-21", bad, 1))
    rep = check_history(p, RULES, TODAY)
    assert not rep.ok
    line = HIST_SRC.splitlines().index(next(l for l in HIST_SRC.splitlines() if "2026-10-21" in l)) + 1
    assert any(e.startswith(f"{line}행: opened") for e in rep.errors)


def test_duplicate_dev_id_is_an_error(tmp_path):
    dup = next(l for l in HIST_SRC.splitlines() if l.startswith("DEV-2026-1100"))
    p = _hist(tmp_path, HIST_SRC + dup + "\n")
    rep = check_history(p, RULES, TODAY)
    assert not rep.ok and any("중복" in e for e in rep.errors)


def test_history_error_stops_run_with_exit_2(tmp_path):
    p = _hist(tmp_path, HIST_SRC.replace("2026-10-21", "2026/10/21", 1))
    r = _cli(INTAKE / "DEV-2026-2201.yaml", "--history", p, "--out", tmp_path / "o", "--today", "2026-11-24")
    assert r.returncode == 2 and "HISTORY ERR" in r.stdout and "Traceback" not in r.stderr
    assert not (tmp_path / "o").exists()


def test_future_dated_rows_are_not_counted(tmp_path):
    extra = "DEV-2026-9999,2026-12-30,Plant A,CHR-03,process_parameter,major,x,True\n"
    p = _hist(tmp_path, HIST_SRC + extra)
    rep = check_history(p, RULES, TODAY)
    assert rep.ok and any("기준일" in w for w in rep.warnings)
    hits = find_recurrence(dev("DEV-2026-2201"), rep.rows, RULES, TODAY)
    assert "DEV-2026-9999" not in {h["dev_id"] for h in hits}


def test_deviation_itself_in_history_is_not_its_own_recurrence(tmp_path):
    extra = "DEV-2026-2201,2026-11-21,Plant A,CHR-03,process_parameter,major,x,True\n"
    p = _hist(tmp_path, HIST_SRC + extra)
    md = build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml", p, tmp_path / "o", TODAY).read_text(encoding="utf-8")
    sec = md.split("## 4. 반복성 검토", 1)[1].split("##", 1)[0]
    assert "건 5건" in sec and "| DEV-2026-2201 |" not in sec
    assert "자체가 있어 반복 건에서 제외" in sec


def test_unknown_category_and_class_are_warnings(tmp_path):
    p = _hist(tmp_path, HIST_SRC + "DEV-2026-9998,2026-03-01,Plant A,CHR-03,cleaning,grade2,x,True\n")
    rep = check_history(p, RULES, TODAY)
    assert rep.ok
    assert any("category 'cleaning'" in w for w in rep.warnings)
    assert any("final_class 'grade2'" in w for w in rep.warnings)


def test_blank_match_key_is_a_warning(tmp_path):
    p = _hist(tmp_path, HIST_SRC + "DEV-2026-9997,2026-03-01,,CHR-03,process_parameter,minor,x,True\n")
    rep = check_history(p, RULES, TODAY)
    assert rep.ok and any("site 비어 있음" in w for w in rep.warnings)


def test_check_history_cli(tmp_path):
    ok = _cli("--check-history", "--today", "2026-11-24")
    assert ok.returncode == 0 and "사용 가능" in ok.stdout
    bad = _hist(tmp_path, HIST_SRC.replace("2026-10-21", "2026/10/21", 1))
    r = _cli("--check-history", "--history", bad, "--today", "2026-11-24")
    assert r.returncode == 1 and "ERR" in r.stdout and "사용 불가" in r.stdout
    missing = _cli("--check-history", "--history", tmp_path / "nope.csv")
    assert missing.returncode == 2


def test_cli_without_forms_or_check_is_usage_error():
    r = _cli()
    assert r.returncode == 2 and "입력 양식" in r.stderr


def test_bad_today_is_usage_error_not_traceback():
    r = _cli(INTAKE / "DEV-2026-2201.yaml", "--today", "2026/11/24")
    assert r.returncode == 2 and "YYYY-MM-DD" in r.stderr and "Traceback" not in r.stderr


# --- synthetic SOP -> rules.yaml worked example ------------------------------

SOP_MD = ROOT / "data/synthetic/sop/SYN-QA-SOP-001.md"
SOP_RULES = ROOT / "config/examples/rules_SYN-QA-SOP-001.yaml"


def _sop_clauses():
    return re.findall(r"^\*\*(\d+(?:\.\d+)+)\*\*", SOP_MD.read_text(encoding="utf-8"), flags=re.M)


def test_example_sop_is_marked_synthetic():
    text = SOP_MD.read_text(encoding="utf-8")
    assert "합성" in text.splitlines()[0] and "실제 사업장의 절차가 아닙니다" in text
    assert "실제 SOP 아님" in load_rules(SOP_RULES)["sop_reference"]


def test_example_sop_every_clause_is_traced():
    """Each SOP clause appears in the rules file: as a trigger reason, a manual
    check, or an explained comment. A new SOP clause without a decision fails."""
    clauses = _sop_clauses()
    assert len(clauses) >= 10
    text = SOP_RULES.read_text(encoding="utf-8")
    untraced = [c for c in clauses if not re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text)]
    assert not untraced, untraced


def test_example_sop_reasons_cite_clauses():
    r = load_rules(SOP_RULES)
    for triggers in r["classes"].values():
        for t in triggers:
            assert re.search(r"\(SOP \d+(\.\d+)+\)$", t["reason"]), t["reason"]
    assert re.search(r"\(SOP \d+(\.\d+)+\)$", r["default_reason"])


@pytest.mark.parametrize("name, level, clause, count", [
    ("DEV-2026-2201", "critical", "5.5.1", 5),   # CPP -> major, but 5 repeats in 2 years -> critical
    ("DEV-2026-2202", "critical", "5.2.1", 1),
    ("DEV-2026-2203", "minor", "5.4.1", 0),
])
def test_example_sop_classifies_samples(name, level, clause, count):
    r = load_rules(SOP_RULES)
    d = load(INTAKE / f"{name}.yaml", r)
    n = len(find_recurrence(d, HISTORY, r, TODAY))
    got, reasons = propose_class(d, r, n)
    assert (got, n) == (level, count)
    assert any(f"(SOP {clause})" in x for x in reasons)


def test_example_sop_escalation_keeps_lower_triggers_visible(tmp_path):
    md = build(INTAKE / "DEV-2026-2201.yaml", SOP_RULES, ROOT / "data/synthetic/history.csv",
               tmp_path, TODAY).read_text(encoding="utf-8")
    assert "제안 등급: 중대 (Critical)" in md
    for c in ("5.3.1", "5.3.3", "5.3.4"):
        assert f"(SOP {c})" in md.split("그 밖에 해당한 트리거", 1)[1].split("분류 기준 출처", 1)[0]


def test_unmapped_sop_clause_is_shown_as_reviewer_check(tmp_path):
    p = build(INTAKE / "DEV-2026-2201.yaml", SOP_RULES, ROOT / "data/synthetic/history.csv",
              tmp_path, TODAY, want_docx=True)
    md = p.read_text(encoding="utf-8")
    sec = md.split("## 3. 분류", 1)[1].split("## 4.", 1)[0]
    assert "검토자가 직접 확인" in sec and "☐ SOP 5.5.2" in sec
    from docx import Document
    doc = Document(tmp_path / "DEV-2026-2201_draft.docx")
    assert any("SOP 5.5.2" in x.text for x in doc.paragraphs)


def test_no_manual_checks_section_when_empty():
    assert RULES["manual_checks"] == []
    md = (ROOT / "sample_output/DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    assert "검토자가 직접 확인" not in md


@pytest.mark.parametrize("bad", [
    "x", [{"clause": "5.5.2"}], [{"clause": "", "text": "t"}], [{"clause": "1", "text": "t", "level": "major"}],
])
def test_malformed_manual_checks_stop_the_run(bad):
    r = copy.deepcopy(RULES)
    r["manual_checks"] = bad
    with pytest.raises(RulesError) as e:
        check_rules(r)
    assert "manual_checks" in str(e.value)


def test_example_sop_history_check_is_clean():
    rep = check_history(ROOT / "data/synthetic/history.csv", load_rules(SOP_RULES), TODAY)
    assert rep.ok and not rep.warnings


# --- Word output: a reviewer can't mistake the draft or miss a blank ---------

from docx import Document as _Document  # noqa: E402
from docx.enum.text import WD_COLOR_INDEX  # noqa: E402
from docx.oxml.ns import qn as _qn  # noqa: E402

from devdraft.docx_out import _add_inline, markdown_to_docx  # noqa: E402


@pytest.fixture(scope="module")
def sop_docx(tmp_path_factory):
    out = tmp_path_factory.mktemp("docx")
    md_path = build(INTAKE / "DEV-2026-2201.yaml", SOP_RULES, ROOT / "data/synthetic/history.csv",
                    out, TODAY, want_docx=True)
    return md_path.read_text(encoding="utf-8"), _Document(out / "DEV-2026-2201_draft.docx")


def _all_paragraphs(doc):
    yield from doc.paragraphs
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def test_docx_every_blank_is_boxed_bold_and_highlighted(sop_docx):
    md, doc = sop_docx
    runs = [r for p in _all_paragraphs(doc) for r in p.runs if BLANK_TEXT in r.text]
    assert len(runs) == md.count(BLANK_TEXT)
    for r in runs:
        assert r.text.startswith("☐") and r.bold and r.font.highlight_color == WD_COLOR_INDEX.YELLOW, r.text


BLANK_TEXT = "작성 필요"


def test_docx_manual_check_box_is_highlighted(sop_docx):
    _, doc = sop_docx
    p = next(p for p in doc.paragraphs if "SOP 5.5.2" in p.text)
    box = next(r for r in p.runs if r.text.startswith("☐"))
    assert box.font.highlight_color == WD_COLOR_INDEX.YELLOW


def test_docx_every_page_says_draft(sop_docx):
    _, doc = sop_docx
    for sec in doc.sections:
        head = " ".join(p.text for p in sec.header.paragraphs)
        assert "초안 — 승인 문서 아님" in head and "DEV-2026-2201" in head and "2026-11-24" in head
        foot_xml = sec.footer._element.xml
        assert "PAGE" in foot_xml and "NUMPAGES" in foot_xml


def test_docx_banner_is_a_shaded_box(sop_docx):
    _, doc = sop_docx
    cell = doc.tables[0].rows[0].cells[0]
    assert "승인 문서가 아닙니다" in cell.text
    assert cell._tc.tcPr.find(_qn("w:shd")) is not None
    assert cell.paragraphs[0].runs[0].bold


def test_docx_table_headers_repeat_and_are_shaded(sop_docx):
    _, doc = sop_docx
    data_tables = [t for t in doc.tables[1:]]
    assert len(data_tables) >= 5
    for t in data_tables:
        first = t.rows[0]
        assert first._tr.trPr.find(_qn("w:tblHeader")) is not None
        assert first.cells[0]._tc.tcPr.find(_qn("w:shd")) is not None


def test_docx_has_no_raw_markdown(sop_docx):
    _, doc = sop_docx
    for p in _all_paragraphs(doc):
        assert "**" not in p.text and "`" not in p.text, p.text
        assert not p.text.startswith("*"), p.text


def test_docx_joins_wrapped_markdown_lines_into_one_paragraph(sop_docx):
    _, doc = sop_docx
    hits = [p for p in doc.paragraphs if "자동 생성되었습니다" in p.text]
    assert len(hits) == 1 and "조사 결과나 결론을 생성하지 않습니다" in hits[0].text
    assert all(r.italic for r in hits[0].runs if r.text.strip())


def test_docx_sets_korean_font():
    doc = _Document()
    from devdraft.docx_out import _style
    _style(doc)
    fonts = doc.styles["Normal"].element.rPr.find(_qn("w:rFonts"))
    assert fonts.get(_qn("w:eastAsia")) == "Malgun Gothic"


def test_inline_markdown_to_runs():
    doc = _Document()
    p = doc.add_paragraph()
    _add_inline(p, "a **b** `c` *d `e`* ☐ **작성 필요** f")
    got = [(r.text, bool(r.bold), bool(r.italic)) for r in p.runs]
    assert ("b", True, False) in got and ("c", False, False) in got
    assert ("d ", False, True) in got and ("e", False, True) in got
    assert ("☐ 작성 필요", True, False) in got
    assert p.text == "a b c d e ☐ 작성 필요 f"


def test_markdown_to_docx_on_default_rules_sample(tmp_path):
    md = (ROOT / "sample_output/DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    doc = _Document(markdown_to_docx(md, tmp_path / "x.docx"))
    text = "\n".join(p.text for p in _all_paragraphs(doc))
    assert text.count(BLANK_TEXT) == md.count(BLANK_TEXT)
    assert "DEV-2026-2203" in doc.sections[0].header.paragraphs[0].text


# --- public SOP example: Duke COMM-PAS-013 --------------------------------------

DUKE_RULES = ROOT / "config/examples/rules_Duke_COMM-PAS-013.yaml"
DUKE_MAP = ROOT / "docs/sop_mapping/Duke_COMM-PAS-013.md"


def _duke_mapped_clauses():
    return re.findall(r"^\| (\d+(?:\.\d+)+) \|", DUKE_MAP.read_text(encoding="utf-8"), flags=re.M)


def test_duke_mapping_doc_cites_source_and_disclaims():
    text = DUKE_MAP.read_text(encoding="utf-8")
    assert "Revision 01" in text and "01 Jul 2025" in text
    assert "COMM-PAS-013%20Deviations%20and%20Investigations.pdf" in text
    assert "Duke University와 관련이 없고" in text and "원문은 저장소에 복사하지 않았습니다" in text


def test_duke_every_mapped_clause_is_in_rules():
    clauses = _duke_mapped_clauses()
    assert {"3.4", "4.26", "8.4.2", "8.4.3.1", "8.8.1.2"} <= set(clauses)
    text = DUKE_RULES.read_text(encoding="utf-8")
    missing = [c for c in clauses if not re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text)]
    assert not missing, missing


def test_duke_manual_checks_are_all_in_mapping_doc():
    r = load_rules(DUKE_RULES)
    assert {m["clause"] for m in r["manual_checks"]} <= set(_duke_mapped_clauses())


def test_duke_invents_no_severity_tiers():
    """The SOP has no Critical/Major/Minor; the tool must not add them."""
    r = load_rules(DUKE_RULES)
    ids = {lv["id"] for lv in r["levels"]}
    labels = " ".join(lv["label"] for lv in r["levels"]).lower()
    assert ids == {"repeat", "not_repeat"}
    assert not ({"critical", "major", "minor"} & ids) and "critical" not in labels
    triggers = [t for ts in r["classes"].values() for t in ts]
    assert triggers and all(t["field"] == "recurrence_count" for t in triggers)
    assert r["recurrence"]["window_days"] == 730


@pytest.mark.parametrize("name, level, hits", [
    ("DEV-2026-2201", "repeat", {"DEV-2026-1100", "DEV-2026-1003", "DEV-2026-1101", "DEV-2026-1025", "DEV-2026-1102"}),
    ("DEV-2026-2202", "repeat", {"DEV-2025-1022"}),  # outside 365 days, inside 2 years
    ("DEV-2026-2203", "not_repeat", set()),
])
def test_duke_repeat_deviation_on_samples(name, level, hits):
    r = load_rules(DUKE_RULES)
    d = load(INTAKE / f"{name}.yaml", r)
    rec = find_recurrence(d, HISTORY, r, TODAY)
    assert {h["dev_id"] for h in rec} == hits
    assert propose_class(d, r, len(rec))[0] == level


def test_duke_draft_leaves_risk_scoring_to_reviewer(tmp_path):
    md = build(INTAKE / "DEV-2026-2202.yaml", DUKE_RULES, ROOT / "data/synthetic/history.csv",
               tmp_path, TODAY).read_text(encoding="utf-8")
    sec = md.split("## 3. 분류", 1)[1].split("## 4.", 1)[0]
    for c in ("3.4", "8.4.2", "8.4.2.1", "8.4.3.1", "8.8.1.2", "3.7.2.1"):
        assert f"☐ SOP {c}:" in sec
    assert "도구는 점수를 매기지 않음" in sec
    assert not re.search(r"(Score|점수)\s*[:=]\s*\d", md)  # no score filled in by the tool
    assert "Duke COMM-PAS-013 Rev 01" in sec and "Duke와 무관" in sec


def test_duke_history_check_has_no_noise():
    rep = check_history(ROOT / "data/synthetic/history.csv", load_rules(DUKE_RULES), TODAY)
    assert rep.ok and not rep.warnings


def test_history_class_labels_silences_only_listed_values(tmp_path):
    r = copy.deepcopy(RULES)
    r["levels"] = [{"id": "a", "label": "A"}]
    r["default_level"] = "a"
    r["classes"] = {}
    present = {h["final_class"] for h in HISTORY}
    assert len(present) >= 2
    rep = check_history(ROOT / "data/synthetic/history.csv", r, TODAY)
    assert {w.split("'")[1] for w in rep.warnings if w.startswith("final_class")} == present
    keep = sorted(present)[0]
    r["history_class_labels"] = sorted(present - {keep})
    rep = check_history(ROOT / "data/synthetic/history.csv", r, TODAY)
    assert [w.split("'")[1] for w in rep.warnings if w.startswith("final_class")] == [keep]


@pytest.mark.parametrize("bad", ["major", [""], [1]])
def test_history_class_labels_must_be_strings(bad):
    r = copy.deepcopy(RULES)
    r["history_class_labels"] = bad
    with pytest.raises(RulesError):
        check_rules(r)
# --- provenance and synthetic-data guard ---------------------------------------

import hashlib  # noqa: E402

from devdraft import __version__  # noqa: E402


def _real_copy(tmp_path, name="DEV-2026-2201"):
    """Same form without `synthetic: true`, i.e. what a real form looks like."""
    text = (INTAKE / f"{name}.yaml").read_text(encoding="utf-8")
    p = tmp_path / f"{name}_real.yaml"
    p.write_text("\n".join(l for l in text.splitlines() if not l.startswith("synthetic:")) + "\n", encoding="utf-8")
    return p


def _real_history(tmp_path):
    rows = list(csv.DictReader(open(ROOT / "data/synthetic/history.csv", encoding="utf-8")))
    for r in rows:
        r["synthetic"] = "False"
    p = tmp_path / "qms_export.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return p


import csv  # noqa: E402


def test_real_form_with_synthetic_history_is_rejected(tmp_path):
    with pytest.raises(IntakeError) as e:
        build(_real_copy(tmp_path), ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
              tmp_path / "o", TODAY)
    assert "합성" in str(e.value) and "--history" in str(e.value)
    assert not (tmp_path / "o").exists() or not list((tmp_path / "o").glob("*_draft.md"))


def test_real_form_with_real_history_has_no_synthetic_marks(tmp_path):
    md = build(_real_copy(tmp_path), ROOT / "config/rules.yaml", _real_history(tmp_path),
               tmp_path / "o", TODAY, want_docx=True).read_text(encoding="utf-8")
    assert "합성" not in md
    doc = _Document(tmp_path / "o" / "DEV-2026-2201_draft.docx")
    assert "합성" not in doc.sections[0].header.paragraphs[0].text


def test_synthetic_draft_is_marked_in_md_docx_and_summary(tmp_path):
    results, summary = run_batch([INTAKE / "DEV-2026-2203.yaml"], ROOT / "config/rules.yaml",
                                 ROOT / "data/synthetic/history.csv", tmp_path, TODAY,
                                 want_docx=True, want_summary=True)
    md = (tmp_path / "DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    assert md.splitlines()[2].startswith("> **합성(가짜) 데이터로 만든 초안")
    head = _Document(tmp_path / "DEV-2026-2203_draft.docx").sections[0].header.paragraphs[0].text
    assert head.startswith("합성 데이터 — 실제 문서 아님")
    assert "합성(가짜) 데이터로 만든 초안이 포함" in summary.read_text(encoding="utf-8")


def test_footer_names_the_actual_input_file(tmp_path):
    src = tmp_path / "칭량_서명누락_v2.yaml"
    src.write_bytes((INTAKE / "DEV-2026-2203.yaml").read_bytes())
    md = build(src, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY).read_text(encoding="utf-8")
    assert "`칭량_서명누락_v2.yaml`" in md and "`DEV-2026-2203.yaml`" not in md


def test_provenance_hashes_match_files(tmp_path):
    form, hist = _real_copy(tmp_path), _real_history(tmp_path)
    rules = SOP_RULES
    md = build(form, rules, hist, tmp_path / "o", TODAY).read_text(encoding="utf-8")
    sec = md.split("## 부록. 생성 근거", 1)[1]
    for p in (form, rules, hist):
        assert f"{p.name} (SHA-256 {hashlib.sha256(p.read_bytes()).hexdigest()}" in sec
    assert "SYN-QA-SOP-001 Rev.01" in sec and "| 기준일 | 2026-11-24 |" in sec
    assert f"devdraft {__version__}" in sec and f"{len(HISTORY)}행)" in sec


def test_provenance_marks_synthetic_history():
    md = (ROOT / "sample_output/DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    assert "행, 합성 데이터)" in md.split("## 부록. 생성 근거", 1)[1]


def test_same_inputs_give_identical_draft(tmp_path):
    a = build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path / "a", TODAY).read_bytes()
    b = build(INTAKE / "DEV-2026-2201.yaml", ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path / "b", TODAY).read_bytes()
    assert a == b


def test_sample_output_is_up_to_date(tmp_path):
    """sample_output/ must be what the current code produces (README links to it)."""
    run_batch(sorted(INTAKE.glob("*.yaml")), ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_summary=True)
    for f in tmp_path.glob("*.md"):
        assert f.read_text(encoding="utf-8") == (ROOT / "sample_output" / f.name).read_text(encoding="utf-8"), \
            f"{f.name} is stale — regenerate with: python -m devdraft.cli data/synthetic/intake/*.yaml " \
            "--summary --today 2026-11-24 --out sample_output"


# --- terminology: "deviation" everywhere (old Korean term removed) --------------

def test_terminology_uses_deviation_everywhere(tmp_path):
    """Project decision: the term is "deviation" in all output and docs."""
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if not tracked:
        pytest.skip("not a git checkout")
    old = "일" + "탈"  # split so this test file itself doesn't match
    hits = [f for f in tracked
            if (f.endswith((".py", ".md", ".yaml", ".csv", ".txt")) or f == ".gitignore")
            and f != "DECISIONS.md"  # the change log names the old term on purpose
            if old in (ROOT / f).read_text(encoding="utf-8", errors="ignore")]
    assert not hits, hits
    results, summary = run_batch([INTAKE / "DEV-2026-2201.yaml"], ROOT / "config/rules.yaml",
                                 ROOT / "data/synthetic/history.csv", tmp_path, TODAY,
                                 want_docx=True, want_summary=True)
    md = (tmp_path / "DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    assert md.startswith("# Deviation 보고서 초안 — DEV-2026-2201")
    assert old not in md and old not in summary.read_text(encoding="utf-8")
    doc = _Document(tmp_path / "DEV-2026-2201_draft.docx")
    assert old not in "\n".join(p.text for p in _all_paragraphs(doc))
