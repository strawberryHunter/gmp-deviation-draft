# 사용 가이드

> 처음이면 먼저 [튜토리얼](TUTORIAL.md)로 전체 흐름을 따라 해 보십시오. 이 문서는 항목별 참고서입니다.

GMP deviation 보고서 **초안** 도우미 사용법입니다. QA 담당자가 처음 쓰는 경우를 기준으로 순서대로 적었습니다.

```
① 템플릿 복사·작성 → ② 실행 → ③ 거부되면 양식 보완 → ④ 초안 검토·작성 → ⑤ 검증된 QMS에 등록·승인
                         (도구)                          (사람)                (사람, QMS)
```

도구가 하는 일은 ②까지입니다. 근본원인, 제품 품질 영향 평가, CAPA, 등급 확정, 서명·승인은 사람이 합니다.

---

## 1. 설치 (최초 1회)

Python 3.10 이상이 필요합니다. 인터넷 연결은 설치할 때만 필요하고, 실행 중에는 외부로 아무것도 보내지 않습니다.

```bash
cd gmp-deviation-draft
```

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q
```

마지막 줄이 `N passed`로 끝나면 준비된 것입니다.

---

## 2. deviation 1건 처리하기

### 2-1. 양식 작성

빈 템플릿을 복사합니다. **복사본은 `drafts/`에 둡니다.** `drafts/`는 git에 올라가지 않습니다.

```bash
mkdir -p drafts && cp templates/intake_template.yaml drafts/DEV-2026-2301.yaml
```

복사한 파일을 텍스트 편집기(메모장, VS Code 등)로 열어 채웁니다. 항목마다 주석(`#` 뒤)에 무엇을 쓰는지 적혀 있습니다.

| 구분 | 규칙 |
|---|---|
| `[필수]` 항목 | 비워 두면 거부됩니다. 배치 무관이면 `N/A`라고 적습니다. |
| 예/아니오 8개 항목 | 반드시 `true` 또는 `false` (따옴표 없이). `yes`/`no`/`예`도 거부됩니다. 모르면 확인 후 적습니다. 비워 두면 거부됩니다. |
| `description` | 관찰한 사실·수치·시각만. 원인 추정은 쓰지 않습니다. |
| `parameters` | 기록서에 적힌 기준·실측값 그대로. **초안의 수치는 여기서만 나옵니다.** |
| 근본원인·CAPA | 양식에 넣지 않습니다 (넣으면 거부). 조사 후 초안에 직접 씁니다. |

여러 줄 설명은 이렇게 씁니다.

```yaml
description: |
  용출 단계 pH가 3.62로 기록됨 (허용 범위 3.40-3.60).
  이탈 시간 약 6분.
```

### 2-2. 실행

실제 deviation은 QMS에서 내보낸 이력 CSV를 `--history`로 함께 지정합니다 (이력 준비는 6장).

```bash
python -m devdraft.cli drafts/DEV-2026-2301.yaml --docx --out drafts --history /사내경로/deviation_history.csv
```

`--history`를 빼면 기본 합성 이력이 쓰이는데, 이때 실제 양식은 가짜 반복 건이 붙지 않도록 거부됩니다.
도구를 연습할 때는 양식 맨 위에 `synthetic: true`를 넣으면 `--history` 없이도 실행됩니다 (초안에 "합성 데이터" 표시).

정상이면 아래처럼 나오고 `drafts/`에 `DEV-2026-2301_draft.md`와 `.docx`가 생깁니다.

```
OK  DEV-2026-2301.yaml -> drafts/DEV-2026-2301_draft.md
```

### 2-3. 거부되었을 때

`ERR`로 시작하면 초안을 만들지 않은 것입니다. 메시지에 문제가 **한 번에 모두** 나옵니다. 양식을 고치고 같은 명령을 다시 실행합니다.

