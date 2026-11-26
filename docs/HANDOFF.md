# HANDOFF — 현재 상태와 다음 할 일

> 작업이 끝날 때마다 갱신합니다 (규칙: [`CLAUDE.md`](../CLAUDE.md)).
> **마지막 갱신: 2026-11-26** · 기준 브랜치 `main` · 테스트 317개 통과 + 웹 화면 검사(엔진 36 · 실제 입력 15 · 화면) · **CI 통과 시 Claude가 자동 머지** (CI 6개: Ubuntu Python 3.10–3.13, Windows 3.12, web) · 도구 버전 `devdraft 0.5.0`
>
> **프로젝트 목적: 입사 포트폴리오.** 실제 회사 도입이 아니므로 회사 SOP·사내 적격성 평가는 범위 밖입니다. 우선순위는 "검토자가 처음 1분에 보고 이해하는가"입니다.

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
| 자동 테스트(CI) — PR·main마다 GitHub에서 테스트 실행 | ✅ Ubuntu 3.10–3.13 + Windows |
| 영문 Windows 콘솔에서 한국어 메시지 | ✅ (이전에는 오류로 종료) |
| 포트폴리오용 결과물 미리보기 — 현실적 합성 사례 4건의 초안 PDF·이미지, README 갤러리 | ✅ `sample_output/showcase/` |
| README를 포트폴리오 첫 화면으로 (설계 판단·재현해서 고친 결함·영문 요약) | ✅ |
| 튜토리얼 [`docs/TUTORIAL.md`](TUTORIAL.md) — 실제 명령·출력, 테스트로 대조 | ✅ |
| 요약표 Word 출력 (`--summary --docx`, 가로 방향) | ✅ |
| 요약표 Excel 출력 (`--summary --xlsx`, 수식 주입 방지) | ✅ (openpyxl, 사용자 승인) |
| 템플릿을 직접 채워 본 결과 (안내 문구가 사건 경위에 섞임, 발견 일시 검증 없음) | ✅ 수정 |
| 반복성 조회를 못 한 경우 "없음" 대신 "조회 안 함"으로 표시 | ✅ |
| 규칙에 없는 기준에 "예"로 답한 항목을 제안 아래에 명시 | ✅ |
| Windows `cmd`·PowerShell의 `*.yaml`, 없는 파일 | ✅ (이전에는 오류로 종료) |
| 한국어 Excel 기본 "CSV"(CP949) 이력 파일 | ✅ 경고와 함께 읽음 (사용자 결정) |
| 위험 질문 8개 — "환자 안전 영향"(CRITICAL 트리거), "규제 신고 대상"(등급과 별개, ☐ 신고 검토 항목) | ✅ (사용자 결정) |
| 입력 문장이 Markdown 기호를 포함해도 입력 그대로 표시 (`\|` 때문에 표 열이 밀리던 문제 포함) | ✅ |
| 처음 쓰는 사람용 화면: 한국어 `--help`(예시·종료 코드), 만든 파일 전부 표시, 마지막에 건수·저장 위치·다음 할 일 | ✅ |
| 한국어 Windows에서 출력을 파일로 저장할 때(cp949) 오류로 멈추던 문제 | ✅ 수정, CI에 Windows PowerShell 실행 단계 추가 |
| 빈 양식 만들기 `--new 번호` (Windows·macOS 같은 명령), 설치 안내(ZIP·Python·자주 나는 오류) | ✅ |
| 양식에 따옴표 없이 적은 숫자 모양 값(배치 0412 등)을 적힌 그대로 초안에 표시 | ✅ (이전에는 266으로 바뀌고 오류로 종료) |
| 브라우저 화면 `web/` — 여러 건 관리, 빠진 항목·제안 등급·반복 건·보고 기한, Word 내보내기, YAML 가져오기. CLI 결과와 대조 테스트 | ✅ 게시본: claude.ai 아티팩트 "Deviation 초안 데스크" (비공개) — **실제 화면에서 Word 저장은 사용자 확인 필요** |
| 같은 항목을 두 번 적은 양식·rules.yaml 거부 | ✅ (이전에는 뒤의 값이 말없이 쓰여 등급이 바뀜) |
| 회사 실제 SOP 반영 | — 포트폴리오라 범위 밖 (공개 SOP 예시로 방법을 보여 줌) |

