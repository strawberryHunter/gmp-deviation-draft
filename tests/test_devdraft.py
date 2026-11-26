from datetime import date
from pathlib import Path

import pytest
import yaml

from devdraft.classify import find_recurrence, investigation_plan, load_history, propose_class
from devdraft.cli import build, run_batch
from devdraft.summary import FormResult, render_summary
from devdraft.draft import render_markdown
import subprocess
import sys

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
    for lvl in ("MAJOR (제안)", "CRITICAL (제안)", "MINOR (제안, 반복 기준 미평가)"):
        assert lvl in md
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
    p = _cli(INTAKE / "DEV-2026-2203.yaml", "--rules", bad, "--out", tmp_path / "o")
    assert p.returncode == 2 and "RULES ERR" in p.stdout
    assert not (tmp_path / "o").exists()


# --- guard rails not covered earlier ----------------------------------------

import ast  # noqa: E402

ALLOWED_IMPORTS = {"__future__", "argparse", "ast", "csv", "dataclasses", "datetime",
                   "glob", "hashlib", "io", "pathlib", "re", "sys", "types", "yaml", "docx", "openpyxl"}


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
    # The CLI writes Hangul as UTF-8 when the console can't encode it (English
    # Windows), so decode as UTF-8 rather than the platform locale (cp1252).
    return subprocess.run([sys.executable, "-m", "devdraft.cli", *map(str, args)],
                          cwd=cwd, capture_output=True, text=True, encoding="utf-8")


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


def test_cp949_history_is_read_with_a_warning(tmp_path):
    """User decision 2026-11-25: read Korean Excel's default "CSV" (CP949)."""
    p = tmp_path / "h.csv"
    p.write_bytes(HIST_SRC.replace("Plant A", "공장 A").encode("cp949"))
    rep = check_history(p, RULES, TODAY)
    assert rep.ok and any("CP949" in w for w in rep.warnings)
    assert {r["site"] for r in rep.rows} >= {"공장 A"}  # Korean decoded correctly, not garbled
    form = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    form["site"] = "공장 A"
    fp = tmp_path / "f.yaml"
    fp.write_text(yaml.safe_dump(form, allow_unicode=True), encoding="utf-8")
    hits = find_recurrence(load(fp, RULES), rep.rows, RULES, TODAY)
    assert len(hits) == 5  # same recurrences as the UTF-8 file with "Plant A"


def test_utf8_history_has_no_encoding_warning():
    rep = check_history(ROOT / "data/synthetic/history.csv", RULES, TODAY)
    assert not any("CP949" in w for w in rep.warnings)


def test_other_encoding_history_is_an_error(tmp_path):
    p = tmp_path / "h.csv"
    p.write_bytes(HIST_SRC.encode("utf-8").replace(b"Plant A", "Usine été A".encode("latin-1")))
    with pytest.raises(HistoryError) as e:
        check_history(p, RULES, TODAY)
    assert "UTF-8도 CP949도 아닙니다" in str(e.value)


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


def _twips(length):
    return round(length / 635)  # python-docx keeps lengths in EMU; 635 EMU = 1 twip (1/1440 inch)


def test_docx_page_is_a4_with_one_inch_margins(sop_docx):
    """The same sheet as the Word file of the browser screen (web/src/engine.js DOCX_TEXT_WIDTH):
    A4 210 x 297 mm = 11906 x 16838 twips, margins 1440 twips (25.4 mm) on every side."""
    _, doc = sop_docx
    sec = doc.sections[0]
    assert (_twips(sec.page_width), _twips(sec.page_height)) == (11906, 16838)
    assert [_twips(m) for m in (sec.top_margin, sec.bottom_margin, sec.left_margin, sec.right_margin)] == [1440] * 4
    text_width = 11906 - 2 * 1440
    engine = (ROOT / "web/src/engine.js").read_text(encoding="utf-8")
    assert "export const DOCX_TEXT_WIDTH = 11906 - 2 * 1440;" in engine
    for t in doc.tables:  # tables are laid out for that width (each column is rounded to a whole twip)
        grid = [int(c.get(_qn("w:w"))) for c in t._tbl.tblGrid.findall(_qn("w:gridCol"))]
        assert abs(sum(grid) - text_width) < len(grid), grid


def test_docx_table_rows_are_not_split_across_pages(sop_docx):
    _, doc = sop_docx
    rows = [r for t in doc.tables for r in t.rows]
    assert len(rows) > 20
    for r in rows:
        assert r._tr.trPr is not None and r._tr.trPr.find(_qn("w:cantSplit")) is not None, [c.text for c in r.cells]


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


def test_docx_headings_use_the_named_fonts_not_the_theme():
    """Opened in Word, headings came out in Calibri: the template's heading styles name the theme
    fonts as well, and Word follows the theme over the font names we set."""
    doc = _Document()
    from devdraft.docx_out import _style
    _style(doc)
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "List Bullet"):
        fonts = doc.styles[name].element.rPr.find(_qn("w:rFonts"))
        attrs = {k.split("}")[1]: v for k, v in fonts.attrib.items()}
        assert attrs == {"ascii": "Arial", "hAnsi": "Arial", "cs": "Arial", "eastAsia": "Malgun Gothic"}, (name, attrs)


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
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8").stdout.split()
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


# --- docs: relative links resolve ------------------------------------------------

@pytest.mark.parametrize("doc", ["README.md", "CLAUDE.md", "docs/HANDOFF.md", "docs/USAGE.md",
                                 "docs/TUTORIAL.md", "docs/sop_mapping/Duke_COMM-PAS-013.md"])
def test_relative_links_in_docs_resolve(doc):
    path = ROOT / doc
    text = path.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'src="([^"]+)"', text)
    broken = [l for l in links
              if not l.startswith(("http://", "https://", "#", "mailto:"))
              and not (path.parent / l.split("#", 1)[0]).exists()]
    assert not broken, broken


def test_handoff_has_user_todo_and_update_date():
    text = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    assert re.search(r"마지막 갱신: \d{4}-\d{2}-\d{2}", text)
    assert "## 3. 사용자가 해야 할 일" in text and "## 4. 다음 작업 후보" in text
    assert "docs/HANDOFF.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# --- console encodings (English / Korean Windows) ---------------------------------

import os  # noqa: E402
import sys  # noqa: E402