| 메시지 | 뜻 / 할 일 |
|---|---|
| `필수 항목 누락: detected_by, ...` | 해당 항목을 채웁니다. |
| `예/아니오 미응답 (true 또는 false로 기재): ...` | 해당 항목에 `true` 또는 `false`를 적습니다. 비워 두면 "아니오"로 처리하지 않고 거부합니다. |
| `true/false가 아닌 값: cpp_excursion='no'` | `yes`, `no`, `on`, `예`, `"true"`, `1` 등은 안 됩니다. `true` / `false`로 고칩니다. |
| `값 뒤에 양식 주석이 붙어 값의 일부로 읽힘: title` | 값과 `#` 주석 사이 공백이 지워져 주석이 값에 섞였습니다. `#` 앞에 공백을 두거나 주석을 지웁니다. 그대로 두면 주석 문구가 초안에 들어가므로 거부합니다. |
| `알 수 없는 항목: root_cause` | 양식에 없는 항목입니다. 오타이거나, 근본원인처럼 양식에 쓰면 안 되는 항목입니다. |
| `category는 [...] 중 하나여야 합니다` | 템플릿 주석의 목록 중 하나로 고칩니다. |
| `YAML 문법 오류 (N행)` | N행 근처의 들여쓰기, `:` 뒤 공백, 따옴표 짝을 확인합니다. |
| `같은 deviation 번호(...)의 양식이 이번 실행에 이미 있습니다` | 한 번 실행에 같은 `id`가 두 파일에 있습니다. 하나를 고칩니다. |
| `RULES ERR ...` | 양식이 아니라 `config/rules.yaml` 문제입니다. 5장 참고. 이때는 아무 초안도 만들지 않습니다. |
| `반복성 조회 이력이 합성(가짜) 데이터입니다` | 실제 양식을 기본 합성 이력으로 실행했습니다. `--history`로 실제 이력 CSV를 지정합니다 (6장). 가짜 반복 건이 실제 초안에 붙는 것을 막기 위해 거부합니다. |
| `HISTORY ERR ...` | 이력 CSV 문제입니다. `--check-history`로 전체 목록을 보고 고칩니다 (6장). 아무 초안도 만들지 않습니다. |

---

## 3. 초안 검토 — 사람이 할 일

초안(`.docx`)을 열면 `☐ 작성 필요` 칸이 **노란색으로 강조**되어 남아 있습니다. **도구는 이 칸을 절대 채우지 않습니다.**

- 모든 쪽 머리글에 빨간 글씨로 `초안 — 승인 문서 아님 · deviation 번호 · 초안 생성일`, 바닥글에 쪽 번호가 들어갑니다. 쪽을 따로 인쇄해도 초안임을 알 수 있습니다.
- 첫 쪽의 노란 상자는 이 문서가 초안이라는 경고입니다.
- 빈칸을 채우면 노란 강조를 지워 두면 남은 빈칸을 찾기 쉽습니다 (Word: 홈 → 텍스트 강조 색 → 색 없음).
- 표가 다음 쪽으로 넘어가면 머리 행이 반복됩니다.

