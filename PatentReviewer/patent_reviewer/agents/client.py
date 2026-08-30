from __future__ import annotations

import json
import asyncio

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel

from ..config import Settings


def _strict_json_schema(model: type[BaseModel]) -> dict[str, object]:
    schema = model.model_json_schema()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["additionalProperties"] = False
                properties = value.get("properties")
                if isinstance(properties, dict):
                    value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


class _CompatibleResponses:
    def __init__(self, client: AsyncOpenAI, settings: Settings):
        self._client = client
        self._settings = settings

    async def parse(self, *, model: str, input: str, text_format: type[BaseModel], store: bool = False):
        # The configured third-party gateway exposes Chat Completions but not
        # the Responses endpoint. Avoid waiting for a Responses timeout.
        if "api.openai.com" not in self._settings.openai_base_url:
            return await self._chat_parse(model=model, input=input, text_format=text_format)
        try:
            response = await self._client.responses.parse(
                model=model, input=input, text_format=text_format, store=store,
            )
            if response.output_parsed is not None:
                return response
        except Exception:
            pass

        return await self._chat_parse(model=model, input=input, text_format=text_format)

    async def _chat_parse(self, *, model: str, input: str, text_format: type[BaseModel]):
        base_url = self._settings.openai_base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
            "User-Agent": self._settings.openai_user_agent or "PatentClaw-Reviewer/0.1",
        }
        request = {
            "model": model,
            "messages": [{"role": "user", "content": input}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": text_format.__name__,
                    "strict": True,
                    "schema": _strict_json_schema(text_format),
                },
            },
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.openai_timeout_seconds), headers=headers,
        ) as client:
            result = None
            for attempt in range(5):
                result = await client.post(f"{base_url}/chat/completions", json=request)
                if result.status_code != 429 or attempt == 4:
                    break
                retry_after = result.headers.get("retry-after")
                try:
                    delay = min(60.0, max(1.0, float(retry_after))) if retry_after else 2.0 ** attempt
                except ValueError:
                    delay = 2.0 ** attempt
                await asyncio.sleep(delay)
            result.raise_for_status()
        body = result.json()
        content = body.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError("Structured gateway response did not contain message content")
        parsed = text_format.model_validate(json.loads(content))

        class ParsedResponse:
            output_parsed = parsed

        return ParsedResponse()


class _CompatibleClient:
    def __init__(self, client: AsyncOpenAI, settings: Settings):
        self.responses = _CompatibleResponses(client, settings)


def build_client(settings: Settings) -> _CompatibleClient:
    if not settings.openai_api_key:
        raise ValueError("Online mode requires PR_OPENAI_API_KEY")
    headers = {"User-Agent": settings.openai_user_agent} if settings.openai_user_agent else None
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        default_headers=headers,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    return _CompatibleClient(client, settings)
