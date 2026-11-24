# gmp-deviation-draft

생산시설 품질 문서 작성 중 반복 부분을 줄이는 **GMP 일탈(Deviation) 보고서 초안 도우미**입니다.

```
양식 입력(YAML) → 검증 → 분류 제안 + 반복성 조회 + 조사 계획 → 보고서 초안(MD/DOCX) → 사람이 검토
```

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
| 위험 확인 항목(true/false) 미응답 거부 | 미응답을 "아니오"로 간주하기 |

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
```

결과 예시(Markdown)는 [`sample_output/`](sample_output/)에 있습니다. `*.docx`는 저장소에 넣지 않으므로 `--docx`로 직접 생성해 확인하십시오.

| 파일 | 내용 |
|---|---|
| `DEV-2026-2201` | CPP 이탈 + 반복 이력 → **MAJOR** 제안 |
| `DEV-2026-2202` | 무균 보증 영향 → **CRITICAL** 제안 |
| `DEV-2026-2203` | 기록 서명 누락 → **MINOR** 제안 |
| `DEV-2026-2204` | 발견자 미기재 → **거부** (누락 항목 안내) |

마지막 건은 일부러 불완전하게 두었습니다. 양식이 덜 채워졌을 때 도구가 추정하지 않고 되돌려보내는지를 보여줍니다.

## QA가 직접 고치는 곳

[`config/rules.yaml`](config/rules.yaml) 한 파일입니다.

- `required_fields` — 필수 입력 항목
- `required_flags` — 반드시 true/false로 답해야 하는 위험 확인 항목. `classes`에서 `equals:` 트리거로 쓰는 항목은 모두 여기에 있어야 하며, 빠지면 도구가 실행을 멈춥니다.
- `classes` — critical / major / minor 판단 트리거와 각 근거 문구
- `recurrence` — 조회 기간(기본 365일)과 일치 기준(설비 + 유형)
- `categories` — 허용 일탈 유형
- `ishikawa` — 6M 조사 항목 문구

## 보안 / 데이터 취급

- 외부 전송 없음. LLM 호출 없음. 전부 로컬에서 동작합니다.
- 실제 배치 데이터를 쓰려면 이 저장소가 아니라 사내 환경에서 실행하고, 합성 데이터는 제거하십시오.
- `drafts/`와 `*.docx`는 `.gitignore`에 있습니다. 실제 일탈 내용이 저장소에 들어가지 않도록 하기 위함입니다.

## 합성 데이터 다시 만들기

```bash
python scripts/make_synthetic_data.py
```

이력 51건(설비 8종, 최근 18개월)과 입력 양식 4건을 만듭니다. `CHR-03` 설비는 반복 건이 나오도록 일부러 심어두었습니다.

## 테스트

```bash
pip install -r requirements.txt
python -m pytest -q
```

분류 트리거 3종, 반복성 조회 기간, 필수/미허용 항목 검증, 위험 확인 항목 미응답·비(非)불리언 거부, rules.yaml 트리거-필수 플래그 일관성, 빈 템플릿(미작성 시 거부·판단 항목 없음), `drafts/`·`*.docx` 무시 여부, 판단 칸 공란 유지, 입력에 없는 수치가 초안에 들어가지 않는지, DOCX 생성까지 확인합니다.

## 구조

```
devdraft/
  intake.py     양식 로드 + 검증 (누락/미허용 항목 거부)
  classify.py   분류 제안, 반복성 조회, 6M 조사 계획
  draft.py      Markdown 초안 렌더링
  docx_out.py   Word 변환 (Arial, 표 괘선)
  cli.py        실행 진입점
config/rules.yaml
templates/intake_template.yaml   QA가 채우는 빈 입력 양식
data/synthetic/
scripts/make_synthetic_data.py
tests/
```
