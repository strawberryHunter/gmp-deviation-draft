"""Render the deviation report draft.

Every section that needs human judgement is left as an explicit
placeholder rather than filled with plausible-looking text. The tool
restates facts the reporter entered; it does not invent findings,
root causes or conclusions.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from .intake import Deviation
from .mdtext import block, inline
from .classify import unused_yes_answers
from .rules import level_label

TBD = "☐ **작성 필요**"

_MATCH_LABEL = {"equipment_id": "설비", "category": "유형", "site": "사업장"}

BANNER = (
    "> **초안입니다 — 승인 문서가 아닙니다.**  \n"
    "> 이 문서는 입력된 내용을 보고서 형식으로 재배열한 것입니다. 조사 결과·근본원인·영향평가 결론은 "
    "담당자가 직접 작성해야 하며, 분류는 제안일 뿐 QA 검토자의 확인이 필요합니다.  \n"
    "> 전자서명·승인 기능은 포함하지 않습니다 (해당 기능은 검증된 QMS에서 수행).\n"
)


# Reporter's yes/no answers, in the order shown in the draft.
FLAG_LABELS = [
    ("sterility_assurance_impacted", "무균 보증 영향"),
    ("released_product_affected", "출하 제품 영향"),
    ("data_integrity_concern", "데이터 완전성 우려"),
    ("patient_safety_impact", "환자 안전 영향"),
    ("cpp_excursion", "CPP 이탈"),
    ("spec_oos", "규격 이탈(OOS)"),
    ("other_batches_possibly_affected", "타 배치 영향 가능성"),
    ("regulatory_report_required", "규제 신고 대상 가능성"),
]

SYNTHETIC_MARK = "합성(가짜) 데이터로 만든 초안 — 실제 deviation 문서로 사용 금지"


def _provenance_block(dev: Deviation, src: dict | None, generated_on: str) -> str:
    if not src:
        return "생성 근거 정보 없음 (도구를 직접 호출한 경우)."
    rows = [
        ("입력 양식", f"{src['form']} (SHA-256 {src['form_sha']})"),
        ("분류 규칙", f"{src['rules']} (SHA-256 {src['rules_sha']})"),
        ("분류 기준 SOP", src.get("sop") or "미기재"),
        ("반복성 조회 이력", f"{src['history']} (SHA-256 {src['history_sha']}, {src['history_rows']}행"
                        + (", 합성 데이터" if src.get("history_synthetic") else "") + ")"),
        ("기준일", src["today"]),
        ("생성 도구", f"devdraft {src['version']}"),
    ]
    return "\n".join(["| 항목 | 값 |", "|---|---|"] + [f"| {k} | {inline(v)} |" for k, v in rows])


def _params_table(dev: Deviation) -> str:
    if not dev.parameters:
        return "해당 없음"
    head = "| 항목 | 기준 | 실측 | 비고 |\n|---|---|---|---|"
    rows = [
        f"| {inline(p.get('name',''))} | {inline(p.get('spec',''))} | {inline(p.get('actual',''))} "
        f"| {inline(p.get('duration',''))} |"
        for p in dev.parameters
    ]
    return "\n".join([head, *rows])


def _escaped(dev: Deviation) -> SimpleNamespace:
    """The deviation's text fields, escaped for Markdown (see mdtext)."""
    out = {}
    for name in Deviation.__dataclass_fields__:
        value = getattr(dev, name)
        if isinstance(value, str):
            out[name] = block(value) if name in ("description", "immediate_actions") else inline(value)
    return SimpleNamespace(**out)