@pytest.mark.parametrize("enc", ["cp1252", "ascii", "cp949", "utf-8"])
def test_cli_messages_survive_console_encoding(tmp_path, enc):
    env = {**os.environ, "PYTHONIOENCODING": enc}
    p = subprocess.run([sys.executable, "-m", "devdraft.cli", str(INTAKE / "DEV-2026-2204.yaml"),
                        "--out", str(tmp_path)], cwd=ROOT, capture_output=True, env=env)
    assert p.returncode == 1, p.stderr.decode("utf-8", "replace")  # rejected form, not a crash
    assert b"Traceback" not in p.stderr
    shown = "utf-8"  # only UTF-8 can show every symbol the CLI prints; others are switched to it
    assert "필수 항목 누락: detected_by" in p.stdout.decode(shown)


@pytest.mark.parametrize("enc", ["cp1252", "ascii", "cp949", "utf-8"])
@pytest.mark.parametrize("args, code, text", [
    # success: the last line says "☐ 작성 필요" (cp949 has no ☐)
    (["data/synthetic/intake/DEV-2026-2201.yaml", "--today", "2026-11-24"], 0, "☐ 작성 필요"),
    # rejection whose message contains "—" (cp949 has no —)
    (["data/synthetic/tutorial/no_synthetic_flag.yaml", "--today", "2026-11-24"], 1, "합성(가짜) 데이터입니다 —"),
    (["--help"], 0, "초안 도우미 —"),
    (["--check-history", "--today", "2026-11-24"], 0, "사용 가능"),
])
def test_every_kind_of_output_survives_korean_and_english_windows_encodings(tmp_path, enc, args, code, text):
    """Korean Windows writes redirected output (> log.txt, pipes) as cp949,
    English Windows as cp1252. A message the encoding cannot hold must not
    crash the run (that would also exit 1, the same code as a rejection)."""
    out = ["--out", str(tmp_path)] if "--help" not in args and "--check-history" not in args else []
    p = subprocess.run([sys.executable, "-m", "devdraft.cli", *args, *out], cwd=ROOT, capture_output=True,
                       env={**os.environ, "PYTHONIOENCODING": enc})
    assert b"Traceback" not in p.stderr, p.stderr.decode("utf-8", "replace")
    assert p.returncode == code
    assert text in p.stdout.decode("utf-8")


def test_printed_symbols_probe_covers_what_the_cli_prints():
    """Any non-ASCII character in a CLI message must be in the encoding probe,
    or a console that lacks it would crash on that message."""
    import devdraft.cli as cli_mod
    src = "".join(Path(m.__file__).read_text(encoding="utf-8") for m in (cli_mod, __import__("devdraft.history").history,
                                                                         __import__("devdraft.intake").intake))
    strings = re.findall(r'f?"(?:[^"\\\n]|\\.)*"', src)
    used = {ch for st in strings for ch in st if ord(ch) > 127 and not ("\uac00" <= ch <= "\ud7a3")}
    missing = sorted(ch for ch in used if ch not in cli_mod._PRINTED_SYMBOLS)
    assert not missing, f"_PRINTED_SYMBOLS에 없는 출력 문자: {missing}"


# --- portfolio showcase (realistic synthetic cases) --------------------------------

SHOWCASE = ROOT / "data/synthetic/showcase"
SHOWCASE_OUT = ROOT / "sample_output/showcase"


@pytest.mark.parametrize("name, level, reason", [
    ("DEV-2026-2301", "critical", "데이터 완전성"),
    ("DEV-2026-2302", "major", "OOS"),
    ("DEV-2026-2303", "critical", "무균 보증"),
    ("DEV-2026-2304", "major", "다른 배치"),
])
def test_showcase_cases_cover_each_risk_path(name, level, reason):
    d = load(SHOWCASE / f"{name}.yaml", RULES)
    assert d.synthetic
    got, reasons = propose_class(d, RULES, len(find_recurrence(d, HISTORY, RULES, TODAY)))
    assert got == level and any(reason in r for r in reasons)


def test_showcase_outputs_are_up_to_date_and_complete(tmp_path):
    """Regenerate with: python scripts/make_showcase.py --word (Microsoft Word on macOS), or without --word (LibreOffice)."""
    run_batch(sorted(SHOWCASE.glob("*.yaml")), ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_summary=True)
    produced = sorted(tmp_path.glob("*.md"))
    assert len(produced) == 5  # 4 drafts + summary
    for f in produced:
        assert f.read_text(encoding="utf-8") == (SHOWCASE_OUT / f.name).read_text(encoding="utf-8"), \
            f"{f.name} is stale — run: python scripts/make_showcase.py"
    for yml in SHOWCASE.glob("*.yaml"):
        assert (SHOWCASE_OUT / f"{yml.stem}_draft.pdf").stat().st_size > 10_000
        assert (SHOWCASE_OUT / f"{yml.stem}_p1.png").stat().st_size > 10_000


def _png_size(path):
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR", path
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_showcase_page_images_are_a4():
    """The README shows these images: they must be pictures of the sheet the tool writes now (A4, 210 x 297 mm)."""
    drafts = sorted(SHOWCASE_OUT.glob("DEV-*_p*.png"))
    summary = sorted(SHOWCASE_OUT.glob("_summary_*_p*.png"))
    assert len(drafts) >= 8 and summary
    for png in drafts:
        w, h = _png_size(png)
        assert abs(h / w - 297 / 210) < 0.01, f"{png.name}: {w} x {h} is not an A4 page"
    for png in summary:
        w, h = _png_size(png)
        assert abs(w / h - 297 / 210) < 0.01, f"{png.name}: {w} x {h} is not an A4 page on its side"


def _showcase_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_showcase", ROOT / "scripts/make_showcase.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_showcase_script_names_page_images_like_the_readme_links():
    mod = _showcase_script()
    assert mod.page_image_name("DEV-2026-2301_draft", 1) == "DEV-2026-2301_p1.png"
    assert mod.page_image_name("_summary_2026-11-24", 2) == "_summary_2026-11-24_p2.png"
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "sample_output/showcase/" + mod.page_image_name("DEV-2026-2301_draft", 1) in text


def test_showcase_script_says_what_is_missing(tmp_path, monkeypatch):
    """Without the program that draws the pages, the script stops with the name of what is needed
    and writes nothing (it does not leave half a showcase)."""
    mod = _showcase_script()
    monkeypatch.setattr(mod.sys, "platform", "linux")
    with pytest.raises(SystemExit, match="--word 는 Microsoft Word가 설치된 macOS"):
        mod.word_to_pdf([tmp_path / "a.docx"], tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="soffice 가 필요합니다"):
        mod.soffice_to_pdf([tmp_path / "a.docx"], tmp_path)
    monkeypatch.setitem(sys.modules, "pymupdf", None)  # import pymupdf -> ImportError
    with pytest.raises(SystemExit, match="pdftoppm .* 또는 PyMuPDF"):
        mod.pdf_to_pngs(tmp_path / "a.pdf", tmp_path)
    assert not list(tmp_path.iterdir())