| 초안 위치 | 검토자가 할 일 |
|---|---|
| 상단 표, 1. 사건 경위, 2. 즉시 조치 | 입력한 내용이 그대로 옮겨졌는지 원본 기록과 대조 |
| 3. 분류 (제안) | 제안 등급과 근거를 보고 **확정 등급**과 (다를 경우) **사유**를 직접 기재. "그 밖에 해당한 트리거"도 확인 |
| 3. 검토자가 직접 확인 (있을 때) | 도구가 평가하지 않은 SOP 조항입니다. 하나씩 확인하고, 해당하면 확정 등급에 반영 |
| 3. 분류 기준 출처 | SOP 번호가 표시되는지 확인. `작성 필요`이면 rules.yaml이 아직 SOP와 대조되지 않은 상태 |
| 4. 반복성 검토 | 과거 건 **목록**(번호·개설일·등급)입니다. 과거 근본원인은 기본적으로 표시하지 않으니 필요하면 QMS에서 직접 확인합니다. 이번 건과 원인이 같은지는 도구가 판단하지 않습니다 |
| 5. 조사 계획 (6M) | 각 항목 조사 후 결과 기재. 해당 없으면 "해당 없음"과 이유 |
| 6. 근본원인 | 조사 결과로 뒷받침되는 내용만 기재 |
| 7. 제품 품질 영향 평가 | 해당 배치·영향 가능 배치 평가, 결론과 근거 |
| 8. CAPA | 시정·재발방지·예방조치, 담당, 기한 |
| 9. 검토 및 승인 | 이 초안에서 하지 않습니다. 검증된 QMS에서 수행 |
| 부록. 생성 근거 | 이 초안을 만든 입력 양식·rules.yaml·이력 파일의 파일명과 SHA-256, 기준일, 도구 버전. QMS 등록 시 초안과 함께 보관하면 어떤 입력으로 만들었는지 추적할 수 있음 |

완성된 내용은 사내 QMS에 등록하고, 승인은 QMS에서 합니다. 이 도구의 출력물은 승인 문서가 아닙니다.

---

## 4. 여러 건을 한 번에 처리 (`--summary`)

```bash
python -m devdraft.cli drafts/*.yaml --docx --summary --out drafts --history /사내경로/deviation_history.csv
```

각 건의 초안과 함께 `drafts/_summary_<날짜>.md`가 생깁니다 (`--docx`를 함께 주면 가로 방향 Word `_summary_<날짜>.docx`도, `--xlsx`를 주면 Excel `_summary_<날짜>.xlsx`도) ([예시](../sample_output/_summary_2026-11-24.md)).

- **초안 생성** 표: deviation 번호, 제목, 제안 등급과 근거, 반복 건 수, 초안 파일
- **거부** 표: 입력 파일과 거부 사유 — 보완할 목록으로 사용
- 확정 등급란, 우선순위, 과거 근본원인, 공정 수치는 요약표에 넣지 않습니다.
- Excel 요약표에서 입력값이 `=`·`+`·`-`·`@`로 시작해도 **수식이 아닌 글자**로 저장됩니다 (수식 주입 방지).

`drafts/*.yaml`에는 이미 만든 `_draft.md`가 섞이지 않습니다 (확장자가 다름). 단, 한 폴더에 같은 `id`의 양식이 두 개 있으면 두 번째는 거부됩니다.

---

## 5. `config/rules.yaml`을 SOP에 맞추기

분류 **제안** 기준은 이 파일 하나에 있습니다. 코드는 고치지 않습니다.
**현재 저장소의 등급 기준은 SOP와 대조되지 않은 예시 값입니다.** 실제 사용 전에 아래 순서대로 맞추십시오.

### 5-1. 순서

1. **SOP 출처 기재** — `sop_reference: "QA-SOP-012 Rev.05"` 처럼 SOP 번호와 개정 번호를 적습니다. 초안의 "분류 기준 출처"에 표시됩니다.
2. **등급 목록** — `levels`에 SOP의 등급을 **높은 등급부터** 적습니다. `label`은 SOP 표기 그대로 씁니다.
3. **기본 등급** — 어떤 기준에도 해당하지 않을 때의 등급을 `default_level`에, 문구를 `default_reason`에 적습니다.
4. **등급별 기준** — `classes` 아래 등급 `id`마다 트리거를 적습니다. SOP 문구를 `reason`에 그대로 옮기면 검토자가 대조하기 쉽습니다.
5. **반복성** — `recurrence.window_days`(조회 기간, 일)와 `match_on`(같은 건으로 볼 조건)을 SOP에 맞춥니다.
6. **확인** — `python -m pytest -q`와 샘플 실행 (5-4).

### 5-2. 예시 — SOP 문구를 rules.yaml로 옮기기

