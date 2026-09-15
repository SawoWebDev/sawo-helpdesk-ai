import asyncio

import httpx

from app.ai.base import AIEngine, AIEngineError
from app.services.ai_usage import record_usage

TIMEOUT = httpx.Timeout(120.0, connect=10.0)
EMBED_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Transient, retry-worthy network failures (DNS blips, dropped connections,
# read timeouts) as opposed to a real HTTP error response from the server
# (bad request, rate limit, model unavailable) — those aren't retried here
# since retrying won't help. Seen live: the container's DNS resolver
# intermittently failing to resolve openrouter.ai, which silently sent every
# question to the fallback message with no retry.
TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError)
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


def _describe_error(exc: Exception) -> str:
    """httpx sometimes leaves a low-level connection error's own message
    empty, with the real detail only in __cause__ (e.g. a raw OSError from
    DNS resolution) — str(exc) alone can silently come out blank."""
    text = str(exc) or repr(exc)
    if exc.__cause__ is not None:
        cause_text = str(exc.__cause__)
        if cause_text and cause_text not in text:
            text = f"{text} ({cause_text})" if text else cause_text
    return text


async def _with_retry(call):
    """Runs `call` (a zero-arg async callable), retrying on transient network
    errors with a short delay. Any other exception propagates immediately."""
    last_exc: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await call()
        except TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise last_exc


class OpenRouterEngine(AIEngine):
    name = "openrouter"

    def __init__(self, api_key: str, model: str, embedding_model: str):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")

        async def _call():
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.embedding_model, "input": texts},
                )
                resp.raise_for_status()
                return resp.json()

        try:
            data = await _with_retry(_call)
            ordered = sorted(data["data"], key=lambda item: item["index"])
            asyncio.create_task(record_usage(self.embedding_model, "embedding", data.get("usage")))
            return [item["embedding"] for item in ordered]
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter embedding request failed: {_describe_error(exc)}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter embedding response malformed: {exc}") from exc

    async def generate(self, system_prompt: str, context: str, user_query: str) -> str:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"},
        ]

        async def _call():
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "messages": messages},
                )
                resp.raise_for_status()
                return resp.json()

        try:
            data = await _with_retry(_call)
            asyncio.create_task(record_usage(self.model, "chat", data.get("usage")))
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter chat request failed: {_describe_error(exc)}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter chat response malformed: {exc}") from exc
