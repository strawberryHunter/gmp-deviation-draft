"""Render the deviation report draft.

Every section that needs human judgement is left as an explicit
placeholder rather than filled with plausible-looking text. The tool
restates facts the reporter entered; it does not invent findings,
root causes or conclusions.
"""
from __future__ import annotations

from datetime import date

from .intake import Deviation
from .rules import level_label

TBD = "☐ **작성 필요**"

_MATCH_LABEL = {"equipment_id": "설비", "category": "유형", "site": "사업장"}

BANNER = (
    "> **초안입니다 — 승인 문서가 아닙니다.**  \n"
    "> 이 문서는 입력된 내용을 보고서 형식으로 재배열한 것입니다. 조사 결과·근본원인·영향평가 결론은 "
    "담당자가 직접 작성해야 하며, 분류는 제안일 뿐 QA 검토자의 확인이 필요합니다.  \n"
    "> 전자서명·승인 기능은 포함하지 않습니다 (해당 기능은 검증된 QMS에서 수행).\n"
)


def _params_table(dev: Deviation) -> str:
    if not dev.parameters:
        return "해당 없음"
    head = "| 항목 | 기준 | 실측 | 비고 |\n|---|---|---|---|"
    rows = [
        f"| {p.get('name','')} | {p.get('spec','')} | {p.get('actual','')} | {p.get('duration','')} |"
        for p in dev.parameters
    ]
    return "\n".join([head, *rows])


def render_markdown(dev: Deviation, proposed: str, reasons: list[str],
                    recurrence: list[dict], plan: list[tuple[str, str]],
                    generated_on: str | None = None, *, rules: dict | None = None,
                    also: list[tuple[str, str]] | None = None,
                    self_in_history: bool = False) -> str:
    generated_on = generated_on or date.today().isoformat()
    rec_cfg = (rules or {}).get("recurrence") or {"window_days": 365, "match_on": ["equipment_id", "category"]}
    window = f"최근 {rec_cfg['window_days']}일"
    match = "·".join(_MATCH_LABEL.get(k, k) for k in rec_cfg["match_on"])
    rec_block = f"{window} 내 동일 {match} 건 없음."
    if recurrence:
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
            + ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in recurrence]
        )
    if self_in_history:
        rec_block += f"\n\n※ 이력 파일에 이번 일탈({dev.id}) 자체가 있어 반복 건에서 제외했습니다."
    sop = (rules or {}).get("sop_reference") or ""
    source = sop if sop else f"{TBD} — 분류 기준 출처 미기재 (config/rules.yaml sop_reference). 사내 SOP와 대조 필요."
    also_block = ""
    if also:
        also_block = "\n그 밖에 해당한 트리거 (하위 등급):\n" + "\n".join(
            f"- [{level_label(rules, lvl)}] {r}" for lvl, r in also) + "\n"
    manual_block = ""
    manual = (rules or {}).get("manual_checks") or []
    if manual:
        manual_block = (
            "\n**도구가 판단하지 않은 SOP 기준 — 검토자가 직접 확인** "
            "(해당하면 위 제안 등급과 다를 수 있음):\n\n"
            + "\n".join(f"- ☐ SOP {m['clause']}: {m['text']}" for m in manual)
            + "\n"
        )
    plan_block = "\n".join(f"| {k} | {v} | {TBD} |" for k, v in plan)

    return f"""# 일탈 보고서 초안 — {dev.id}

{BANNER}
| 항목 | 내용 |
|---|---|
| 일탈 번호 | {dev.id} |
| 제목 | {dev.title} |
| 사업장 / 구역 | {dev.site} / {dev.area} |
| 제품 / 배치 | {dev.product} / {dev.batch} |
| 설비 | {dev.equipment_id or "해당 없음"} |
| 공정 단계 | {dev.process_step} |
| 발견 일시 | {dev.detected_at} |
| 발견자 | {dev.detected_by or TBD} |
| 유형 | {dev.category or TBD} |
| 초안 생성일 | {generated_on} |

## 1. 사건 경위

{dev.description}

### 관련 공정 변수

{_params_table(dev)}

## 2. 즉시 조치

{dev.immediate_actions}

## 3. 분류 (제안)

**제안 등급: {level_label(rules, proposed)}**

근거:
{chr(10).join(f"- {r}" for r in reasons)}
{also_block}
분류 기준 출처: {source}
{manual_block}
| 확인 항목 | 보고자 입력 |
|---|---|
| 무균 보증 영향 | {"예" if dev.sterility_assurance_impacted else "아니오"} |
| 출하 제품 영향 | {"예" if dev.released_product_affected else "아니오"} |
| 데이터 완전성 우려 | {"예" if dev.data_integrity_concern else "아니오"} |
| CPP 이탈 | {"예" if dev.cpp_excursion else "아니오"} |
| 규격 이탈(OOS) | {"예" if dev.spec_oos else "아니오"} |
| 타 배치 영향 가능성 | {"예" if dev.other_batches_possibly_affected else "아니오"} |

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

---
*이 초안은 입력 양식 `{dev.id}.yaml`로부터 자동 생성되었습니다. 생성 도구는 사실을 재배열할 뿐,
조사 결과나 결론을 생성하지 않습니다.*
"""
