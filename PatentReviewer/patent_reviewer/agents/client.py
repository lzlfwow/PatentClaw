from __future__ import annotations

from openai import AsyncOpenAI

from ..config import Settings


def build_client(settings: Settings) -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise ValueError("Online mode requires PR_OPENAI_API_KEY")
    headers = {"User-Agent": settings.openai_user_agent} if settings.openai_user_agent else None
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        default_headers=headers,
    )
