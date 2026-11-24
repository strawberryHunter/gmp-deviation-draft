# gmp-deviation-draft

생산시설 품질 문서 작성 중 반복 부분을 줄이는 **GMP 일탈(Deviation) 보고서 초안 도우미**입니다.

```
양식 입력(YAML) → 검증 → 분류 제안 + 반복성 조회 + 조사 계획 → 보고서 초안(MD/DOCX) → 사람이 검토
```

**처음 쓰는 경우 → [사용 가이드 `docs/USAGE.md`](docs/USAGE.md)** (설치, 양식 작성, 거부 메시지 대응, 초안 검토, SOP에 맞춘 rules.yaml 수정)

> **모든 데이터는 합성(가짜) 데이터입니다.** 사업장·제품·배치·설비·일탈 사례 모두 지어낸 것입니다.

## 설계 원칙 — 도구가 하지 않는 것

GxP 문서라 "그럴듯하게 채워주는" 동작이 가장 위험합니다. 그래서 이 도구는:

| 하는 것 | 하지 않는 것 |
|---|---|
| 입력한 사실을 보고서 형식으로 재배열 | 조사 결과·근본원인·영향평가 결론 생성 |
| 규칙에 따른 **분류 제안**과 그 근거 표시 | 분류 확정 (QA 검토자가 확정란에 직접 기재) |
| 과거 이력에서 반복 건 조회 | 반복 원인 추정 |
| 6M 기반 조사 항목 제시 | 조사 수행 여부 판단 |
| 누락 항목 거부 | 누락 항목을 추정해서 채우기 |
| 위험 확인 항목(true/false) 미응답·`yes`/`no` 등 거부 | 미응답을 "아니오"로 간주하기 |
| 반복 건 목록(번호·일자·등급) 표시 | 과거 근본원인 기본 표시 (`show_root_cause`로만 켬) |

근본원인·영향평가·CAPA 칸은 전부 `☐ 작성 필요`로 비워 둡니다. 테스트가 이를 강제합니다
(`test_draft_never_fills_judgement_sections`).

전자서명·승인 흐름은 **포함하지 않습니다.** 승인은 검증된 QMS에서 수행해야 하며, 이 도구는 그 앞단의 초안 작성만 담당합니다.
도구가 만든 초안을 사용하려면 사내 절차에 따른 검토와, 필요 시 소프트웨어 적격성 평가가 선행되어야 합니다.

## 입력 양식 작성

빈 템플릿 [`templates/intake_template.yaml`](templates/intake_template.yaml)을 복사해 `<일탈번호>.yaml`로 저장하고 채웁니다.
항목마다 무엇을 어떻게 적는지 주석이 달려 있습니다. 복사본은 `drafts/` 등 커밋되지 않는 위치에 두십시오.

- `[필수]` 항목이 비어 있으면 초안을 만들지 않고 누락 항목을 **한 번에 모두** 알려줍니다.
- 위험 확인 항목 6개는 반드시 `true` / `false`로 적어야 합니다. 비워 두거나 `"예"`, `"yes"`, `1`처럼 쓰면 거부합니다.
  미응답이 "아니오"로 처리되어 분류 제안이 낮아지는 것을 막기 위함입니다.
- 근본원인·영향평가·CAPA 항목은 양식에 없으며, 넣으면 거부합니다.

## 실행

```bash
python -m devdraft.cli data/synthetic/intake/DEV-2026-2201.yaml --docx
python -m devdraft.cli data/synthetic/intake/*.yaml --out drafts --today 2026-11-24
python -m devdraft.cli data/synthetic/intake/*.yaml --summary --today 2026-11-24
python -m devdraft.cli --check-history --history <QMS에서 내보낸 이력.csv>
```

`--summary`는 여러 건을 한 번에 처리할 때 `_summary_<날짜>.md`를 함께 만듭니다
([예시](sample_output/_summary_2026-11-24.md)).

- 초안이 만들어진 건: 일탈 번호, 제목, **제안** 등급과 근거, 반복 건 수, 초안 파일
- 거부된 건: 입력 파일과 거부 사유 (보완 후 다시 실행)
- 확정 등급란은 두지 않습니다. 확정은 각 초안에서만 합니다. 우선순위·처리 순서도 매기지 않습니다.
- 과거 이력의 근본원인과 공정 수치는 요약표에 옮기지 않습니다 (건수만 표시, 상세는 각 초안).
- 한 실행에 같은 일탈 번호가 두 번 나오면 두 번째는 덮어쓰지 않고 거부합니다. YAML 문법 오류도 해당 건만 거부합니다.

결과 예시(Markdown)는 [`sample_output/`](sample_output/)에 있습니다. `*.docx`는 저장소에 넣지 않으므로 `--docx`로 직접 생성해 확인하십시오.

| 파일 | 내용 |
|---|---|
| `DEV-2026-2201` | CPP 이탈 + 반복 이력 → **MAJOR** 제안 |
| `DEV-2026-2202` | 무균 보증 영향 → **CRITICAL** 제안 |
| `DEV-2026-2203` | 기록 서명 누락 → **MINOR** 제안 |
| `DEV-2026-2204` | 발견자 미기재 → **거부** (누락 항목 안내) |

마지막 건은 일부러 불완전하게 두었습니다. 양식이 덜 채워졌을 때 도구가 추정하지 않고 되돌려보내는지를 보여줍니다.

## QA가 직접 고치는 곳