## 2. 머지된 작업

| PR | 내용 |
|---|---|
| [#1](https://github.com/strawberryHunter/gmp-deviation-draft/pull/1) | 입력 검증, 빈 양식, `--summary`, rules.yaml SOP 대비 구조, 사용 가이드 |
| [#2](https://github.com/strawberryHunter/gmp-deviation-draft/pull/2) | 이력 CSV 점검, 합성 SOP 예시, `manual_checks` |
| [#3](https://github.com/strawberryHunter/gmp-deviation-draft/pull/3) | Word 초안 서식 |
| [#4](https://github.com/strawberryHunter/gmp-deviation-draft/pull/4) | 생성 근거 기록, 합성 이력 오용 방지 |
| [#5](https://github.com/strawberryHunter/gmp-deviation-draft/pull/5) | 공개 SOP(Duke) 매핑, 용어 "deviation" 통일 |
| [#6](https://github.com/strawberryHunter/gmp-deviation-draft/pull/6) | CLAUDE.md, 이 HANDOFF 문서 |
| [#7](https://github.com/strawberryHunter/gmp-deviation-draft/pull/7) | CI(Ubuntu 3.10–3.13, Windows), 영문 Windows 콘솔 오류·OS별 해시 차이 수정 |
| [#8](https://github.com/strawberryHunter/gmp-deviation-draft/pull/8) | 포트폴리오 결과물 미리보기 (현실적 합성 사례 4건 PDF·이미지) |
| [#9](https://github.com/strawberryHunter/gmp-deviation-draft/pull/9) | README 포트폴리오 첫 화면, 자동 머지 규칙 |
| [#10](https://github.com/strawberryHunter/gmp-deviation-draft/pull/10) | 튜토리얼(출력 테스트로 대조), 요약표 Word, Windows 와일드카드·없는 파일 |
| [#11](https://github.com/strawberryHunter/gmp-deviation-draft/pull/11) | 입력한 사실을 그대로 표시 (Markdown 기호 때문에 표 열이 밀리던 문제) |
| [#12](https://github.com/strawberryHunter/gmp-deviation-draft/pull/12) | 사용자 결정 반영, CP949 이력 자동 읽기 |
| [#13](https://github.com/strawberryHunter/gmp-deviation-draft/pull/13) | 위험 질문 2개 추가: 환자 안전 영향(CRITICAL), 규제 신고 대상(검토 항목) |
| [#14](https://github.com/strawberryHunter/gmp-deviation-draft/pull/14) | 요약표 Excel 출력 (수식 주입 방지) |
| [#15](https://github.com/strawberryHunter/gmp-deviation-draft/pull/15) | 템플릿 안내 문구가 사건 경위에 섞이던 문제, 발견 일시 검증 |
| [#16](https://github.com/strawberryHunter/gmp-deviation-draft/pull/16) | 반복성 조회를 못 한 경우 "없음" 대신 "조회 안 함" |
| [#17](https://github.com/strawberryHunter/gmp-deviation-draft/pull/17) | 규칙에 없는 기준에 "예"로 답한 항목을 제안 아래에 명시 |
| [#18](https://github.com/strawberryHunter/gmp-deviation-draft/pull/18) | HANDOFF 갱신 (포트폴리오 공개 준비 할 일) |
| [#19](https://github.com/strawberryHunter/gmp-deviation-draft/pull/19) | 처음 쓰는 사람 기준 화면 개선: 한국어 도움말, 만든 파일 전부 표시, 실행 끝 요약 줄 |
| [#20](https://github.com/strawberryHunter/gmp-deviation-draft/pull/20) | 한국어 Windows 출력 오류 수정, `--new`, 설치 안내, CI에 Windows PowerShell 사용자 경로 |
| [#21](https://github.com/strawberryHunter/gmp-deviation-draft/pull/21) | 화면의 파일 경로를 짧게 (현재 폴더 기준) |
| [#22](https://github.com/strawberryHunter/gmp-deviation-draft/pull/22) | 양식의 숫자 모양 값(0412, 1:30, 3.40)을 적힌 그대로 읽음 (이전에는 값이 바뀌고 오류로 중단) |
| [#23](https://github.com/strawberryHunter/gmp-deviation-draft/pull/23) | 브라우저 화면 `web/` 추가 (사이드바 리디자인, YAML 가져오기), CI에 web 작업, CLI 기준값 대조 |
| [#24](https://github.com/strawberryHunter/gmp-deviation-draft/pull/24) | 같은 항목이 두 번 있는 양식·rules.yaml 거부 (이전에는 뒤의 값을 말없이 사용) |
| [#25](https://github.com/strawberryHunter/gmp-deviation-draft/pull/25) | 웹: 더보기 메뉴 깨짐(글자가 세로로 쌓임), 완료한 초안 카드의 빨간 D+ 표시, 낮은 화면에서 메뉴 서랍 맨 아래(사용법)에 닿지 않던 문제 수정 |
| [#26](https://github.com/strawberryHunter/gmp-deviation-draft/pull/26) | 웹: 내보내기 요약표가 한 화면에 들어오게 (1280px에서 보고 기한·행별 내보내기 버튼이 잘려 있었음), 좁은 화면에서는 표를 행마다 쌓아 표시, 번호·제목 없는 초안은 "번호 미입력 / 제목 없음" |

## 3. 사용자가 해야 할 일 — Claude가 대신할 수 없는 것

위에서부터 중요한 순서입니다. 끝나면 Claude에게 결과를 알려 주세요.

- [ ] **⓪ (선택) 저장소를 공개(Public)로 전환** — 지원서에는 포트폴리오 PDF(대화에서 받은 파일)만 첨부해도 됩니다. 면접관이 코드를 보고 싶어 할 때 전환하십시오. 비공개 상태에서는 링크가 404입니다. 이 세션은 저장소 설정을 바꿀 권한이 없습니다(2026-11-25 시도, 403).
  - Settings → General → 맨 아래 Danger Zone → **Change visibility** → Public
  - 공개 전 점검 완료: 추적 파일에 비밀값·개인 이메일 없음, 커밋 이메일은 GitHub noreply 주소
  - 같은 화면에서 함께: About(오른쪽 톱니)에 주제 태그 `gmp` `gxp` `deviation-management` `data-integrity` `quality-assurance` `python` 추가, 프로필에서 **Pin**
- [ ] **⓪-2 포트폴리오 페이지 공유** — claude.ai 아티팩트(대화에서 받은 링크) 오른쪽 위 Share에서 링크 공유 켜기. 공유 후 README나 이력서에 링크를 넣을지 Claude에게 알려 주세요.

- [ ] **⓪-3 웹 화면에서 Word 저장 한 번 눌러 보기** — 게시된 "Deviation 초안 데스크"에서 예시 불러오기 → 카드 열기 → 내보내기 → Word. 저장 확인 창이 뜨고 .docx가 받아지는지 알려 주세요. 테스트는 저장 기능의 대역으로만 했습니다.

- [ ] **① Word 초안을 실제 Word에서 열어 보기** — 작업 환경에 맑은 고딕이 없어 화면 확인을 못 했습니다.
  1. 바로 볼 수 있는 렌더링 결과: [`sample_output/showcase/`](../sample_output/showcase/)의 PDF (이 환경의 대체 글꼴로 렌더링됨). Word 원본이 필요하면 "프롬프트 A" 또는 `python scripts/make_showcase.py`
  2. 확인할 것: 모든 쪽 머리글의 빨간 "초안 — 승인 문서 아님" · 빈칸 노란 강조 · 한글이 맑은 고딕으로 보이는지
  3. 이상하면 화면 캡처를 Claude에게 보내기
- [ ] **② CI 결과 확인** — PR 화면 아래쪽 "Checks"가 초록색 ✅인지 봐 주세요. 빨간 ❌면 Claude에게 "CI 실패 고쳐줘"

- [ ] **③ GitHub 브랜치 정리** — 이 세션은 원격 브랜치를 지울 권한이 없습니다. 머지가 끝난 아래 브랜치는 지워도 내용이 사라지지 않습니다. 포트폴리오 저장소가 깔끔해 보입니다.
  `fix/flag-validation-template`, `feat/history-check`, `feat/docx-format`, `feat/traceability`, `feat/public-sop-example`, `docs/handoff`, `ci/github-actions`, `feat/showcase`, `docs/readme-portfolio`, `feat/summary-docx`, `fix/verbatim-facts`, `decisions/resolve-open-items`, `feat/new-risk-questions`, `feat/summary-xlsx`, `fix/template-comment-leak`, `fix/recurrence-not-checked`, `fix/unused-yes-answers`
  - 지우는 곳: 저장소 → Branches → 각 줄의 휴지통 아이콘
  - 앞으로 자동으로 지우려면: Settings → General → **Automatically delete head branches** 켜기

## 4. 다음 작업 후보 — Claude에게 그대로 복사해서 보내는 프롬프트

### 프롬프트 A — 확인용 Word 초안 만들기
```
CLAUDE.md와 docs/HANDOFF.md를 읽고, 합성 샘플 3건(DEV-2026-2201~2203)의 Word 초안을
--today 2026-11-24 로 만들어서 파일로 보내줘. 확인할 것도 같이 알려줘.
```

### 프롬프트 B — 다른 SOP 반영 (포트폴리오 범위 밖, 참고용)
```
CLAUDE.md와 docs/HANDOFF.md를 읽고 시작해.
아래는 우리 회사 deviation SOP의 등급 정의 부분이야. 원문은 저장소에 넣지 말고,
docs/sop_mapping/Duke_COMM-PAS-013.md 와 같은 방식으로 조항별 매핑 문서와
config/rules.yaml 을 만들어줘. SOP에 없는 등급은 만들지 말고, 도구가 판단 못 하는 조항은
manual_checks 로 남겨. 애매한 해석은 DECISIONS.md 에 "확인 필요"로 적어.

SOP 번호/개정: <예: QA-SOP-012 Rev.05>
<등급 정의 부분 붙여넣기>
```

### 프롬프트 C — 다음 개선 (목적과 관계없이 유용, 위에서부터 권장)
```
CLAUDE.md와 docs/HANDOFF.md를 읽고, "다음 개선 후보" 중 맨 위 항목을 진행해줘.
```

**다음 개선 후보** (Claude가 끝낼 때마다 이 목록을 갱신, 포트폴리오 기준 우선순위)

1. **웹: 다른 규칙 파일 선택** — 지금은 기본 rules.yaml만 내장. Duke 예시 규칙을 고를 수 있게 (CLI 기준값에 Duke 결과 추가).
2. **웹: 미리보기 패널의 Tab 이동 가두기** — 지금은 Tab이 뒤 화면으로 나감 (Esc로는 닫힘).
3. **웹: 초안을 YAML로 내보내기** — 화면에서 쓴 초안을 CLI 양식으로 저장.

## 5. 참고 문서
- 사용법: [`docs/USAGE.md`](USAGE.md)
- 판단 기록: [`DECISIONS.md`](../DECISIONS.md)
- SOP 매핑 예시: [`docs/sop_mapping/Duke_COMM-PAS-013.md`](sop_mapping/Duke_COMM-PAS-013.md), [`config/examples/`](../config/examples/)
