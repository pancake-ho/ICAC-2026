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
    document_parse_url: str
    document_parse_model: str
    document_parse_output_formats: str

    request_timeout_sec: int


def load_config() -> AppConfig:
    """
    프로젝트 루트의 .env를 기준으로 환경변수를 읽는다.

    실전에서는 run_icac.py를 루트에서 실행한다고 가정한다.
    그래도 어느 위치에서 실행하더라도 동작하도록 파일 위치 기준 root를 계산한다.
    """
    root_dir = Path(__file__).resolve().parent.parent

    # 루트 .env 우선 로드
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
        upstage_base_url="https://api.upstage.ai/v1",
        solar_model=os.getenv("SOLAR_MODEL", "solar-pro3"),
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
    )