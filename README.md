# ICAC-2026

ICAC 2026 예선 대비용 Upstage API 실전 파이프라인입니다.

## 목표

대회 공지에서 제시한 사전학습 항목을 하나의 실전 흐름으로 연결합니다.

1. Solar Pro 3 활용
2. Document Parse 활용
3. Upstage API 활용

핵심 흐름은 다음과 같습니다.

```text
문제 PDF / 이미지 / 공지 문서
→ Document Parse로 구조화
→ Solar Pro 3로 문제 해석 및 답안 생성
→ hallucination / 개인정보 / 구현 가능성 검토
→ 제출용 markdown 저장
```

## 프로젝트 구조

```text
ICAC-2026/
├── docparse_prac/              # 기존 Document Parse 연습용 코드
├── icac_core/                  # 실전용 핵심 코드
│   ├── __init__.py
│   ├── config.py
│   ├── upstage_client.py
│   ├── docparse.py
│   ├── solar.py
│   ├── prompts.py
│   ├── pipeline.py
│   └── utils.py
├── inputs/                     # 실전 문제 파일 또는 참고 문서 입력 폴더
├── outputs/                    # 파싱 결과 및 답안 생성 결과 저장 폴더
├── run_icac.py                 # 실전 CLI 실행 파일
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── test_api.py                 # 기존 Solar Pro 3 단독 호출 테스트용 파일
```

## 설치

Ubuntu 22.04 LTS 기준입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 작성합니다.

```bash
ICAC_KEY=your_upstage_api_key_here
```

`.env.example`을 복사해서 사용할 수 있습니다.

```bash
cp .env.example .env
```

실제 API Key가 들어간 `.env` 파일은 GitHub에 올리면 안 됩니다.

## 사용법

### 1. 문서 파싱

PDF 또는 이미지 문서를 Document Parse로 구조화합니다.

```bash
python3 run_icac.py parse --file inputs/problem.pdf
```

스캔본 또는 이미지 문서라면 OCR을 강제할 수 있습니다.

```bash
python3 run_icac.py parse --file inputs/problem.png --ocr force
```

### 2. 파싱 결과 요약

이미 파싱된 `parsed.md`를 Solar Pro 3로 요약하고 ICAC 관점에서 분석합니다.

```bash
python3 run_icac.py summary --parsed outputs/parse/problem/parsed.md
```

결과를 파일로 저장하려면 `--out` 옵션을 사용합니다.

```bash
python3 run_icac.py summary \
  --parsed outputs/parse/problem/parsed.md \
  --out outputs/summary.md
```

### 3. 텍스트 문제로 답안 생성

문제 원문이 텍스트 파일로 있을 때 사용합니다.

```bash
python3 run_icac.py solve-text --problem inputs/problem.txt
```

참고 문서가 있을 경우 함께 넣을 수 있습니다.

```bash
python3 run_icac.py solve-text \
  --problem inputs/problem.txt \
  --reference outputs/parse/notice/parsed.md
```

### 4. 문제 문서를 파싱하고 바로 답안 생성

문제 파일이 PDF 또는 이미지일 때 가장 실전적인 방식입니다.

```bash
python3 run_icac.py solve-doc --file inputs/problem.pdf
```

스캔본 또는 이미지 문서라면 OCR을 강제합니다.

```bash
python3 run_icac.py solve-doc --file inputs/problem.png --ocr force
```

추가 지시를 넣고 싶다면 `--instruction` 옵션을 사용합니다.

```bash
python3 run_icac.py solve-doc \
  --file inputs/problem.pdf \
  --instruction "Django 백엔드와 DB 구현 가능성을 강조해줘"
```

## 출력 결과

결과는 `outputs/` 아래에 저장됩니다.

```text
outputs/
├── parse/
│   └── 문서명/
│       ├── raw_response.json
│       ├── parsed.md
│       ├── parsed.html
│       └── meta.txt
└── solve/
    └── 실행시각/
        ├── 00_problem_analysis.json
        ├── problem.txt
        ├── 01_draft_answer.md
        ├── 02_review.md
        └── 03_final_answer.md
```

각 파일의 의미는 다음과 같습니다.

