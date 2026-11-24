# HANDOFF — 현재 상태와 다음 할 일

> 작업이 끝날 때마다 갱신합니다 (규칙: [`CLAUDE.md`](../CLAUDE.md)).
> **마지막 갱신: 2026-11-24** · 기준 브랜치 `main` · 테스트 170개 통과 · 도구 버전 `devdraft 0.5.0`

## 1. 현재 상태 — 한눈에

| 기능 | 상태 |
|---|---|
| 입력 양식 검증 (누락·잘못된 값 거부, `yes`/`no` 거부) | ✅ |
| 빈 입력 템플릿 (`templates/intake_template.yaml`) | ✅ |
| 분류 **제안** + 근거 (rules.yaml) | ✅ |
| 반복성 조회 (같은 사업장·설비·유형, 과거 근본원인 기본 숨김) | ✅ |
| 이력 CSV 점검 (`--check-history`) | ✅ |
| 일괄 처리 요약표 (`--summary`) | ✅ |
| Word 초안 (모든 쪽 "초안" 머리글, 빈칸 노란 강조) | ✅ — **실제 Word 화면 확인은 아직** |
| 생성 근거 기록 (입력 파일명·SHA-256·기준일·버전) | ✅ |
| 합성 이력이 실제 양식에 섞이는 것 차단 | ✅ |
| SOP 반영 예시: 합성 SOP, 공개 SOP(Duke COMM-PAS-013) | ✅ |
| **회사 실제 SOP 반영** | ⏸ SOP 원문 필요 |
| 자동 테스트(CI) — PR마다 GitHub에서 테스트 실행 | ❌ 없음 |

## 2. 머지된 작업