def test_readme_shows_showcase_images():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    imgs = re.findall(r'src="([^"]+\.png)"', text)
    assert imgs and all((ROOT / i).exists() for i in imgs)


# --- summary table as Word (--summary --docx) ------------------------------------

def test_summary_docx_written_with_summary_header(tmp_path):
    results, summary = run_batch(sorted(INTAKE.glob("*.yaml")), ROOT / "config/rules.yaml",
                                 ROOT / "data/synthetic/history.csv", tmp_path, TODAY,
                                 want_docx=True, want_summary=True)
    doc = _Document(summary.with_suffix(".docx"))
    head = doc.sections[0].header.paragraphs[0].text
    assert "일괄 처리 요약" in head and "생성일 2026-11-24" in head
    assert head.startswith("합성 데이터 — 실제 문서 아님")  # summary of synthetic forms
    rows = [[c.text for c in r.cells] for t in doc.tables for r in t.rows]
    assert any(r[0] == "DEV-2026-2201" and "MAJOR (제안)" in r[2] for r in rows)
    assert any(r[0] == "DEV-2026-2204.yaml" and "detected_by" in r[1] for r in rows)
    assert all("**" not in c and "`" not in c for r in rows for c in r)
    sec = doc.sections[0]
    assert (_twips(sec.page_width), _twips(sec.page_height)) == (16838, 11906)  # A4 on its side for the wide table
    assert all(r._tr.trPr.find(_qn("w:cantSplit")) is not None for t in doc.tables for r in t.rows)


def test_summary_docx_only_with_docx_flag(tmp_path):
    run_batch([INTAKE / "DEV-2026-2203.yaml"], ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_summary=True)
    assert not list(tmp_path.glob("_summary_*.docx"))


def test_draft_docx_header_still_reads_id_and_date(tmp_path):
    build(INTAKE / "DEV-2026-2203.yaml", ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
          tmp_path, TODAY, want_docx=True)
    head = _Document(tmp_path / "DEV-2026-2203_draft.docx").sections[0].header.paragraphs[0].text
    assert "DEV-2026-2203" in head and "생성일 2026-11-24" in head


# --- file arguments: unexpanded wildcards (Windows) and missing files -------------

