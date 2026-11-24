# 공개 SOP 매핑 — Duke COMM-PAS-013 Deviations and Investigations

> **공개된 실제 SOP를 이 도구에 옮겨 본 예시입니다.** Duke University와 관련이 없고, Duke가 검토하거나 승인한 것이 아닙니다.
> SOP 원문은 저장소에 복사하지 않았습니다. 아래 링크에서 원문을 확인하십시오. 이 문서에는 조항 번호, 짧은 인용, 도구 반영 방식만 적습니다.

| 항목 | 내용 |
|---|---|
| 문서 | COMM-PAS-013 *Deviations and Investigations* |
| 개정 / 시행일 | Revision 01 / Effective 01 Jul 2025 |
| 소유 | Duke Cancer Institute, Adult and Pediatric Blood and Marrow Transplant Program (APBMT) Clinical Quality Program, Stem Cell Laboratory (STCL) |
| 원문 | <https://web.emmes.com/study/duke/SOP/Common%20Quality/COMM-PAS-013%20Deviations%20and%20Investigations.pdf> (공개 PDF) |
| 확인일 | 2026-11-24 (저작권·배포 제한 문구 없음 확인) |
| 옮긴 결과 | [`config/examples/rules_Duke_COMM-PAS-013.yaml`](../../config/examples/rules_Duke_COMM-PAS-013.yaml) |

## 이 SOP의 분류 방식 — 이 도구의 기본 가정과 다른 점

이 SOP에는 **Critical / Major / Minor 같은 deviation 등급이 없습니다.** 대신:

1. **Risk assessment 점수**: Severity · Probability · Detectability를 각각 사람이 1–5점으로 매기고 곱해서 Combined Risk Score를 냅니다 (8.4.2, Appendix A Tab 5). 기준표는 별도 문서 COMM-PAS-014에 있습니다.
2. **Repeat Deviation**: "2년 안에 다시 일어난 deviation" (4.26). 해당하면 trend 조사와 이전 조치의 효과성 평가가 보고서에 들어가야 합니다 (8.8.1.2).

그래서 이 도구에 옮길 때 원칙은 이렇습니다.

- SOP에 없는 등급을 **만들지 않습니다.** 도구가 제안하는 것은 SOP가 정의한 범주인 **Repeat Deviation 해당 / 해당 없음** 하나뿐입니다.
- 점수 매기기(severity 등)는 사람의 판단이므로 **도구가 계산하지 않습니다.** `manual_checks`로 초안에 `☐` 항목으로 남겨 검토자가 채웁니다.

## 조항별 반영

| 조항 | SOP 요지 (짧은 인용) | 도구 반영 |
|---|---|---|
| 2.4 | "Deviations (planned or unplanned) must be initiated and documented for any departure…" | 맥락 — 도구는 이미 개시된 deviation의 초안만 만듦 |
| 3.4 | 발견 후 "within three business days" 안에 개시 | `manual_checks` — 영업일·휴일 계산이 필요해 도구가 판단하지 않음 |
| 3.6 | Medical Director가 "approves or rejects all initiated deviations" | 반영 안 함 — 승인은 검증된 QMS에서 (이 도구는 승인 기능 없음) |
| 3.7.1 | CQP가 완결성·상세 수준 검토·승인 | 반영 안 함 — 위와 같음 |
| 3.7.2.1 | 관련 제품 quarantine 확인, CQP 승인 전까지 해제 금지 | `manual_checks` |
| 3.7.3 | 제품 출하·CoA 서명 전 "no product impact" 확인 | 초안 "7. 제품 품질 영향 평가" 칸 (`☐ 작성 필요`) |
| 4.26 | Repeat Deviation: "re-occurs within a 2-year period" | 트리거 — `recurrence_count` ≥ 1, `window_days: 730` |
| 8.4.2 | Severity·Probability·Detectability 위험 평가 (COMM-PAS-014) | `manual_checks` — 점수는 사람이 매김 |
| 8.4.2.1 | 이번에 일어나지 않은 관련 결과까지 위험 평가 확장 | `manual_checks` |
| 8.4.3.1 | 어느 파라미터라도 5점이면 CAPA 검토, 안 하면 근거 기재 | `manual_checks` |
| 8.8.1.2 | Repeat Deviation이면 trend 조사 + 이전 조치 효과성 평가 | `manual_checks` (반복 건 목록은 도구가 제공) |

## 확인 필요 — 도구가 SOP를 해석한 부분

- **"similar" / "re-occurs"의 범위**: SOP는 무엇이 같은 deviation인지 정하지 않습니다. 이 예시는 도구의 기존 기준인 **같은 사업장·설비·유형**(`match_on: [site, equipment_id, category]`)을 썼습니다. 실제로는 CQP가 정하는 기준으로 바꿔야 합니다.
- **2년 = 730일**로 계산했습니다.
- 초안 양식의 "QA 검토자 확정 등급" 칸은 이 SOP에서는 "Repeat Deviation 해당 여부 확인"으로 읽어야 합니다. SOP의 승인 주체는 Medical Director와 CQP입니다.
- 입력 양식의 위험 확인 항목 6개(CPP 이탈, OOS 등)는 이 SOP의 분류 기준이 아니므로 분류 트리거로 쓰지 않았습니다. 초안에는 보고자 입력 사실로만 표시됩니다.