| PR | 내용 |
|---|---|
| [#1](https://github.com/strawberryHunter/gmp-deviation-draft/pull/1) | 입력 검증, 빈 양식, `--summary`, rules.yaml SOP 대비 구조, 사용 가이드 |
| [#2](https://github.com/strawberryHunter/gmp-deviation-draft/pull/2) | 이력 CSV 점검, 합성 SOP 예시, `manual_checks` |
| [#3](https://github.com/strawberryHunter/gmp-deviation-draft/pull/3) | Word 초안 서식 |
| [#4](https://github.com/strawberryHunter/gmp-deviation-draft/pull/4) | 생성 근거 기록, 합성 이력 오용 방지 |
| [#5](https://github.com/strawberryHunter/gmp-deviation-draft/pull/5) | 공개 SOP(Duke) 매핑, 용어 "deviation" 통일 |

## 3. 사용자가 해야 할 일 — Claude가 대신할 수 없는 것

위에서부터 중요한 순서입니다. 끝나면 Claude에게 결과를 알려 주세요.

- [ ] **① 프로젝트 목적 알려 주기** — 포트폴리오/과제/실제 회사 도입 중 무엇인지에 따라 다음 작업 우선순위가 달라집니다.
- [ ] **② Word 초안을 실제 Word에서 열어 보기** — 작업 환경에 맑은 고딕이 없어 화면 확인을 못 했습니다.
  1. 아래 "프롬프트 A"로 Word 초안을 만들어 달라고 하거나, 직접 `python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx`
  2. 확인할 것: 모든 쪽 머리글의 빨간 "초안 — 승인 문서 아님" · 빈칸 노란 강조 · 한글이 맑은 고딕으로 보이는지
  3. 이상하면 화면 캡처를 Claude에게 보내기
- [ ] **③ 결정해 주기** ([`DECISIONS.md`](../DECISIONS.md) "확인 필요") — 각 항목에 "이대로" 또는 "바꿔"만 답하면 됩니다.

  | 질문 | 지금 상태 |
  |---|---|
  | "같은 deviation"을 무엇으로 볼까? | 같은 사업장 + 설비 + 유형 |
  | 기본 rules.yaml을 합성 SOP로 바꿀까? | 안 바꿈 (분류 기준 출처 "작성 필요" 표시 유지) |
  | Excel 기본 저장(CP949) 이력 파일을 자동으로 읽을까? | 안 읽음, "CSV UTF-8로 다시 저장" 안내 |
  | 반복 건 표에 과거 근본원인을 보일까? | 숨김 |
  | 거부 건이 있으면 종료 코드 1 | 1 |

- [ ] **④ 회사 SOP 구하기** (실제 도입이 목적일 때만) — deviation 등급 정의 부분. 아래 "프롬프트 B"로 전달.
- [ ] **⑤ GitHub 브랜치 정리** — 이 세션은 원격 브랜치를 지울 권한이 없습니다. 머지가 끝난 아래 5개는 지워도 내용이 사라지지 않습니다.
  `fix/flag-validation-template`, `feat/history-check`, `feat/docx-format`, `feat/traceability`, `feat/public-sop-example`
  - 지우는 곳: 저장소 → Branches → 각 줄의 휴지통 아이콘
  - 앞으로 자동으로 지우려면: Settings → General → **Automatically delete head branches** 켜기
- [ ] **⑥ (실제 도입 시) 회사 절차** — 사내 품질 절차에 따른 도구 검토와, 필요하면 소프트웨어 적격성 평가(CSV). 실제 데이터는 회사 환경에서만.

## 4. 다음 작업 후보 — Claude에게 그대로 복사해서 보내는 프롬프트

### 프롬프트 A — 확인용 Word 초안 만들기
```
CLAUDE.md와 docs/HANDOFF.md를 읽고, 합성 샘플 3건(DEV-2026-2201~2203)의 Word 초안을
--today 2026-11-24 로 만들어서 파일로 보내줘. 확인할 것도 같이 알려줘.
```

### 프롬프트 B — 회사 SOP 반영 (SOP 원문이 있을 때)
```
CLAUDE.md와 docs/HANDOFF.md를 읽고 시작해.
아래는 우리 회사 deviation SOP의 등급 정의 부분이야. 원문은 저장소에 넣지 말고,
docs/sop_mapping/Duke_COMM-PAS-013.md 와 같은 방식으로 조항별 매핑 문서와
config/rules.yaml 을 만들어줘. SOP에 없는 등급은 만들지 말고, 도구가 판단 못 하는 조항은
manual_checks 로 남겨. 애매한 해석은 DECISIONS.md 에 "확인 필요"로 적어.

SOP 번호/개정: <예: QA-SOP-012 Rev.05>
<등급 정의 부분 붙여넣기>
```

### 프롬프트 C — 결정 반영 (③에 답할 때)
```
CLAUDE.md와 docs/HANDOFF.md를 읽고 시작해. DECISIONS.md "확인 필요" 결정:
- 같은 deviation 기준: <이대로 / 설비만 / 유형만 / ...>
- 기본 rules.yaml 합성 SOP 적용: <이대로 / 바꿔>
- CP949 자동 읽기: <이대로 / 바꿔>
- 과거 근본원인 표시: <이대로 / 보여줘>
- 종료 코드: <이대로 / 바꿔>
반영하고 PR 만들어줘.
```

### 프롬프트 D — 다음 개선 (목적과 관계없이 유용, 위에서부터 권장)
```
CLAUDE.md와 docs/HANDOFF.md를 읽고, "다음 개선 후보" 중 맨 위 항목을 진행해줘.
```

**다음 개선 후보** (Claude가 끝낼 때마다 이 목록을 갱신)
1. **CI 추가** — PR마다 GitHub Actions에서 `pytest` 실행. 지금은 Claude가 로컬에서 돌린 결과만 믿고 머지하고 있음
2. **Python 최소 버전 검증** — 문서는 3.10 이상이라고 하지만 3.10에서 실행해 본 적 없음 (CI에서 3.10~3.13 매트릭스로 같이 해결 가능)
3. **새 판단 항목** — 예: "환자 안전 영향", "규제 신고 대상". 입력 양식·템플릿·초안·rules.yaml에 함께 추가 (항목 이름은 사용자가 정해야 함)
4. **요약표 Excel/Word 출력** — 지금은 Markdown만

## 5. 참고 문서
- 사용법: [`docs/USAGE.md`](USAGE.md)
- 판단 기록: [`DECISIONS.md`](../DECISIONS.md)
- SOP 매핑 예시: [`docs/sop_mapping/Duke_COMM-PAS-013.md`](sop_mapping/Duke_COMM-PAS-013.md), [`config/examples/`](../config/examples/)
