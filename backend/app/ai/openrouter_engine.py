import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngine, AIEngineError
from app.services.ai_usage import record_usage

# Read timeout for a single attempt. Lower than it looks: the retry-on-
# timeout logic below (TRANSIENT_ERRORS includes httpx.ReadTimeout) means a
# stuck attempt gets abandoned and retried rather than the caller waiting
# out its full duration, and record_usage logs the *cumulative* time across
# every attempt -- a logged 226s reading measured live this session was one
# attempt hitting the old 120s timeout, a 1s retry delay, then a second
# attempt taking ~105s, not one 226s call. A lower per-attempt timeout means
# more, faster tries at landing on a fast provider within the same overall
# wait, instead of staying committed to one bad attempt for two minutes at a
# time. 45s sits above this account's measured p75 generation time (~51s
# includes some slower legitimate large-context calls, so this will
# occasionally abandon and retry a call that would have succeeded on its
# own -- an acceptable trade given the alternative is a multi-minute wait).
TIMEOUT = httpx.Timeout(45.0, connect=10.0)
EMBED_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Left to its own default routing, OpenRouter sometimes lands a request on a
# provider that is technically available but extremely slow. Measured live on
# this account's chat model (deepseek/deepseek-v4-flash) across 50 real calls
# this session: median 17.8s, but p90 187.9s and a max of 226s -- and it's
# not one bad provider. "OpenInference" was the worst repeat offender (8
# calls, averaging 122s, up to 226s) and is named explicitly below. But
# "DigitalOcean" alone returned both a 6s call and a 207s call in this same
# session -- the slowness is congestion across the free-tier provider pool
# generally, not a fixed property of any one provider's name. A growing
# exclude-list can't keep up with that; `preferred_max_latency` is
# OpenRouter's own mechanism for exactly this, asking it to weigh each
# candidate provider's own historical tail latency when it picks one, rather
# than this client guessing after the fact which single name to blacklist
# next. `sort: "throughput"` was tried first and did not help here --
# throughput scores steady-state tokens/sec once generation starts, not the
# slow queueing/cold-start actually being measured (confirmed live: same
# provider, same ~226s, with sort applied) -- so it's not used.
#
# These are measured facts about this account's traffic today, not
# permanent properties of any provider -- if this KB's typical context size
# changes, or OpenRouter's routing or a provider's performance changes,
# SLOW_PROVIDERS and the latency target below are the first things to
# revisit (check ai_usage_logs grouped by provider, the way this was found).
SLOW_PROVIDERS = ["OpenInference"]
PROVIDER_PREFERENCE = {
    "ignore": SLOW_PROVIDERS,
    "preferred_max_latency": {"p90": 15},
}

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

    def __init__(self, api_key: str, model: str, embedding_model: str, db: AsyncSession):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model
        # Same DB context (engine/database file) the caller's session is bound
        # to, so usage logging for this request lands in the same database as
        # the operation it's recording — see app.services.ai_usage.record_usage.
        self.db = db

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
                    json={"model": self.embedding_model, "input": texts, "provider": PROVIDER_PREFERENCE},
                )
                resp.raise_for_status()
                return resp.json()

        try:
            started_at = time.perf_counter()
            data = await _with_retry(_call)
            latency_ms = round((time.perf_counter() - started_at) * 1000)
            ordered = sorted(data["data"], key=lambda item: item["index"])
            asyncio.create_task(
                record_usage(
                    self.embedding_model,
                    "embedding",
                    data.get("usage"),
                    self.db,
                    provider=data.get("provider"),
                    latency_ms=latency_ms,
                )
            )
            return [item["embedding"] for item in ordered]
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter embedding request failed: {_describe_error(exc)}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter embedding response malformed: {exc}") from exc

    def _chat_payload(
        self,
        system_prompt: str,
        context: str,
        user_query: str,
        temperature: float | None,
        history: list[tuple[str, str]] | None,
    ) -> dict:
        messages = [{"role": "system", "content": system_prompt}]
        for prior_question, prior_answer in history or []:
            messages.append({"role": "user", "content": prior_question})
            messages.append({"role": "assistant", "content": prior_answer})
        messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"})
        payload = {"model": self.model, "messages": messages, "provider": PROVIDER_PREFERENCE}
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def generate(
        self,
        system_prompt: str,
        context: str,
        user_query: str,
        temperature: float | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")

        payload = self._chat_payload(system_prompt, context, user_query, temperature, history)

        async def _call():
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=self._headers(), json=payload)
                resp.raise_for_status()
                return resp.json()

        try:
            started_at = time.perf_counter()
            data = await _with_retry(_call)
            latency_ms = round((time.perf_counter() - started_at) * 1000)
            asyncio.create_task(
                record_usage(
                    self.model,
                    "chat",
                    data.get("usage"),
                    self.db,
                    provider=data.get("provider"),
                    finish_reason=data["choices"][0].get("finish_reason"),
                    latency_ms=latency_ms,
                )
            )
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter chat request failed: {_describe_error(exc)}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter chat response malformed: {exc}") from exc

    async def generate_stream(
        self,
        system_prompt: str,
        context: str,
        user_query: str,
        temperature: float | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")

        payload = self._chat_payload(system_prompt, context, user_query, temperature, history)
        payload["stream"] = True
        # Puts token counts and cost in the final chunk, so streamed calls are
        # logged to ai_usage_logs the same as non-streamed ones.
        payload["usage"] = {"include": True}

        usage: dict | None = None
        provider: str | None = None
        finish_reason: str | None = None
        yielded = False
        started_at = time.perf_counter()
        try:
            for attempt in range(RETRY_ATTEMPTS):
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                        async with client.stream(
                            "POST", f"{OPENROUTER_BASE_URL}/chat/completions", headers=self._headers(), json=payload
                        ) as resp:
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                chunk = parse_stream_line(line)
                                if chunk is None:
                                    continue
                                if chunk is STREAM_DONE:
                                    break
                                if chunk.get("error"):
                                    raise AIEngineError(f"OpenRouter stream error: {chunk['error']}")
                                provider = chunk.get("provider") or provider
                                usage = chunk.get("usage") or usage
                                for choice in chunk.get("choices") or []:
                                    finish_reason = choice.get("finish_reason") or finish_reason
                                    text = (choice.get("delta") or {}).get("content")
                                    if text:
                                        yielded = True
                                        yield text
                    break
                except TRANSIENT_ERRORS:
                    # Text already shown can't be taken back by a silent retry
                    # that might phrase things differently, so only a failure
                    # before the first piece is retried.
                    if yielded or attempt == RETRY_ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter chat request failed: {_describe_error(exc)}") from exc
        except ValueError as exc:
            raise AIEngineError(f"OpenRouter chat stream malformed: {exc}") from exc

        latency_ms = round((time.perf_counter() - started_at) * 1000)
        asyncio.create_task(
            record_usage(
                self.model, "chat", usage, self.db, provider=provider, finish_reason=finish_reason, latency_ms=latency_ms
            )
        )


STREAM_DONE = object()


def parse_stream_line(line: str):
    """One line of OpenRouter's server-sent-event stream: the decoded chunk
    dict, STREAM_DONE for the closing `data: [DONE]`, or None for anything
    to skip (blank separators and `: OPENROUTER PROCESSING` keep-alives)."""
    if not line.startswith("data:"):
        return None
    data = line[len("data:"):].strip()
    if data == "[DONE]":
        return STREAM_DONE
    return json.loads(data)
