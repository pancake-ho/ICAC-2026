from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from core.config import AppConfig
from core.utils import (
    ensure_dir,
    now_compact,
    now_string,
    safe_stem,
    save_json,
    save_text,
    preview_text,
)


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".webp",
}


@dataclass(frozen=True)
class ParseArtifacts:
    source_file: Path
    output_dir: Path
    raw_json_path: Path
    markdown_path: Path
    html_path: Path
    meta_path: Path
    markdown: str
    html: str


def validate_document_path(file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"문서 파일이 존재하지 않습니다: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"파일이 아닙니다: {file_path}")

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 확장자입니다: {file_path.suffix}\n"
            f"지원 확장자: {sorted(SUPPORTED_EXTENSIONS)}"
        )


def extract_markdown(result: dict[str, Any]) -> str:
    content = result.get("content", {})

    if isinstance(content, dict):
        markdown = content.get("markdown")
        if isinstance(markdown, str):
            return markdown

    markdown = result.get("markdown")
    if isinstance(markdown, str):
        return markdown

    return ""


def extract_html(result: dict[str, Any]) -> str:
    content = result.get("content", {})

    if isinstance(content, dict):
        html = content.get("html")
        if isinstance(html, str):
            return html

    html = result.get("html")
    if isinstance(html, str):
        return html

    return ""


def _sleep_before_retry(attempt: int) -> None:
    delay = min(2**attempt, 8)
    time.sleep(delay)


def parse_document(
    config: AppConfig,
    file_path: Path,
    ocr: str = "auto",
) -> dict[str, Any]:
    """
    Upstage Document Parse로 문서를 파싱한다.

    ocr:
        - auto: 일반 PDF/문서용
        - force: 스캔본, 이미지, 포스터처럼 OCR이 필요한 경우
    """
    validate_document_path(file_path)

    if ocr not in {"auto", "force"}:
        raise ValueError("ocr 옵션은 'auto' 또는 'force'만 가능합니다.")

    headers = {
        "Authorization": f"Bearer {config.upstage_api_key}",
    }

    data = {
        "model": config.document_parse_model,
        "output_formats": config.document_parse_output_formats,
        "ocr": ocr,
    }

    retryable_status = {429, 500, 502, 503, 504}
    last_error: Exception | None = None
    last_response_text = ""

    for attempt in range(config.document_parse_retries + 1):
        try:
            with file_path.open("rb") as f:
                files = {"document": f}

                response = requests.post(
                    config.document_parse_url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=config.request_timeout_sec,
                )

            if response.status_code == 200:
                return response.json()

            last_response_text = response.text

            if response.status_code not in retryable_status:
                raise RuntimeError(
                    "[Document Parse 실패]\n"
                    f"status_code={response.status_code}\n"
                    f"response={response.text}"
                )

            last_error = RuntimeError(
                "[Document Parse 일시 실패]\n"
                f"status_code={response.status_code}\n"
                f"response={response.text}"
            )

        except requests.RequestException as exc:
            last_error = exc

        if attempt < config.document_parse_retries:
            _sleep_before_retry(attempt)

    raise RuntimeError(
        "[Document Parse 재시도 후 실패]\n"
        f"last_error={last_error}\n"
        f"last_response={last_response_text}"
    ) from last_error


def save_parse_artifacts(
    config: AppConfig,
    file_path: Path,
    result: dict[str, Any],
) -> ParseArtifacts:
    """
    파싱 결과를 outputs/parse/{문서명}/{실행시각}/ 아래에 저장한다.

    기존 방식처럼 문서명 폴더에 바로 저장하면 같은 파일을 여러 번 돌릴 때
    결과가 덮어써질 수 있으므로 run_id를 추가한다.
    """
    document_name = safe_stem(file_path)
    run_id = now_compact()

    output_dir = config.outputs_dir / "parse" / document_name / run_id
    ensure_dir(output_dir)

    raw_json_path = output_dir / "raw_response.json"
    markdown_path = output_dir / "parsed.md"
    html_path = output_dir / "parsed.html"
    meta_path = output_dir / "meta.txt"

    markdown = extract_markdown(result).strip()
    html = extract_html(result).strip()

    if not markdown and html:
        markdown = html

    save_json(raw_json_path, result)
    save_text(markdown_path, markdown)
    save_text(html_path, html)

    if not markdown:
        raise RuntimeError(
            "Document Parse 결과에서 markdown/html 텍스트를 추출하지 못했습니다.\n"
            f"원본 응답은 저장되었습니다: {raw_json_path}"
        )

    meta = f"""[ICAC Document Parse Result]
created_at: {now_string()}
source_file: {file_path}
raw_json: {raw_json_path}
markdown: {markdown_path}
html: {html_path}
markdown_chars: {len(markdown)}
html_chars: {len(html)}

[Markdown Preview]
{preview_text(markdown)}
"""
    save_text(meta_path, meta)

    return ParseArtifacts(
        source_file=file_path,
        output_dir=output_dir,
        raw_json_path=raw_json_path,
        markdown_path=markdown_path,
        html_path=html_path,
        meta_path=meta_path,
        markdown=markdown,
        html=html,
    )


def parse_and_save(
    config: AppConfig,
    file_path: Path,
    ocr: str = "auto",
) -> ParseArtifacts:
    result = parse_document(config=config, file_path=file_path, ocr=ocr)
    return save_parse_artifacts(
        config=config,
        file_path=file_path,
        result=result,
    )