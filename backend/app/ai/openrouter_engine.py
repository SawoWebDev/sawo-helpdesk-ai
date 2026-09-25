import asyncio
import time

import httpx

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
                    provider=data.get("provider"),
                    latency_ms=latency_ms,
                )
            )
            return [item["embedding"] for item in ordered]
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter embedding request failed: {_describe_error(exc)}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter embedding response malformed: {exc}") from exc

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

        messages = [{"role": "system", "content": system_prompt}]
        for prior_question, prior_answer in history or []:
            messages.append({"role": "user", "content": prior_question})
            messages.append({"role": "assistant", "content": prior_answer})
        messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"})
        payload = {"model": self.model, "messages": messages, "provider": PROVIDER_PREFERENCE}
        if temperature is not None:
            payload["temperature"] = temperature

        async def _call():
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
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
