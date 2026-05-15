from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    inputs_dir: Path
    outputs_dir: Path

    upstage_api_key: str
    upstage_base_url: str

    solar_model: str
    solar_max_tokens: int | None

    document_parse_url: str
    document_parse_model: str
    document_parse_output_formats: str

    request_timeout_sec: int
    solar_retries: int
    document_parse_retries: int

    max_problem_chars: int
    max_reference_chars: int


def _get_optional_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    value = int(raw)
    if value <= 0:
        return None
    return value


def load_config() -> AppConfig:
    """
    프로젝트 루트의 .env를 기준으로 환경변수를 읽는다.

    Ubuntu 22.04 LTS / 대회 실전 환경 기준:
    - 루트에서 python3 -m core.run_icac ... 실행 권장
    - core/run_icac.py 직접 실행도 run_icac.py 내부 sys.path 보정으로 지원
    """
    root_dir = Path(__file__).resolve().parent.parent

    load_dotenv(root_dir / ".env")

    api_key = os.getenv("ICAC_KEY")
    if not api_key:
        raise RuntimeError(
            "ICAC_KEY가 없습니다. 프로젝트 루트에 .env 파일을 만들고 "
            "ICAC_KEY=발급받은_KEY 형식으로 저장하세요."
        )

    return AppConfig(
        root_dir=root_dir,
        inputs_dir=root_dir / "inputs",
        outputs_dir=root_dir / "outputs",
        upstage_api_key=api_key,
        upstage_base_url=os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1"),
        solar_model=os.getenv("SOLAR_MODEL", "solar-pro3"),
        solar_max_tokens=_get_optional_int("SOLAR_MAX_TOKENS", default=None),
        document_parse_url=os.getenv(
            "DOCUMENT_PARSE_URL",
            "https://api.upstage.ai/v1/document-digitization",
        ),
        document_parse_model=os.getenv("DOCUMENT_PARSE_MODEL", "document-parse"),
        document_parse_output_formats=os.getenv(
            "DOCUMENT_PARSE_OUTPUT_FORMATS",
            "['markdown', 'html']",
        ),
        request_timeout_sec=int(os.getenv("REQUEST_TIMEOUT_SEC", "300")),
        solar_retries=int(os.getenv("SOLAR_RETRIES", "2")),
        document_parse_retries=int(os.getenv("DOCUMENT_PARSE_RETRIES", "2")),
        max_problem_chars=int(os.getenv("MAX_PROBLEM_CHARS", "24000")),
        max_reference_chars=int(os.getenv("MAX_REFERENCE_CHARS", "18000")),
    )