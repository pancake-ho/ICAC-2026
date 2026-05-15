from __future__ import annotations

from typing import Any

from core.config import AppConfig
from core.upstage_client import UpstageClients
from core.utils import extract_json_from_text


def call_solar(
    config: AppConfig,
    clients: UpstageClients,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.25,
    max_tokens: int | None = None,
) -> str:
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

    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    response = clients.solar.chat.completions.create(**kwargs)
    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("Solar Pro 3 응답이 비어 있습니다.")

    return content


def call_solar_json(
    config: AppConfig,
    clients: UpstageClients,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
) -> dict[str, Any]:
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