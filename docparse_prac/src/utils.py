"""
저장 및 파일 추출 수행
"""

import json
from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_stem(file_path: Path) -> str:
    """
    파일 이름에서 확장자를 제거한 안전한 저장용 이름을 반환한다.
    예:
    campus notice.pdf -> campus_notice
    """
    return file_path.stem.replace(" ", "_")


def make_output_dir(base_output_dir: Path, file_path: Path) -> Path:
    """
    파일별 결과 저장 폴더 생성.
    예:
    outputs/campus_notice/
    """
    output_dir = base_output_dir / safe_stem(file_path)
    ensure_dir(output_dir)
    return output_dir


def save_json(data: dict, path: Path) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(text: str, path: Path) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def extract_markdown(result: dict) -> str:
    """
    Upstage Document Parse 응답에서 markdown을 최대한 안전하게 추출한다.
    API 응답 구조가 조금 달라도 터지지 않게 방어적으로 작성.
    """
    content = result.get("content", {})

    if isinstance(content, dict):
        markdown = content.get("markdown")
        if markdown:
            return markdown

    markdown = result.get("markdown")
    if markdown:
        return markdown

    return ""


def extract_html(result: dict) -> str:
    """
    Upstage Document Parse 응답에서 html을 최대한 안전하게 추출한다.
    """
    content = result.get("content", {})

    if isinstance(content, dict):
        html = content.get("html")
        if html:
            return html

    html = result.get("html")
    if html:
        return html

    return ""


def preview_text(text: str, max_chars: int = 800) -> str:
    if not text:
        return ""
    return text[:max_chars]