[`config/rules.yaml`](config/rules.yaml) 한 파일입니다. 자세한 절차와 SOP 문구 → YAML 예시는 [사용 가이드 5장](docs/USAGE.md#5-configrulesyaml을-sop에-맞추기).

> **현재 등급 기준은 SOP와 대조되지 않은 예시 값입니다.** 실제 사용 전에 사내 SOP에 맞추고 `sop_reference`를 기재하십시오.
> 비어 있으면 초안의 "분류 기준 출처"에 `☐ 작성 필요`가 표시됩니다.

- `sop_reference` — 근거 SOP 번호·개정 (초안에 표시)
- `levels` — 등급 목록(높은 등급부터)과 표시 이름. 등급 수·이름은 SOP대로 바꿀 수 있습니다.
- `default_level` / `default_reason` — 어떤 기준에도 해당하지 않을 때의 제안
- `classes` — 등급별 트리거 (예/아니오 항목 `equals: true`, 반복 건수 `recurrence_count` + `min`)
- `required_fields` / `required_flags` — 필수 입력 항목 / 반드시 true·false로 답할 항목
- `recurrence` — 조회 기간(`window_days`), 일치 기준(`match_on`: equipment_id / category / site), 과거 근본원인 표시 여부(`show_root_cause`, 기본 false)
- `categories` — 허용 일탈 유형
- `ishikawa` — 6M 조사 항목 문구
- `manual_checks` — 도구가 평가하지 못하는 SOP 조항. 초안에 `☐ 검토자가 직접 확인` 항목으로 표시
- `history_class_labels` — 이력의 `final_class` 중 `levels`에 없어도 되는 값

공개된 실제 SOP(Duke COMM-PAS-013)를 옮긴 예시: [`docs/sop_mapping/Duke_COMM-PAS-013.md`](docs/sop_mapping/Duke_COMM-PAS-013.md) → [`config/examples/rules_Duke_COMM-PAS-013.yaml`](config/examples/rules_Duke_COMM-PAS-013.yaml). Critical/Major/Minor가 없는 SOP라 도구는 Repeat Deviation 해당 여부만 제안합니다.

합성 SOP를 옮긴 완성 예시: [`data/synthetic/sop/SYN-QA-SOP-001.md`](data/synthetic/sop/SYN-QA-SOP-001.md) → [`config/examples/rules_SYN-QA-SOP-001.yaml`](config/examples/rules_SYN-QA-SOP-001.yaml) ([사용 가이드 5-2-1](docs/USAGE.md#5-2-1-끝까지-따라-해-볼-수-있는-예시-합성-sop))

종료 코드: 전부 성공 `0`, 거부 1건 이상 `1`, rules.yaml·이력 파일 오류 `2` ([사용 가이드 7장](docs/USAGE.md#7-명령-옵션)).

rules.yaml에 오류(없는 등급 참조, 오타 키, 따옴표 붙은 `"true"`, 필수 플래그가 아닌 트리거 등)가 있으면
`RULES ERR`로 어디가 틀렸는지 알려주고 아무 초안도 만들지 않습니다.

## 보안 / 데이터 취급

- 외부 전송 없음. LLM 호출 없음. 전부 로컬에서 동작합니다.
- 실제 배치 데이터를 쓰려면 이 저장소가 아니라 사내 환경에서 실행하고, 합성 데이터는 제거하십시오.
- `drafts/`와 `*.docx`는 `.gitignore`에 있습니다. 실제 일탈 내용이 저장소에 들어가지 않도록 하기 위함입니다.

## 합성 데이터 다시 만들기

```bash
python scripts/make_synthetic_data.py
```

이력 51건(설비 8종, 최근 18개월)과 입력 양식 4건을 만듭니다. 합성 SOP(`data/synthetic/sop/`)는 이 스크립트가 만들지 않는 고정 파일입니다. `CHR-03` 설비는 반복 건이 나오도록 일부러 심어두었습니다.

## 테스트

```bash
pip install -r requirements.txt
python -m pytest -q
```

분류 트리거 3종, 반복성 조회 기간, 필수/미허용 항목 검증, 위험 확인 항목 미응답·비(非)불리언 거부, rules.yaml 트리거-필수 플래그 일관성, 빈 템플릿(미작성 시 거부·판단 항목 없음), `drafts/`·`*.docx` 무시 여부, 일괄 요약표(전 건 기재·제안 표시·이력 근본원인 미기재·중복 번호/YAML 오류 거부), 사용자 정의 등급(SOP 등급명·등급 수), 하위 등급 트리거 표시, rules.yaml 오류 검출, 판단 칸 공란 유지, 입력에 없는 수치가 초안에 들어가지 않는지, DOCX 생성까지 확인합니다.

## 구조

```
devdraft/
  intake.py     양식 로드 + 검증 (누락/미허용 항목 거부)
  classify.py   분류 제안, 반복성 조회, 6M 조사 계획
  draft.py      Markdown 초안 렌더링
  docx_out.py   Word 변환 (모든 쪽 '초안' 머리글, 빈칸 노란 강조, 경고 상자)
  rules.py      rules.yaml 로드 + 검증
  history.py    이력 CSV 점검 (--check-history)
  summary.py    일괄 처리 요약표 (--summary)
  cli.py        실행 진입점
config/rules.yaml
config/examples/rules_SYN-QA-SOP-001.yaml   합성 SOP를 옮긴 예시
templates/intake_template.yaml   QA가 채우는 빈 입력 양식
docs/USAGE.md                    사용 가이드
data/synthetic/
scripts/make_synthetic_data.py
tests/
```