```text
raw_response.json
- Document Parse API의 원본 응답입니다.

parsed.md
- 문서에서 추출된 markdown 결과입니다.
- Solar Pro 3 입력으로 사용하기 좋습니다.

parsed.html
- 문서 레이아웃을 HTML 형태로 확인할 수 있는 결과입니다.

meta.txt
- 원본 파일 경로, 생성 시각, markdown preview 등을 기록합니다.

00_problem_analysis.json
- 문제 요구사항, 대상 사용자, AI 기능, MVP 범위, 리스크, 지표를 JSON으로 구조화한 결과입니다.

01_draft_answer.md
- Solar Pro 3가 생성한 1차 제출 답안 초안입니다.

02_review.md
- 심사위원 관점에서 초안을 검토한 결과입니다.

03_final_answer.md
- 검토 내용을 포함한 최종 제출 후보입니다.
```

## 실전 사용 전략

ICAC 예선에서 문제 파일이 제공되면 다음 순서로 진행합니다.

```text
1. 문제 파일을 inputs/ 폴더에 넣는다.
2. solve-doc으로 Document Parse와 답안 생성을 한 번에 수행한다.
3. outputs/solve/실행시각/03_final_answer.md를 확인한다.
4. hallucination, 개인정보, 구현 가능성, 지표를 직접 검토한다.
5. 제출 형식에 맞게 문장을 다듬어 제출한다.
```

추천 실행 명령어는 다음과 같습니다.

```bash
python3 run_icac.py solve-doc --file inputs/problem.pdf
```

이미 문제 원문을 텍스트로 옮긴 경우에는 다음 명령어를 사용합니다.

```bash
python3 run_icac.py solve-text --problem inputs/problem.txt
```

## 제출 전 체크리스트

최종 제출 전 반드시 아래 항목을 확인합니다.

```text
[문제 적합성]
- 문제 요구사항에 직접 답했는가?
- 캠퍼스 문제와 명확히 연결되는가?
- 대상 사용자가 구체적인가?

[AI 활용]
- AI 활용이 장식이 아니라 핵심 기능인가?
- Document Parse, Solar Pro 3, Upstage API 활용 흐름이 자연스러운가?
- 단순 챗봇 제안으로 끝나지 않는가?

[실현 가능성]
- MVP 범위가 현실적인가?
- Django 백엔드, DB, API, 관리자 페이지 기준으로 구현 설명이 가능한가?
- 제한 시간 안에 설명 가능한 구조인가?

[기대 효과]
- 학생 편의성, 행정 효율, 정보 접근성 개선이 드러나는가?
- 성과 지표가 정량 또는 준정량으로 제시되었는가?

[리스크]
- 개인정보 보호 방안이 있는가?
- hallucination 대응이 있는가?
- 관리자 검토 또는 출처 표시 구조가 있는가?
- 운영 부담과 악성 사용 대응이 있는가?

[문장 품질]
- 첫 문단만 읽어도 무엇을 해결하는지 보이는가?
- 제목이 짧고 명확한가?
- 불필요하게 긴 문장이 없는가?
```

## 좋은 답안 구조

ICAC 예선 답안은 아래 구조를 기본으로 사용합니다.

```text
제목

1. 문제 정의
2. 대상 사용자
3. 기존 문제점
4. 제안 솔루션
5. AI 활용 방식
6. 시스템 흐름
7. 구현 가능성
8. 기대 효과
9. 리스크 및 대응
10. 성과 지표
11. 결론
```

## 코드 사용 예시

### 문제 PDF를 바로 제출용 답안으로 변환

```bash
python3 run_icac.py solve-doc --file inputs/campus_problem.pdf
```

### 이미지 포스터 또는 스캔본 문제를 처리

```bash
python3 run_icac.py solve-doc --file inputs/problem_image.png --ocr force
```

### 텍스트 문제를 처리

```bash
python3 run_icac.py solve-text --problem inputs/problem.txt
```

### 참고 문서 기반 답안 생성

```bash
python3 run_icac.py solve-text \
  --problem inputs/problem.txt \
  --reference outputs/parse/reference/parsed.md
```

## 주의사항

- AI가 생성한 답안을 그대로 제출하지 않습니다.
- 문서에 없는 내용을 확정적으로 쓰지 않습니다.
- 개인정보, 학교 내부 정보, API Key는 GitHub에 올리지 않습니다.
- API 응답이 길거나 JSON 형식이 깨질 수 있으므로 결과 파일을 반드시 확인합니다.
- 제출 전에는 반드시 사람이 최종 검토합니다.

## 한 줄 요약

이 프로젝트는 ICAC 2026 예선에서 문제 문서 입력부터 제출용 답안 생성까지 빠르게 수행하기 위한 Document Parse + Solar Pro 3 + Upstage API 기반 실전 파이프라인입니다.