def render_markdown(dev: Deviation, proposed: str, reasons: list[str],
                    recurrence: list[dict], plan: list[tuple[str, str]],
                    generated_on: str | None = None, *, rules: dict | None = None,
                    also: list[tuple[str, str]] | None = None,
                    self_in_history: bool = False,
                    sources: dict | None = None) -> str:
    generated_on = generated_on or date.today().isoformat()
    rec_cfg = (rules or {}).get("recurrence") or {"window_days": 365, "match_on": ["equipment_id", "category"]}
    window = f"최근 {rec_cfg['window_days']}일"
    match = "·".join(_MATCH_LABEL.get(k, k) for k in rec_cfg["match_on"])
    rec_block = f"{window} 내 동일 {match} 건 없음."
    missing = [k for k in rec_cfg["match_on"] if not str(dev.get(k) or "").strip()]
    rec_trigger = any(t.get("field") == "recurrence_count"
                      for ts in ((rules or {}).get("classes") or {}).values() for t in ts or [])
    grade_note = " (반복 기준 미평가 — 반복성 조회를 하지 않음)" if missing and rec_trigger else ""
    if missing:
        labels = "·".join(_MATCH_LABEL.get(k, k) for k in missing)
        rec_block = (
            f"**반복성 조회를 하지 않았습니다** — {labels} 값이 비어 있어 같은 건을 찾을 수 없습니다 "
            "(\"반복 없음\"이 아닙니다).\n\n"
            f"- {TBD} QMS에서 반복 여부 직접 확인 ({window}, 동일 {match} 기준)"
        )
    elif recurrence:
        # Past root causes are hidden unless QA opts in: listing them invites
        # copying an old cause instead of investigating this one.
        cols = ["dev_id", "opened", "final_class"]
        head = ["번호", "개설일", "등급"]
        if rec_cfg.get("show_root_cause", False):
            cols.append("root_cause")
            head.append("근본원인 (당시 기록)")
        rec_block = "\n".join(
            [f"{window} 내 동일 {match} 건 {len(recurrence)}건 (목록만 표시, 원인 연관성은 판단하지 않음):", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            + ["| " + " | ".join(inline(r.get(c, "")) for c in cols) + " |" for r in recurrence]
        )
    if self_in_history:
        rec_block += f"\n\n※ 이력 파일에 이번 deviation({inline(dev.id)}) 자체가 있어 반복 건에서 제외했습니다."
    sop = (rules or {}).get("sop_reference") or ""
    source = inline(sop) if sop else f"{TBD} — 분류 기준 출처 미기재 (config/rules.yaml sop_reference). 사내 SOP와 대조 필요."
    also_block = ""
    if also:
        also_block = "\n그 밖에 해당한 트리거 (하위 등급):\n" + "\n".join(
            f"- [{inline(level_label(rules, lvl))}] {inline(r)}" for lvl, r in also) + "\n"
    manual_block = ""
    manual = (rules or {}).get("manual_checks") or []
    if manual:
        manual_block = (
            "\n**도구가 판단하지 않은 SOP 기준 — 검토자가 직접 확인** "
            "(해당하면 위 제안 등급과 다를 수 있음):\n\n"
            + "\n".join(f"- ☐ SOP {inline(m['clause'])}: {inline(m['text'])}" for m in manual)
            + "\n"
        )
    plan_block = "\n".join(f"| {inline(k)} | {inline(v)} | {TBD} |" for k, v in plan)
    flag_rows = "\n".join(f"| {label} | {'예' if dev.get(field) else '아니오'} |" for field, label in FLAG_LABELS)
    flag_label = dict(FLAG_LABELS)
    unused = [flag_label.get(f, f) for f in (unused_yes_answers(dev, rules) if rules else [])]
    unused_block = ""
    if unused:
        unused_block = (
            f"\n**보고자가 \"예\"로 답했지만 이 규칙의 분류 기준이 아닌 항목: {', '.join(unused)}** — "
            "제안 등급에 반영되지 않았습니다. 도구는 기준을 만들지 않습니다.\n\n"
            f"- {TBD} SOP에 따라 이 답변이 등급에 영향을 주는지 확인\n"
        )
    report_block = ""
    if dev.regulatory_report_required:
        # Reporting is a separate decision from severity: shown, never decided.
        report_block = (
            "\n**보고자 입력: 규제기관 신고 대상 가능성 \"예\"** — 도구는 신고 여부를 판단하지 않습니다.\n\n"
            f"- {TBD} 신고 필요 여부·기한·신고처 확인 (사내 절차)\n"
        )
    banner = BANNER
    if dev.synthetic:
        banner = f"> **{SYNTHETIC_MARK}**  \n" + banner
    form_name = inline((sources or {}).get("form") or "입력 양식")
    # Every value the reporter entered, escaped so it is shown as entered.
    d = _escaped(dev)

    return f"""# Deviation 보고서 초안 — {d.id}

{banner}
| 항목 | 내용 |
|---|---|
| Deviation 번호 | {d.id} |
| 제목 | {d.title} |
| 사업장 / 구역 | {d.site} / {d.area} |
| 제품 / 배치 | {d.product} / {d.batch} |
| 설비 | {d.equipment_id or "해당 없음"} |
| 공정 단계 | {d.process_step} |
| 발견 일시 | {d.detected_at} |
| 발견자 | {d.detected_by or TBD} |
| 유형 | {d.category or TBD} |
| 초안 생성일 | {generated_on} |

## 1. 사건 경위

{d.description}

### 관련 공정 변수

{_params_table(dev)}

## 2. 즉시 조치

{d.immediate_actions}

## 3. 분류 (제안)

**제안 등급: {inline(level_label(rules, proposed))}**{grade_note}

근거:
{chr(10).join(f"- {inline(r)}" for r in reasons)}
{also_block}{unused_block}
분류 기준 출처: {source}
{manual_block}
| 확인 항목 | 보고자 입력 |
|---|---|
{flag_rows}
{report_block}
**QA 검토자 확정 등급:** {TBD}

**제안과 다를 경우 사유:** {TBD}

## 4. 반복성 검토

{rec_block}

## 5. 조사 계획 (6M)

| 구분 | 확인할 것 | 조사 결과 |
|---|---|---|
{plan_block}

## 6. 근본원인

{TBD} — 조사 완료 후 작성. 조사 결과로 뒷받침되지 않는 추정은 기재하지 않습니다.

## 7. 제품 품질 영향 평가

{TBD} — 해당 배치 및 영향 가능 배치에 대한 평가. 결론(출하 가능 / 보류 / 폐기)과 근거 기재.

## 8. CAPA

| 구분 | 내용 | 담당 | 기한 |
|---|---|---|---|
| 시정조치(Correction) | {TBD} | | |
| 재발방지(Corrective) | {TBD} | | |
| 예방조치(Preventive) | {TBD} | | |

## 9. 검토 및 승인

검증된 QMS에서 수행합니다. 이 초안에는 서명란을 두지 않습니다.

## 부록. 생성 근거

이 초안을 만든 입력 파일과 규칙입니다. 같은 파일로 다시 만들면 같은 초안이 나옵니다.
SHA-256 값으로 파일이 바뀌지 않았는지 확인할 수 있습니다.

{_provenance_block(dev, sources, generated_on)}

---
*이 초안은 입력 양식 `{form_name}`로부터 자동 생성되었습니다. 생성 도구는 사실을 재배열할 뿐,
조사 결과나 결론을 생성하지 않습니다.*
"""
