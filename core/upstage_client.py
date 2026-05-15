from __future__ import annotations

from openai import OpenAI

from core.config import AppConfig


class UpstageClients:
    """
    Upstage API 클라이언트 묶음.

    Solar Pro 3는 OpenAI 호환 Chat Completions 방식으로 호출하고,
    Document Parse는 requests 기반 multipart/form-data로 호출한다.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.solar = OpenAI(
            api_key=config.upstage_api_key,
            base_url=config.upstage_base_url,
        )