SOP에 이렇게 적혀 있다고 가정합니다 (예시일 뿐, 실제 SOP 아님).

> 1등급(중대): 무균 보증 또는 출하 제품에 영향 가능성이 있는 deviation
> 2등급(주요): CPP 이탈, OOS, 또는 최근 2년 내 동일 설비·유형 3회 이상 반복
> 3등급(경미): 위에 해당하지 않는 deviation

```yaml
sop_reference: "QA-SOP-XXX Rev.XX"

levels:
  - id: grade1
    label: "1등급(중대)"
  - id: grade2
    label: "2등급(주요)"
  - id: grade3
    label: "3등급(경미)"

default_level: grade3
default_reason: "1·2등급 기준에 해당 없음 (보고자 입력 기준) — 검토자 확인 필요"

classes:
  grade1:
    - field: sterility_assurance_impacted
      equals: true
      reason: "무균 보증에 영향 가능성 (SOP 5.1)"
    - field: released_product_affected
      equals: true
      reason: "출하 제품에 영향 가능성 (SOP 5.1)"
  grade2:
    - field: cpp_excursion
      equals: true
      reason: "CPP 이탈 (SOP 5.2)"
    - field: spec_oos
      equals: true
      reason: "OOS (SOP 5.2)"
    - field: recurrence_count
      min: 3
      reason: "최근 2년 내 동일 설비·유형 3회 이상 반복 (SOP 5.2)"

recurrence:
  window_days: 730
  match_on: [equipment_id, category]
```

위 예시처럼 SOP에 없는 트리거(예: `data_integrity_concern`)를 `classes`에서 빼도, 입력 양식에서는 계속 true/false로 답하게 할지(`required_flags`) 따로 정합니다. 초안의 확인 항목 표에는 8개 항목이 항상 표시됩니다.

### 5-2-1. 끝까지 따라 해 볼 수 있는 예시 (합성 SOP)

- 합성 SOP 원문: [`data/synthetic/sop/SYN-QA-SOP-001.md`](../data/synthetic/sop/SYN-QA-SOP-001.md) (실제 SOP 아님)
- 옮긴 결과: [`config/examples/rules_SYN-QA-SOP-001.yaml`](../config/examples/rules_SYN-QA-SOP-001.yaml)
  — 모든 조항 번호가 트리거 근거, `manual_checks`, 또는 설명 주석 중 하나로 추적됩니다.

```bash
python -m devdraft.cli data/synthetic/intake/*.yaml --summary --today 2026-11-24 --rules config/examples/rules_SYN-QA-SOP-001.yaml --out /tmp/sop_example
```

| 샘플 | 기본 rules.yaml | 합성 SOP 적용 | 이유 |
|---|---|---|---|
| DEV-2026-2201 | MAJOR | **중대 (Critical)** | CPP 이탈(5.3.1)은 주요지만, 2년 내 같은 사업장·설비·유형 5건 → 반복 상향(5.5.1) |
| DEV-2026-2202 | CRITICAL | 중대 (Critical) | 무균 보증 영향(5.2.1) |
| DEV-2026-2203 | MINOR | 경미 (Minor) | 해당 없음(5.4.1) |

5.5.2(CPP 30분 이상 지속)는 입력 양식에 지속 시간 수치 칸이 없어 트리거로 옮기지 않고 `manual_checks`로 두었습니다. 그래서 모든 초안에 검토자 확인 항목으로 나옵니다.
실제 SOP를 옮길 때도 이 파일을 복사해서 시작하면 됩니다.

### 5-2-2. 공개된 실제 SOP 예시 (Duke COMM-PAS-013)

실제로 공개된 deviation SOP를 옮긴 예시입니다. Duke와 관련이 없고, 원문은 저장소에 복사하지 않았습니다.

