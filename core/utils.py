from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    """
    디렉터리가 없으면 생성한다.
    """
    path.mkdir(parents=True, exist_ok=True)


def now_string() -> str:
    """
    사람이 읽기 쉬운 현재 시각 문자열.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_compact() -> str:
    """
    outputs/solve/{실행시각}/ 폴더명에 쓰기 좋은 현재 시각 문자열.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_stem(file_path: Path) -> str:
    """
    파일 이름에서 확장자를 제거하고 저장용으로 안전한 이름을 만든다.

    예:
        campus notice.pdf -> campus_notice
        문제지(최종).pdf -> 문제지최종
    """
    stem = file_path.stem.strip()
    stem = re.sub(r"\s+", "_", stem)
    stem = re.sub(r"[^0-9a-zA-Z가-힣_\-]", "", stem)
    return stem or "document"


def save_text(path: Path, text: str) -> None:
    """
    UTF-8 텍스트 파일 저장.
    """
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, data: dict[str, Any]) -> None:
    """
    JSON 파일 저장.
    """
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_text(path: Path) -> str:
    """
    UTF-8 텍스트 파일 읽기.
    """
    if not path.exists():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {path}")

    if not path.is_file():
        raise ValueError(f"파일이 아닙니다: {path}")

    return path.read_text(encoding="utf-8")


def preview_text(text: str, max_chars: int = 1200) -> str:
    """
    긴 텍스트 미리보기.
    """
    text = text.strip()

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n...[preview truncated]..."


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """
    모델 출력에서 JSON을 최대한 안전하게 추출한다.

    처리 가능한 형태:
    1. 순수 JSON
    2. ```json ... ``` 코드블록
    3. 앞뒤 설명이 붙고 중간에 JSON 객체가 포함된 경우
    """
    raw = text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return None
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            return None

    return None