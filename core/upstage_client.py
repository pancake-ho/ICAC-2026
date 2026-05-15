from __future__ import annotations

from openai import OpenAI

from core.config import AppConfig


class UpstageClients:
    """
    Upstage API 클라이언트 묶음.

    Solar Pro 3:
    - OpenAI 호환 Chat Completions 방식 호출

    Document Parse:
    - requests 기반 multipart/form-data 호출
    - 실제 호출은 core/docparse.py에서 수행
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.solar = OpenAI(
            api_key=config.upstage_api_key,
            base_url=config.upstage_base_url,
            timeout=config.request_timeout_sec,
        )