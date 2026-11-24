"""Render the deviation report draft.

Every section that needs human judgement is left as an explicit
placeholder rather than filled with plausible-looking text. The tool
restates facts the reporter entered; it does not invent findings,
root causes or conclusions.
"""
from __future__ import annotations

from datetime import date

from .intake import Deviation

TBD = "☐ **작성 필요**"

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
                    generated_on: str | None = None) -> str:
    generated_on = generated_on or date.today().isoformat()
    rec_block = "최근 12개월 내 동일 설비·유형 건 없음."
    if recurrence:
        rec_block = "\n".join(
            [f"최근 12개월 내 유사 건 {len(recurrence)}건:", "", "| 번호 | 개설일 | 등급 | 근본원인 |", "|---|---|---|---|"]
            + [f"| {r['dev_id']} | {r['opened']} | {r['final_class']} | {r['root_cause']} |" for r in recurrence]
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

**제안 등급: {proposed.upper()}**

근거:
{chr(10).join(f"- {r}" for r in reasons)}

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
