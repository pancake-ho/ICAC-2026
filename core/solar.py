from __future__ import annotations

import time
from typing import Any

from core.config import AppConfig
from core.upstage_client import UpstageClients
from core.utils import extract_json_from_text


def _sleep_before_retry(attempt: int) -> None:
    """
    API 일시 실패 대응용 backoff.
    attempt=0이면 1초, 이후 2초, 4초...
    """
    delay = min(2**attempt, 8)
    time.sleep(delay)


def call_solar(
    config: AppConfig,
    clients: UpstageClients,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.25,
    max_tokens: int | None = None,
) -> str:
    """
    Solar Pro 3 호출.

    실전 안정성 보강:
    - 일시적 네트워크/API 오류 재시도
    - 빈 응답 방지
    - max_tokens 환경변수 지원
    """
    effective_max_tokens = max_tokens
    if effective_max_tokens is None:
        effective_max_tokens = config.solar_max_tokens

    kwargs: dict[str, Any] = {
        "model": config.solar_model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": temperature,
    }

    if effective_max_tokens is not None:
        kwargs["max_tokens"] = effective_max_tokens

    last_error: Exception | None = None

    for attempt in range(config.solar_retries + 1):
        try:
            response = clients.solar.chat.completions.create(**kwargs)
            content = response.choices[0].message.content

            if not content or not content.strip():
                raise RuntimeError("Solar Pro 3 응답이 비어 있습니다.")

            return content.strip()

        except Exception as exc:
            last_error = exc
            if attempt >= config.solar_retries:
                break
            _sleep_before_retry(attempt)

    raise RuntimeError(f"Solar Pro 3 호출 실패: {last_error}") from last_error


def call_solar_json(
    config: AppConfig,
    clients: UpstageClients,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """
    Solar 응답을 JSON으로 파싱한다.

    JSON 실패는 여기서 RuntimeError를 던지고,
    pipeline.py에서 fallback JSON을 저장한 뒤 계속 진행한다.
    """
    content = call_solar(
        config=config,
        clients=clients,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
    )

    parsed = extract_json_from_text(content)
    if parsed is None:
        raise RuntimeError(
            "Solar 응답을 JSON으로 파싱하지 못했습니다.\n\n"
            f"[원본 응답]\n{content}"
        )

    return parsed