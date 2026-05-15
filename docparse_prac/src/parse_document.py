"""
문서 1개를 parsing하는 핵심 기능 수행

실행 예시:
    python3 parse_document.py --file samples/campus_notice.pdf

이미지/스캔본일 시 실행 예시:
    python3 parse_document.py --file samples/poster.png --ocr force
"""

import argparse
from pathlib import Path
import requests

from config import (
    UPSTAGE_API_KEY,
    DOCUMENT_PARSE_URL,
    OUTPUTS_DIR,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMATS,
)
from utils import (
    make_output_dir,
    save_json,
    save_text,
    extract_markdown,
    extract_html,
    preview_text,
    now_string,
)


def parse_document(
    file_path: Path,
    model: str = DEFAULT_MODEL,
    output_formats: str = DEFAULT_OUTPUT_FORMATS,
    ocr: str = "auto",
) -> dict:
    """
    Upstage Document Parse API로 문서 1개를 파싱한다.

    Args:
        file_path: PDF 또는 이미지 파일 경로
        model: document-parse
        output_formats: "['markdown', 'html']" 형식 문자열
        ocr:
            - auto: 자동 판단
            - force: 스캔본/이미지처럼 OCR 강제 필요할 때
    """

    if UPSTAGE_API_KEY is None:
        raise RuntimeError(
            "ICAC_KEY가 없습니다. .env 파일에 ICAC_KEY=발급받은_KEY 형식으로 저장하세요."
        )

    if not file_path.exists():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {file_path}")

    headers = {
        "Authorization": f"Bearer {UPSTAGE_API_KEY}",
    }

    data = {
        "model": model,
        "output_formats": output_formats,
        "ocr": ocr,
    }

    with open(file_path, "rb") as f:
        files = {
            "document": f,
        }

        response = requests.post(
            DOCUMENT_PARSE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=300,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Document Parse 실패\n"
            f"status_code={response.status_code}\n"
            f"response={response.text}"
        )

    return response.json()


def save_parse_result(file_path: Path, result: dict) -> None:
    output_dir = make_output_dir(OUTPUTS_DIR, file_path)

    raw_json_path = output_dir / "raw_response.json"
    markdown_path = output_dir / "parsed.md"
    html_path = output_dir / "parsed.html"
    meta_path = output_dir / "meta.txt"

    markdown = extract_markdown(result)
    html = extract_html(result)

    save_json(result, raw_json_path)
    save_text(markdown, markdown_path)
    save_text(html, html_path)

    meta = f"""[Document Parse Practice Result]
created_at: {now_string()}
source_file: {file_path}
raw_json: {raw_json_path}
markdown: {markdown_path}
html: {html_path}

[Markdown Preview]
{preview_text(markdown)}
"""
    save_text(meta, meta_path)

    print("\n파싱 완료")
    print(f"- 원본 파일: {file_path}")
    print(f"- JSON 저장: {raw_json_path}")
    print(f"- Markdown 저장: {markdown_path}")
    print(f"- HTML 저장: {html_path}")
    print("\nMarkdown 미리보기:")
    print("-" * 60)
    print(preview_text(markdown))
    print("-" * 60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="파싱할 PDF 또는 이미지 파일 경로",
    )
    parser.add_argument(
        "--ocr",
        type=str,
        default="auto",
        choices=["auto", "force"],
        help="OCR 옵션. 스캔본/이미지는 force도 테스트",
    )

    args = parser.parse_args()

    file_path = Path(args.file)
    result = parse_document(file_path=file_path, ocr=args.ocr)
    save_parse_result(file_path, result)


if __name__ == "__main__":
    main()