- 조항별 매핑과 근거: [`docs/sop_mapping/Duke_COMM-PAS-013.md`](sop_mapping/Duke_COMM-PAS-013.md)
- 옮긴 결과: [`config/examples/rules_Duke_COMM-PAS-013.yaml`](../config/examples/rules_Duke_COMM-PAS-013.yaml)

```bash
python -m devdraft.cli data/synthetic/intake/*.yaml --summary --today 2026-11-24 --rules config/examples/rules_Duke_COMM-PAS-013.yaml --out /tmp/duke_example
```

이 SOP에는 **Critical/Major/Minor 등급이 없습니다.** 사람이 매기는 위험 점수(Severity × Probability × Detectability)와 "2년 안에 다시 일어난 deviation(Repeat Deviation)"으로 관리합니다. 그래서:

| 샘플 | 도구 제안 | 이유 |
|---|---|---|
| DEV-2026-2201 | Repeat Deviation | 2년 안에 같은 사업장·설비·유형 5건 |
| DEV-2026-2202 | Repeat Deviation | 2년 안에 1건 (DEV-2025-1022) — 1년 기준이었다면 해당 없음 |
| DEV-2026-2203 | Repeat Deviation 해당 없음 | 0건 |

위험 점수, CAPA 필요 여부, 3영업일 내 개시, quarantine은 모두 `manual_checks`로 초안에 `☐` 항목으로 남습니다. **SOP에 없는 등급을 도구가 만들어 내지 않는 것**이 이 예시의 요점입니다.

### 5-3. 트리거 문법

| 형식 | 의미 |
|---|---|
| `field: <예/아니오 항목>` + `equals: true` | 입력 양식에서 그 항목이 `true`이면 해당 |
| `field: recurrence_count` + `min: N` | 조회 기간 안에 `match_on` 조건이 모두 같은 과거 deviation이 N건 이상이면 해당. 어느 등급에나 둘 수 있음 |

사용할 수 있는 예/아니오 항목: `cpp_excursion`, `spec_oos`, `other_batches_possibly_affected`, `sterility_assurance_impacted`, `released_product_affected`, `data_integrity_concern`, `patient_safety_impact`, `regulatory_report_required`.

`regulatory_report_required`(규제 신고 대상 가능성)는 기본 규칙에서 등급 트리거가 아닙니다. 신고 여부는 등급과 별개의 결정이라, 보고자가 `true`로 답하면 초안 분류 절에 `☐ 신고 필요 여부·기한·신고처 확인` 항목만 나타납니다. 도구는 신고 여부를 판단하지 않습니다.

`match_on`에 쓸 수 있는 값: `equipment_id`, `category`, `site`. `site`를 넣으면 다른 사업장의 같은 설비 ID 건이 제외됩니다.

### 5-4. 고친 뒤 확인

```bash
python -m pytest -q
```

```bash
python -m devdraft.cli data/synthetic/intake/*.yaml --summary --today 2026-11-24 --out /tmp/rules_check
```

`/tmp/rules_check/_summary_2026-11-24.md`에서 합성 샘플 3건의 제안 등급이 SOP대로 나오는지 봅니다.
(`DEV-2026-2204`는 일부러 덜 채운 샘플이라 항상 거부되고, 그래서 이 명령의 종료 코드는 `1`입니다. `RULES ERR`가 나오지 않으면 rules.yaml은 정상입니다.)

rules.yaml에 실수가 있으면 `RULES ERR`와 함께 **어디가 왜 틀렸는지** 나오고, 아무 초안도 만들지 않습니다. 예를 들면:

- `classes`에 있는 등급이 `levels`에 없음
- `default_level`이 `levels`에 없음
- `equals: "true"`처럼 따옴표가 붙음, `equal:` 같은 오타
- 트리거 항목이 `required_flags`에 없음 (미응답이 "아니오"로 처리될 위험)

### 5-5. rules.yaml만으로 안 되는 경우

