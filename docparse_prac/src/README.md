# ICAC 2026 Document Parse Practice

ICAC 2026 예선 대비용 Document Parse 프로젝트입니다.

목표:
- PDF/이미지/표 문서를 Document Parse로 Markdown/HTML/JSON 구조화
- 파싱 결과를 기반으로 캠퍼스 문제 해결 아이디어 도출
- ICAC 제출용 답안 초안 생성 프롬프트 만들기

## 1. 설치

```bash
pip install -r requirements.txt
```

## 2. API KEY 설정

```bash
.env 파일 생성:
    ICAC_KEY=발급받은_KEY
```

## 3. 테스트 파일 넣기

```bash
samples/ 폴더에 PDF 또는 이미지 파일을 넣음.
```

## 4. 문서 1개 파싱

```bash
python3 src/parse_document.py --file samples/campus_notice.pdf

이미지나 스캔본 OCR 강제:
python3 src/parse_document.py --file samples/poster.png --ocr force
```

## 5. samples 폴더 전체 파싱

```bash
python3 src/batch_parse.py
```

## 6. ICAC 분석 프롬프트 생성

```bash
python src/make_analysis_prompt.py --markdown outputs/campus_notice/parsed.md

생성된 파일:
    outputs/campus_notice/icac_analysis_prompt.txt

생성된 프롬프트는 ChatGPT에 넣어 ICAC 제출용 답안 초안으로 확장 가능합니다.
``