def test_cli_expands_wildcard_the_shell_left_alone(tmp_path):
    """cmd/PowerShell pass `*.yaml` through literally; bash would expand it."""
    p = _cli("data/synthetic/showcase/*.yaml", "--today", "2026-11-24", "--out", tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert len(list(tmp_path.glob("*_draft.md"))) == 4 and "Traceback" not in p.stderr


def test_cli_wildcard_without_match_is_usage_error(tmp_path):
    p = _cli("data/synthetic/showcase/nothing_*.yaml", "--out", tmp_path)
    assert p.returncode == 2 and "일치하는 양식 파일이 없습니다" in p.stderr and "Traceback" not in p.stderr


def test_missing_form_file_is_a_rejection_not_a_crash(tmp_path):
    p = _cli(INTAKE / "DEV-2026-2201.yaml", "data/synthetic/intake/typo.yaml", "--today", "2026-11-24",
             "--out", tmp_path)
    assert p.returncode == 1 and "파일이 없습니다" in p.stdout and "Traceback" not in p.stderr
    assert (tmp_path / "DEV-2026-2201_draft.md").exists()


def test_non_utf8_form_is_a_rejection(tmp_path):
    f = tmp_path / "cp949.yaml"
    f.write_bytes((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8").encode("cp949"))
    with pytest.raises(IntakeError) as e:
        load(f, RULES)
    assert "UTF-8" in str(e.value)


# --- docs/TUTORIAL.md: every shown output is the real output ----------------------

import shlex  # noqa: E402

TUTORIAL = ROOT / "docs/TUTORIAL.md"


def _tutorial():
    return TUTORIAL.read_text(encoding="utf-8")


_VERIFY = re.compile(r"<!-- verify exit=(\d+) -->\n```bash\n(.+?)\n```\n```text\n(.*?)\n```", re.S)


@pytest.mark.parametrize("exit_code, command, expected",
                         _VERIFY.findall(TUTORIAL.read_text(encoding="utf-8")) or [("0", "", "")])
def test_tutorial_commands_print_what_the_tutorial_shows(tmp_path, exit_code, command, expected):
    argv = shlex.split(command)
    assert argv[:3] == ["python", "-m", "devdraft.cli"], command
    args = argv[3:]
    shown_out = None
    if "--out" in args:  # write to tmp, then map tmp back to the path the tutorial shows
        i = args.index("--out") + 1
        shown_out, args[i] = args[i], str(tmp_path / args[i])
    p = _cli(*args)
    got = p.stdout.strip()
    if shown_out:
        got = got.replace(str(tmp_path / shown_out), shown_out)
    # The CLI prints native paths (drafts\x.md on Windows, which cmd needs);
    # the tutorial shows them with "/".
    got = got.replace(os.sep, "/")
    assert p.returncode == int(exit_code), p.stdout + p.stderr
    assert got == expected.strip()


def test_tutorial_has_verified_steps():
    assert len(_VERIFY.findall(_tutorial())) >= 6


@pytest.mark.parametrize("path, block", re.findall(r"<!-- file: (\S+) -->\n```\w*\n(.*?)\n```",
                                                    TUTORIAL.read_text(encoding="utf-8"), re.S))
def test_tutorial_input_files_are_shown_verbatim(path, block):
    assert (ROOT / path).read_text(encoding="utf-8").rstrip("\n") == block


@pytest.mark.parametrize("path, block", re.findall(r"<!-- excerpt: (\S+) -->\n```\w*\n(.*?)\n```",
                                                    TUTORIAL.read_text(encoding="utf-8"), re.S))
def test_tutorial_excerpts_appear_in_committed_outputs(path, block):
    assert block in (ROOT / path).read_text(encoding="utf-8"), path


def test_duke_sample_outputs_are_up_to_date(tmp_path):
    run_batch(sorted(INTAKE.glob("*.yaml")), DUKE_RULES, ROOT / "data/synthetic/history.csv",
              tmp_path, TODAY, want_summary=True)
    out = ROOT / "sample_output/sop_examples/duke"
    for f in tmp_path.glob("*.md"):
        assert f.read_text(encoding="utf-8") == (out / f.name).read_text(encoding="utf-8"), \
            f"{f.name} stale — regenerate with --rules {DUKE_RULES.relative_to(ROOT)} --out {out.relative_to(ROOT)}"


# --- entered facts are shown verbatim (no Markdown interpretation) ---------------

from devdraft.mdtext import block as md_block, inline as md_inline  # noqa: E402

TRICKY = ["#4 포트 장갑 부적합", "- 직전 배치 적합", "> 작업자 진술", "*재시험 전* 교체", "결과 **Fail** 기록",
          "코드 `GL-4`", "A | B", "2~8°C, 10~15분", "_주의_ 표시", "[A] lot", "<b>x</b>", "1. 첫 번째",
          "=== 구분 ===", "+ 추가", "R&D", "&lt;5", "back\\slash"]


def _tricky_form(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2202.yaml").read_text(encoding="utf-8"))
    f["title"] = "장갑 리크 | 포트 4 *부적합*"
    f["description"] = "\n".join(TRICKY)
    f["immediate_actions"] = "포트 #4 장갑 교체 | 재시험 적합\n> 재시험 결과 Pass"
    f["parameters"] = [{"name": "Glove leak | port 4", "spec": "Pass", "actual": "Fail*", "duration": "~5 min"}]
    p = tmp_path / "tricky.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return f, p


def _md_cells(row: str) -> list[str]:
    """Split a Markdown table row on unescaped pipes."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]


def test_entered_facts_appear_verbatim_in_word(tmp_path):
    f, p = _tricky_form(tmp_path)
    build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv", tmp_path / "o", TODAY, want_docx=True)
    doc = _Document(tmp_path / "o" / "DEV-2026-2202_draft.docx")
    text = "\n".join(p.text for p in _all_paragraphs(doc))
    facts = [f["title"], *f["description"].splitlines(), *f["immediate_actions"].splitlines(),
             f["parameters"][0]["name"], f["parameters"][0]["actual"], f["parameters"][0]["duration"]]
    missing = [x for x in facts if x not in text]
    assert not missing, missing
    # no fact turned into a heading or into the tool's warning box
    assert not [p.text for p in doc.paragraphs if p.style.name.startswith("Heading") and "포트" in p.text]
    assert not [t for t in doc.tables if len(t.rows) == 1 and "작업자 진술" in t.cell(0, 0).text]


def test_parameter_values_stay_in_their_columns(tmp_path):
    """A "|" in a parameter name used to push the actual result into the wrong column."""
    f, p = _tricky_form(tmp_path)
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY, want_docx=True).read_text(encoding="utf-8")
    row = next(l for l in md.splitlines() if l.startswith("| Glove"))
    assert len(_md_cells(row)) == 4
    doc = _Document(tmp_path / "o" / "DEV-2026-2202_draft.docx")
    cells = next([c.text for c in r.cells] for t in doc.tables for r in t.rows if r.cells[0].text.startswith("Glove"))
    assert cells == ["Glove leak | port 4", "Pass", "Fail*", "~5 min"]
    title_row = next(l for l in md.splitlines() if l.startswith("| 제목 |"))
    assert len(_md_cells(title_row)) == 2


def test_description_line_breaks_are_kept(tmp_path):
    f, p = _tricky_form(tmp_path)
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY).read_text(encoding="utf-8")
    body = md.split("## 1. 사건 경위", 1)[1].split("###", 1)[0].strip().splitlines()
    assert len(body) == len(TRICKY) and all(l.endswith("  ") for l in body[:-1])


@pytest.mark.parametrize("text, expected", [
    ("3.40-3.60", "3.40-3.60"), ("SYN-mAb-07", "SYN-mAb-07"), ("SYN_mAb_07", "SYN_mAb_07"),
    ("98.7% (재적분)", "98.7% (재적분)"), ("R&D", "R&D"), ("5.5.2", "5.5.2"), ("≥ 97.0%", "≥ 97.0%"),
    ("#4", r"\#4"), ("- a", r"\- a"), ("1. a", r"1\. a"), ("a|b", r"a\|b"), ("2~8", r"2\~8"),
    ("*x*", r"\*x\*"), ("_x_", r"\_x\_"), ("<b>", r"\<b>"), ("&lt;", r"\&lt;"), ("a\\b", r"a\\b"),
])
def test_md_escaping_rules(text, expected):
    assert md_inline(text) == expected


def test_md_block_keeps_lines():
    assert md_block("a\n#b") == "a  \n\\#b"


def test_summary_cells_are_escaped(tmp_path):
    r = FormResult(file="a.yaml", ok=True, dev_id="D-1", title="*굵게* | 둘", proposed="minor", reasons=["x"])
    row = next(l for l in render_summary([r], "2026-11-24", 365).splitlines() if l.startswith("| D-1"))
    assert len(_md_cells(row)) == 7 and r"\*굵게\* \| 둘" in row


@pytest.mark.parametrize("field", ["title", "batch", "detected_by"])
def test_line_break_in_one_line_field_is_rejected(tmp_path, field):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f[field] = "첫 줄\n둘째 줄"
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "줄바꿈" in str(e.value) and field in str(e.value)


def test_line_break_in_parameter_is_rejected(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    f["parameters"][0]["actual"] = "3.62\n(재측정 3.58)"
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "parameters 1번째" in str(e.value)


def test_multiline_description_is_allowed(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f["description"] = "첫 줄\n둘째 줄"
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    assert load(p, RULES).description == "첫 줄\n둘째 줄"


# --- new risk questions (user decision 2026-11-25) ------------------------------------

def _form_with(tmp_path, **flags):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f.update(flags)
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    return p


@pytest.mark.parametrize("flag", ["patient_safety_impact", "regulatory_report_required"])
def test_new_questions_must_be_answered(tmp_path, flag):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f.pop(flag)
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "미응답" in str(e.value) and flag in str(e.value)


def test_patient_safety_impact_proposes_critical(tmp_path):
    d = load(_form_with(tmp_path, patient_safety_impact=True), RULES)
    level, reasons = propose_class(d, RULES, 0)
    assert level == "critical" and reasons == ["환자 안전에 영향 가능성"]


def test_regulatory_report_is_shown_not_decided(tmp_path):
    """Reporting is a separate decision from severity: a ☐ item, not a trigger."""
    p = _form_with(tmp_path, regulatory_report_required=True)
    d = load(p, RULES)
    assert propose_class(d, RULES, 0)[0] == "minor"  # grade unchanged
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY, want_docx=True).read_text(encoding="utf-8")
    sec = md.split("## 3. 분류", 1)[1].split("## 4.", 1)[0]
    assert "| 규제 신고 대상 가능성 | 예 |" in sec
    assert "☐ **작성 필요** 신고 필요 여부·기한·신고처 확인" in sec
    assert "도구는 신고 여부를 판단하지 않습니다" in sec
    doc = _Document(tmp_path / "o" / "DEV-2026-2203_draft.docx")
    para = next(p for p in doc.paragraphs if "신고 필요 여부" in p.text)
    box = next(r for r in para.runs if r.text.startswith("☐"))
    assert box.font.highlight_color == WD_COLOR_INDEX.YELLOW


def test_no_report_item_when_answer_is_no():
    md = (ROOT / "sample_output/DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    assert "| 규제 신고 대상 가능성 | 아니오 |" in md and "신고 필요 여부" not in md


def test_flag_table_lists_every_required_flag():
    md = (ROOT / "sample_output/DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    sec = md.split("| 확인 항목 | 보고자 입력 |", 1)[1].split("\n\n", 1)[0]
    rows = [l for l in sec.strip().splitlines() if l.startswith("| ") and "---" not in l]
    assert len(rows) == len(RULES["required_flags"]) == 8


def test_regulatory_report_is_never_a_grade_trigger_in_shipped_rules():
    for rules_path in (ROOT / "config/rules.yaml", SOP_RULES, DUKE_RULES):
        r = load_rules(rules_path)
        fields = {t["field"] for ts in r["classes"].values() for t in ts}
        assert "regulatory_report_required" not in fields, rules_path.name
        assert {"patient_safety_impact", "regulatory_report_required"} <= set(r["required_flags"])


# --- summary as Excel (--summary --xlsx, user-approved openpyxl) --------------------

import openpyxl  # noqa: E402

from devdraft.summary_xlsx import write_summary_xlsx  # noqa: E402


def _header_row(ws, first: str) -> int:
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == first)


def test_summary_xlsx_contents(tmp_path):
    results, summary = run_batch(sorted(INTAKE.glob("*.yaml")), ROOT / "config/rules.yaml",
                                 ROOT / "data/synthetic/history.csv", tmp_path, TODAY,
                                 want_summary=True, want_xlsx=True)
    wb = openpyxl.load_workbook(summary.with_suffix(".xlsx"))
    assert wb.sheetnames == ["초안 생성", "거부"]
    ws = wb["초안 생성"]
    notes = " ".join(str(ws.cell(r, 1).value) for r in range(1, 5))
    assert "판단·승인 문서가 아닙니다" in notes and "합성(가짜) 데이터" in notes
    h = _header_row(ws, "Deviation 번호")
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=h + 1)]
    assert [r[0] for r in rows] == ["DEV-2026-2201", "DEV-2026-2202", "DEV-2026-2203"]
    assert rows[0][2] == "MAJOR (제안)" and rows[0][4] == 5
    assert all("(제안" in r[2] for r in rows)
    assert rows[2][2] == "MINOR (제안, 반복 기준 미평가)" and rows[2][4] == "조회 안 함"  # 2203 has no equipment
    assert ws.freeze_panes == f"A{h + 1}" and ws.auto_filter.ref.startswith(f"A{h}")
    header = [c.value for c in ws[h]]
    assert not any("확정" in str(v) or "근본원인" in str(v) for v in header)  # no confirmation, no root cause
    rej = wb["거부"]
    hr = _header_row(rej, "입력 파일")
    assert rej.cell(hr + 1, 1).value == "DEV-2026-2204.yaml" and "detected_by" in rej.cell(hr + 1, 2).value


@pytest.mark.parametrize("evil", ['=HYPERLINK("http://x","클릭")', "=1+1", "+1+1", "-2+3", "@SUM(A1)"])
def test_summary_xlsx_never_writes_formulas(tmp_path, evil):
    """Entered text that looks like a formula must stay text (formula injection)."""
    rs = [FormResult(file="f.yaml", ok=True, dev_id="D-1", title=evil, proposed="minor", reasons=[evil],
                     draft="D-1_draft.md"),
          FormResult(file=evil + ".yaml", ok=False, error=evil)]
    wb = openpyxl.load_workbook(write_summary_xlsx(rs, "2026-11-24", 365, None, tmp_path / "s.xlsx"))
    cells = [c for ws in wb.worksheets for row in ws.iter_rows() for c in row
             if isinstance(c.value, str) and evil in c.value]
    assert len(cells) >= 4
    for c in cells:
        assert c.data_type == "s", (c.coordinate, c.data_type)
        if c.value.startswith(("=", "+", "-", "@")):
            assert c.quotePrefix, c.coordinate


def test_summary_xlsx_only_with_flag(tmp_path):
    run_batch([INTAKE / "DEV-2026-2203.yaml"], ROOT / "config/rules.yaml",
              ROOT / "data/synthetic/history.csv", tmp_path, TODAY, want_summary=True)
    assert not list(tmp_path.glob("*.xlsx"))


def test_xlsx_without_summary_is_usage_error(tmp_path):
    p = _cli(INTAKE / "DEV-2026-2203.yaml", "--xlsx", "--out", tmp_path)
    assert p.returncode == 2 and "--summary" in p.stderr
    assert not list(tmp_path.glob("*"))


def test_openpyxl_is_a_declared_dependency():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^openpyxl>=", reqs, flags=re.M)


# --- template guidance must never leak into a value (found by filling the template) --

OLD_LAYOUT_LEAK = '''description: |         # [필수] 사건 경위. 관찰한 사실·기록된 수치·시각만 적습니다.
  02:30부터 DO 값이 하한(30%) 아래로 떨어져 03:10 최저 22% 기록.
                       #        "~때문으로 보임" 같은 원인 추정은 적지 않습니다.
'''


def _filled_with_block(tmp_path, description_block: str, template: Path = TEMPLATE) -> Path:
    t = template.read_text(encoding="utf-8")
    src = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    for k, v in src.items():
        if k in ("synthetic", "parameters", "description"):
            continue
        val = ("true" if v else "false") if isinstance(v, bool) else f"'{v}'"
        t = re.sub(rf"^{k}:( *)(''|)( *)#", lambda m: f"{k}: {val}  #", t, count=1, flags=re.M)
    t = re.sub(r"^description: ''.*$", description_block.rstrip("\n"), t, count=1, flags=re.M)
    p = tmp_path / "f.yaml"
    p.write_text(t, encoding="utf-8")
    return p


def test_template_has_no_comment_lines_under_a_field():
    """An indented '# ...' line below a field is swallowed by a `|` block."""
    for n, line in enumerate(TEMPLATE.read_text(encoding="utf-8").splitlines(), 1):
        assert not re.match(r"^\s+#", line), f"line {n}: {line!r}"


def test_block_description_from_template_keeps_only_entered_lines(tmp_path):
    block = ("description: |         # [필수] 사건 경위. 관찰한 사실·기록된 수치·시각만 적습니다.\n"
             "  첫 줄 사실.\n  둘째 줄 사실.\n")
    d = load(_filled_with_block(tmp_path, block), RULES)
    assert d.description == "첫 줄 사실.\n둘째 줄 사실.\n"


def test_guidance_swallowed_by_block_is_rejected(tmp_path):
    """Forms copied from the old template layout leaked its guidance into the description."""
    with pytest.raises(IntakeError) as e:
        load(_filled_with_block(tmp_path, OLD_LAYOUT_LEAK), RULES)
    assert "양식 주석이" in str(e.value) and "description" in str(e.value)


def test_every_template_phrase_is_detected_anywhere_in_a_value(tmp_path):
    from devdraft.intake import _template_phrases
    phrases = _template_phrases()
    assert any("원인 추정은 적지 않습니다" in p for p in phrases)
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f["immediate_actions"] = "교체 완료.\n계획만 있는 조치는 \"예정\"이라고 명시합니다."
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(p, RULES)
    assert "immediate_actions" in str(e.value)


# --- detected_at must be a real, past date-time, shown as typed ----------------------

def _form_text_with_detected_at(tmp_path, raw_value: str) -> Path:
    t = (INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8")
    t, n = re.subn(r"^detected_at: .*$", f"detected_at: {raw_value}", t, flags=re.M)
    assert n == 1
    p = tmp_path / "f.yaml"
    p.write_text(t, encoding="utf-8")
    return p


@pytest.mark.parametrize("raw", ["'어제 새벽 3시'", "'2026/11/23 10:10'", "'2026-13-40T99:99'", "'2026-11-23'",
                                 "2026-11-23", "'23.11.2026 10:10'"])
def test_detected_at_must_be_a_real_date_time(tmp_path, raw):
    with pytest.raises(IntakeError) as e:
        load(_form_text_with_detected_at(tmp_path, raw), RULES)
    assert "detected_at" in str(e.value) and "실제 날짜·시각" in str(e.value)


@pytest.mark.parametrize("raw, shown", [("'2026-11-23T10:10'", "2026-11-23T10:10"),
                                        ("'2026-11-23 10:10'", "2026-11-23 10:10"),
                                        ("2026-11-23 10:10:00", "2026-11-23 10:10:00")])
def test_valid_detected_at_is_shown_exactly_as_typed(tmp_path, raw, shown):
    """Unquoted YAML date-times used to load as datetime objects."""
    p = _form_text_with_detected_at(tmp_path, raw)
    assert load(p, RULES).detected_at == shown
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY).read_text(encoding="utf-8")
    assert f"| 발견 일시 | {shown} |" in md


def test_future_detected_at_is_rejected_and_others_still_drafted(tmp_path):
    future = _form_text_with_detected_at(tmp_path, "'2026-11-25T08:00'")  # TODAY is 2026-11-24
    results, _ = run_batch([future, INTAKE / "DEV-2026-2201.yaml"], ROOT / "config/rules.yaml",
                           ROOT / "data/synthetic/history.csv", tmp_path / "o", TODAY)
    assert [r.ok for r in results] == [False, True]
    assert "미래" in results[0].error


def test_same_day_detection_is_accepted(tmp_path):
    p = _form_text_with_detected_at(tmp_path, "'2026-11-24T23:59'")
    assert build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv", tmp_path / "o", TODAY).exists()


# --- recurrence that was not checked must not read as "no recurrence" -----------------

def test_no_equipment_means_recurrence_not_checked_not_none(tmp_path):
    """DEV-2026-2203 has no equipment ID, so no history row can match."""
    md = (ROOT / "sample_output/DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    sec = md.split("## 4. 반복성 검토", 1)[1].split("## 5.", 1)[0]
    assert "반복성 조회를 하지 않았습니다" in sec and "설비 값이 비어" in sec
    assert "건 없음" not in sec
    assert "☐ **작성 필요** QMS에서 반복 여부 직접 확인" in sec


def test_unchecked_recurrence_is_flagged_on_the_proposal():
    md = (ROOT / "sample_output/DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    assert "**제안 등급: MINOR** (반복 기준 미평가" in md
    sec = md.split("근거:", 1)[1].split("분류 기준 출처", 1)[0]
    assert "반복성 조회를 하지 않음(설비 미기재)" in sec


def test_duke_default_reason_does_not_claim_absence_when_unchecked():
    """The Duke default reason says "최근 2년 내 … deviation 없음" — false if nobody looked."""
    md = (ROOT / "sample_output/sop_examples/duke/DEV-2026-2203_draft.md").read_text(encoding="utf-8")
    sec = md.split("## 3. 분류", 1)[1].split("## 4.", 1)[0]
    assert "deviation 없음" not in sec
    assert "반복 기준은 평가되지 않았습니다" in sec
    row = next(l for l in (ROOT / "sample_output/sop_examples/duke/_summary_2026-11-24.md").read_text(
        encoding="utf-8").splitlines() if "DEV-2026-2203" in l)
    assert "반복 기준 미평가" in row and "조회 안 함" in row


def test_checked_recurrence_is_unchanged():
    md = (ROOT / "sample_output/DEV-2026-2202_draft.md").read_text(encoding="utf-8")
    assert "최근 365일 내 동일 사업장·설비·유형 건 없음." in md and "미평가" not in md


def test_empty_category_also_counts_as_not_checked(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    f["category"] = ""
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY).read_text(encoding="utf-8")
    assert "유형 값이 비어" in md and "(반복 기준 미평가" in md


# --- a "yes" answer the rules don't use must not vanish silently ----------------------

def test_unused_yes_answers_are_named_under_rules_without_that_criterion(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f.update(released_product_affected=True, patient_safety_impact=True, regulatory_report_required=True)
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    md = build(p, DUKE_RULES, ROOT / "data/synthetic/history.csv", tmp_path / "o", TODAY).read_text(encoding="utf-8")
    sec = md.split("## 3. 분류", 1)[1].split("## 4.", 1)[0]
    assert "이 규칙의 분류 기준이 아닌 항목: 출하 제품 영향, 환자 안전 영향" in sec
    assert "☐ **작성 필요** SOP에 따라 이 답변이 등급에 영향을 주는지 확인" in sec
    note = sec.split("분류 기준이 아닌 항목", 1)[1].split("\n", 1)[0]
    assert "규제 신고" not in note  # reporting has its own item, not a grade question


def test_no_unused_note_when_rules_use_the_answer(tmp_path):
    f = yaml.safe_load((INTAKE / "DEV-2026-2203.yaml").read_text(encoding="utf-8"))
    f.update(released_product_affected=True, patient_safety_impact=True)
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    md = build(p, ROOT / "config/rules.yaml", ROOT / "data/synthetic/history.csv",
               tmp_path / "o", TODAY).read_text(encoding="utf-8")
    assert "분류 기준이 아닌 항목" not in md and "제안 등급: CRITICAL" in md


def test_duke_sample_surfaces_sterility_yes():
    """DEV-2026-2202 answered sterility 'yes'; the Duke SOP has no such criterion."""
    md = (ROOT / "sample_output/sop_examples/duke/DEV-2026-2202_draft.md").read_text(encoding="utf-8")
    assert "분류 기준이 아닌 항목: 타 배치 영향 가능성, 무균 보증 영향" in md
    row = next(l for l in (ROOT / "sample_output/sop_examples/duke/_summary_2026-11-24.md").read_text(
        encoding="utf-8").splitlines() if l.startswith("| DEV-2026-2202"))
    assert "※ 규칙에 없는 '예' 답변: 타 배치 영향 가능성, 무균 보증 영향" in row


def test_unused_yes_in_excel_summary(tmp_path):
    results, summary = run_batch([INTAKE / "DEV-2026-2202.yaml"], DUKE_RULES, ROOT / "data/synthetic/history.csv",
                                 tmp_path, TODAY, want_summary=True, want_xlsx=True)
    ws = openpyxl.load_workbook(summary.with_suffix(".xlsx"))["초안 생성"]
    h = _header_row(ws, "Deviation 번호")
    assert "규칙에 없는 '예' 답변: 타 배치 영향 가능성, 무균 보증 영향" in ws.cell(h + 1, 4).value


# --- console output a first-time user reads ------------------------------------

def test_help_is_korean_and_explains_every_option():
    p = _cli("--help")
    assert p.returncode == 0
    assert "positional arguments" not in p.stdout and "show this help" not in p.stdout
    for opt in ("--rules", "--history", "--out", "--docx", "--summary", "--xlsx", "--check-history", "--today"):
        line = next(l for l in p.stdout.splitlines() if l.strip().startswith(opt))
        assert re.search(r"[가-힣]", line), f"{opt} 설명 없음: {line}"
    assert "예:" in p.stdout and "templates/intake_template.yaml" in p.stdout and "종료 코드" in p.stdout


def test_run_lists_every_file_written_and_ends_with_counts(tmp_path):
    forms = [ROOT / f"data/synthetic/intake/DEV-2026-220{i}.yaml" for i in (1, 4)]
    p = _cli(*map(str, forms), "--summary", "--docx", "--xlsx", "--today", "2026-11-24", "--out", str(tmp_path))
    assert p.returncode == 1
    for written in tmp_path.iterdir():  # nothing is created silently
        assert str(written) in p.stdout, f"화면에 안 나온 파일: {written.name}"
    last = p.stdout.strip().splitlines()
    assert any(l.startswith("완료: 입력 2건 · 초안 1건 · 거부 1건") for l in last[-3:])
    assert any("ERR 줄의 양식을 보완" in l for l in last[-3:])


def test_successful_run_does_not_tell_user_to_fix_forms(tmp_path):
    p = _cli(str(ROOT / "data/synthetic/intake/DEV-2026-2201.yaml"), "--today", "2026-11-24", "--out", str(tmp_path))
    assert p.returncode == 0
    assert "거부 0건" in p.stdout and "보완" not in p.stdout and "작성 필요" in p.stdout


# --- --new: a blank form without OS-specific copy commands -----------------------

def test_new_creates_blank_form_with_id_and_next_steps(tmp_path):
    p = _cli("--new", "DEV-2026-9001", "--out", tmp_path)
    assert p.returncode == 0, p.stdout
    made = tmp_path / "DEV-2026-9001.yaml"
    text = made.read_text(encoding="utf-8")
    assert re.search(r"^id: 'DEV-2026-9001'", text, re.M)
    assert text.replace("'DEV-2026-9001'", "''", 1) == (ROOT / "templates/intake_template.yaml").read_text(encoding="utf-8")
    assert str(made) in p.stdout and "--docx" in p.stdout and "synthetic: true" in p.stdout
    assert not list(tmp_path.glob("*_draft.md"))  # no draft is made


def test_new_never_overwrites_a_form(tmp_path):
    form = tmp_path / "DEV-2026-9001.yaml"
    form.write_text("이미 적은 사실", encoding="utf-8")
    p = _cli("--new", "DEV-2026-9001", "--out", tmp_path)
    assert p.returncode == 1 and "덮어쓰지 않습니다" in p.stdout
    assert form.read_text(encoding="utf-8") == "이미 적은 사실"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "", "DEV 2026", ".hidden"])
def test_new_rejects_ids_that_are_not_plain_file_names(tmp_path, bad):
    p = _cli("--new", bad, "--out", tmp_path / "out")
    assert p.returncode in (1, 2) and "Traceback" not in p.stderr
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
    assert not (tmp_path / "escape.yaml").exists()


def test_form_made_with_new_then_filled_in_becomes_a_draft(tmp_path):
    """The whole first-time path: --new, fill in every field, run."""
    _cli("--new", "DEV-2026-9001", "--out", tmp_path)
    form = tmp_path / "DEV-2026-9001.yaml"
    sample = yaml.safe_load((INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8"))
    text = form.read_text(encoding="utf-8")
    for key, val in sample.items():
        if key in ("id", "parameters", "synthetic"):
            continue
        lit = ("true" if val else "false") if isinstance(val, bool) else "'" + str(val).replace("'", "''") + "'"
        text, n = re.subn(rf"^{key}:[^\n#]*", f"{key}: {lit}  ", text, count=1, flags=re.M)
        assert n == 1, key
    form.write_text("synthetic: true\n" + text, encoding="utf-8")
    p = _cli(form, "--docx", "--today", "2026-11-24", "--out", tmp_path)
    assert p.returncode == 0, p.stdout
    assert (tmp_path / "DEV-2026-9001_draft.md").exists() and (tmp_path / "DEV-2026-9001_draft.docx").exists()


def test_paths_inside_the_current_folder_are_shown_short(tmp_path):
    """Run from the repo folder without --out (what a user does): no
    C:\\Users\\...\\gmp-deviation-draft-main\\ prefix repeated on every line."""
    out = ROOT / "drafts"
    created = not out.exists()
    p = _cli("--new", "ZZ-SHORT-PATH-TEST")
    try:
        assert p.returncode == 0
        assert str(ROOT) not in p.stdout
        assert f"NEW {Path('drafts') / 'ZZ-SHORT-PATH-TEST.yaml'}" in p.stdout
    finally:
        (out / "ZZ-SHORT-PATH-TEST.yaml").unlink(missing_ok=True)
        if created and out.exists() and not any(out.iterdir()):
            out.rmdir()


# --- a form field is a record of what was typed: numbers are not re-read ---------

from devdraft.rules import form_load  # noqa: E402


def test_form_loader_keeps_number_like_text_as_typed():
    d = form_load("batch: 0412\nstep: 1:30\nph: 3.40\nn: 12\nexp: 1.5e3\nhex: 0x1F\nflag: true\nempty:\nwhen: 2026-11-21 14:20\n")
    assert d == {"batch": "0412", "step": "1:30", "ph": "3.40", "n": "12", "exp": "1.5e3", "hex": "0x1F",
                 "flag": True, "empty": None, "when": "2026-11-21 14:20"}
    # rules.yaml still needs real numbers (window_days, min)
    assert strict_load("window_days: 365")["window_days"] == 365


def test_unquoted_numbers_in_a_form_reach_the_draft_as_typed(tmp_path):
    """YAML 1.1 read batch 0412 as 266 and 1:30 as 90; the draft then crashed
    (the fields were no longer text) instead of showing what was written."""
    text = (INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8")
    text = re.sub(r"^batch: .*$", "batch: 0412", text, flags=re.M)
    text = re.sub(r"^product: .*$", "product: 1:30", text, flags=re.M)
    text = re.sub(r"^  actual: .*$", "  actual: 3.40", text, flags=re.M)
    assert "batch: 0412" in text and "product: 1:30" in text and "  actual: 3.40" in text
    form = tmp_path / "DEV-2026-2201.yaml"
    form.write_text(text, encoding="utf-8")
    p = _cli(form, "--today", "2026-11-24", "--out", tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Traceback" not in p.stderr
    md = (tmp_path / "DEV-2026-2201_draft.md").read_text(encoding="utf-8")
    assert "| 제품 / 배치 | 1:30 / 0412 |" in md
    assert "| Elution pH | 3.40-3.60 | 3.40 | 6 min |" in md


def test_a_form_with_only_a_number_in_a_required_field_is_not_missing(tmp_path):
    text = (INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8")
    form = tmp_path / "f.yaml"
    form.write_text(re.sub(r"^batch: .*$", "batch: 0", text, flags=re.M), encoding="utf-8")
    assert load(form, RULES).batch == "0"


# --- web/: the browser app is tested against what the CLI gives ---------------------

def test_web_reference_files_match_the_cli():
    """web/tests/fixtures and web/src/sample.js are generated from the CLI and the
    synthetic data. If a rule, a sample form or the form loader changes, they must be
    regenerated (python web/tools/make_fixtures.py) and the web tests rerun, so the
    browser app cannot drift from the CLI unnoticed."""
    p = subprocess.run([sys.executable, str(ROOT / "web/tools/make_fixtures.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr


# --- the same key written twice must not silently win or lose --------------------

from devdraft.rules import DuplicateKeyError  # noqa: E402


def test_a_repeated_answer_in_a_form_is_rejected_not_silently_overwritten(tmp_path):
    """Before: a second `sterility_assurance_impacted: false` at the end of the form
    turned the CRITICAL proposal into MAJOR without a word."""
    text = (INTAKE / "DEV-2026-2202.yaml").read_text(encoding="utf-8")
    assert "sterility_assurance_impacted: true" in text
    form = tmp_path / "DEV-2026-2202.yaml"
    form.write_text(text + "sterility_assurance_impacted: false\n", encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(form, RULES)
    assert "같은 항목이 두 번" in str(e.value) and "sterility_assurance_impacted" in str(e.value)
    p = _cli(form, "--today", "2026-11-24", "--out", tmp_path)
    assert p.returncode == 1 and "ERR" in p.stdout and "Traceback" not in p.stderr
    assert not list(tmp_path.glob("*_draft.md"))


def test_a_repeated_key_inside_a_parameter_is_rejected(tmp_path):
    text = (INTAKE / "DEV-2026-2201.yaml").read_text(encoding="utf-8")
    form = tmp_path / "f.yaml"
    form.write_text(text.replace("  actual: '3.62'\n", "  actual: '3.62'\n  actual: '3.58'\n"), encoding="utf-8")
    with pytest.raises(IntakeError) as e:
        load(form, RULES)
    assert "actual" in str(e.value)


def test_a_repeated_block_in_rules_stops_the_run(tmp_path):
    """Two `major:` blocks: YAML kept only the second, dropping the first block's triggers."""
    text = (ROOT / "config/rules.yaml").read_text(encoding="utf-8")
    rules = tmp_path / "rules.yaml"
    rules.write_text(text + "\nrecurrence:\n  window_days: 30\n  match_on: [site]\n", encoding="utf-8")
    with pytest.raises(RulesError) as e:
        load_rules(rules)
    assert "같은 항목이 두 번" in str(e.value) and "recurrence" in str(e.value)
    p = _cli(INTAKE / "DEV-2026-2201.yaml", "--rules", rules, "--today", "2026-11-24", "--out", tmp_path)
    assert p.returncode == 2 and "RULES ERR" in p.stdout and not list(tmp_path.glob("*_draft.md"))


def test_duplicate_check_does_not_disturb_ordinary_files():
    with pytest.raises(DuplicateKeyError):
        strict_load("a: 1\na: 2\n")
    assert strict_load("a: {x: 1}\nb: {x: 2}\n") == {"a": {"x": 1}, "b": {"x": 2}}
    for f in list(INTAKE.glob("*.yaml")) + [ROOT / "config/rules.yaml", ROOT / "templates/intake_template.yaml"]:
        form_load(f.read_text(encoding="utf-8"))