**우선 `manual_checks`에 적습니다.** 도구가 평가할 수 없는 SOP 조항을 그냥 빼 두면, 초안만 보는 검토자는 그 조항이 있었다는 것조차 모릅니다.
`manual_checks`에 적은 조항은 모든 초안의 분류 절에 `☐ 검토자가 직접 확인` 항목으로 표시됩니다. 도구는 이 항목을 판단하지 않습니다.

```yaml
manual_checks:
  - clause: "5.5.2"
    text: "CPP 이탈이 30분 이상 지속되었는가 — 해당하면 중대"
```

도구가 직접 평가하게 하려면 코드 수정과 테스트 추가가 필요합니다. 개발 담당에게 요청하십시오.

- 8개 외의 새 예/아니오 판단 항목 (예: "의료기기 결합 제품 영향")
- "A이고 B이면" 같은 조건 조합
- 수치 기준 (예: "이탈 30분 이상") — 입력 양식에 전용 칸을 추가해야 함
- 이력에 없는 열(예: 제품)로 반복성 일치

### 5-6. 그 밖의 항목

| 항목 | 내용 |
|---|---|
| `required_fields` | 필수 입력 항목. 빼면 해당 항목이 비어도 초안이 만들어집니다 |
| `required_flags` | 반드시 true/false로 답할 항목. 트리거에 쓰는 항목은 빼면 실행이 멈춥니다 |
| `categories` | 허용 deviation 유형. 바꾸면 템플릿 주석의 목록도 같이 고칩니다 |
| `ishikawa` | 조사 계획(6M) 항목 문구 |
| `manual_checks` | 도구가 평가하지 않는 SOP 조항 (`clause`, `text`). 초안에 검토자 확인 항목으로 표시. 5-5 참고 |
| `history_class_labels` | 이력 CSV `final_class`에 있어도 되는 값 중 `levels`에 없는 것 (SOP 개정 전 등급명, 등급 없는 SOP 등). 여기 없는 값은 이력 점검에서 경고 |
| `recurrence.show_root_cause` | 반복 건 표에 과거 건의 근본원인(당시 기록)을 표시할지. 기본 `false` — 과거 원인을 옮겨 쓰는 것을 막기 위함 |

rules.yaml을 바꾸면 사내 변경관리 절차에 따라 변경 이력(누가, 언제, 어떤 SOP 개정에 맞춰)을 남기십시오.

---

## 6. 과거 이력 파일 (반복성 조회용)

기본값은 합성 데이터 `data/synthetic/history.csv`입니다. 실제 이력을 쓰려면 QMS에서 같은 열로 CSV를 내보내 **저장소 밖**에 두고 `--history`로 지정합니다.

**실제 양식은 `--history` 없이 실행되지 않습니다.** 이력 파일에 `synthetic` 열이 `True`인 행이 있으면 합성 이력으로 보고, `synthetic: true`가 없는 양식은 거부합니다. 연습용 양식에는 `synthetic: true`를 적으면 합성 이력으로 실행되고, 초안 맨 위와 Word 모든 쪽 머리글에 "합성 데이터"가 표시됩니다.

```bash
python -m devdraft.cli drafts/*.yaml --summary --out drafts --history /사내경로/deviation_history.csv
```

**처음 쓰기 전에, 그리고 새로 내보낼 때마다 먼저 점검합니다.** 초안은 만들지 않고 이력 파일만 검사합니다.

```bash
python -m devdraft.cli --check-history --history /사내경로/deviation_history.csv
```

```
이력 점검: /사내경로/deviation_history.csv
행 51개 · 오류 0건 · 경고 0건
결과: 사용 가능
```

| 구분 | 내용 | 초안 생성 시 |
|---|---|---|
| 오류 | 필수 열 없음, UTF-8도 CP949도 아님, 날짜가 `YYYY-MM-DD`가 아님, `dev_id` 비어 있음·중복 | `HISTORY ERR`로 중단, 아무 초안도 만들지 않음 (종료 코드 2) |
| 경고 | CP949로 읽음, 기준일 이후 날짜, `site`·`equipment_id` 빈칸, rules.yaml에 없는 `category`·`final_class` | 계속 진행, `HISTORY WARN n건` 한 줄 표시 |

- Excel의 **CSV UTF-8(쉼표로 분리)** 를 권장합니다 (BOM은 자동 처리). 한국어 Windows Excel의 기본 **CSV(쉼표로 분리)** (CP949)도 읽지만, 경고를 띄우니 한글 사업장·설비 이름이 양식과 같은지 확인하십시오. 둘 다 아닌 인코딩은 오류입니다.
- 기준일(`--today`) 이후 날짜의 건과, 이력에 이미 들어 있는 **이번 deviation 자신**은 반복 건에서 뺍니다. 자신을 뺀 경우 초안에 그렇게 표시됩니다.
- `final_class`가 rules.yaml `levels`에 없는 값이면(예: SOP 개정 전 등급명) 경고만 하고 표시는 그대로 합니다. 분류 제안에는 쓰지 않습니다.

필요한 열 (첫 줄 머리글, UTF-8):

| 열 | 내용 |
|---|---|
| `dev_id` | Deviation 번호 |
| `opened` | 개설일 `YYYY-MM-DD` |
| `site` | 사업장 |
| `equipment_id` | 설비 ID (입력 양식과 같은 표기) |
| `category` | deviation 유형 (rules.yaml `categories`와 같은 값) |
| `final_class` | 확정 등급 |
| `root_cause` | (선택) 기록된 근본원인. rules.yaml `recurrence.show_root_cause: true`일 때만 초안에 그대로 표시, 도구가 해석하지 않음 |

---

## 7. 명령 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `양식.yaml ...` | — | 입력 양식 1개 이상 (`drafts/*.yaml` 가능) |
| `--out` | `drafts` | 초안·요약표를 저장할 폴더 |
| `--docx` | 꺼짐 | Word 파일도 생성 |
| `--summary` | 꺼짐 | 일괄 처리 요약표 `_summary_<날짜>.md` 생성 |
| `--xlsx` | 꺼짐 | `--summary`와 함께: 요약표를 Excel `_summary_<날짜>.xlsx`로도 (시트 "초안 생성"·"거부", 머리 행 고정·필터) |
| `--rules` | `config/rules.yaml` | 분류 규칙 파일 |
| `--history` | 합성 이력 | 반복성 조회용 이력 CSV |
| `--check-history` | 꺼짐 | `--history` 파일만 점검하고 끝냄 (초안 없음). 양식 파일 지정 불필요 |
| `--today` | 오늘 | `YYYY-MM-DD`. 반복성 조회 기준일과 초안 생성일 (재현·검증용) |

### 종료 코드

다른 스크립트나 일정 작업에서 호출할 때 결과 판정에 씁니다.

| 코드 | 뜻 |
|---|---|
| `0` | 모든 양식의 초안을 만들었음 / `--check-history`: 오류 없음 |
| `1` | 1건 이상 거부됨 (나머지 건의 초안과 요약표는 만들어짐) / `--check-history`: 오류 있음 |
| `2` | `config/rules.yaml` 또는 이력 파일을 쓸 수 없음, 잘못된 옵션 — 아무 초안도 만들지 않음 |

---

## 8. 데이터 취급 주의

- 실제 배치 정보가 담긴 양식·초안·이력은 `drafts/` 또는 저장소 밖에 둡니다. `drafts/`와 `*.docx`는 git에 올라가지 않지만, 다른 폴더의 `.md`·`.yaml`은 올라갈 수 있습니다.
- `git status`에 실제 deviation 파일이 보이면 커밋하지 마십시오.
- 이 도구의 출력을 실제 GMP 문서에 쓰려면 사내 절차에 따른 검토와, 필요 시 소프트웨어 적격성 평가가 먼저 필요합니다.
