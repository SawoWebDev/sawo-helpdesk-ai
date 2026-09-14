import httpx

from app.ai.base import AIEngine, AIEngineError

TIMEOUT = httpx.Timeout(120.0, connect=10.0)
EMBED_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Backup free models tried, in order, if the configured OPENROUTER_MODEL
# itself fails (rate-limited, discontinued, temporarily down) and is itself
# a free model. Free-tier availability shifts over time — this list only
# needs to stay roughly current, not perfect, since it's a safety net on
# top of the admin-configured model, not the primary choice. Verify a
# candidate is real before adding it (GET /api/v1/models), since OpenRouter
# doesn't error clearly on a stale/renamed :free id — expect a 404.
FREE_MODEL_FALLBACKS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]


class OpenRouterEngine(AIEngine):
    name = "openrouter"

    def __init__(self, api_key: str, model: str, embedding_model: str):
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")
        try:
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
                data = resp.json()
                ordered = sorted(data["data"], key=lambda item: item["index"])
                return [item["embedding"] for item in ordered]
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter embedding request failed: {exc}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter embedding response malformed: {exc}") from exc

    async def generate(self, system_prompt: str, context: str, user_query: str) -> str:
        if not self.api_key:
            raise AIEngineError("OpenRouter API key is not configured.")

        # If the configured model is itself free, fall through a short list of
        # other verified-working free models on failure — free-tier requests
        # get rate-limited or a specific free model can go away, and this
        # keeps the assistant answering instead of only ever hitting the
        # canned fallback message. A paid model is never silently swapped out
        # from under the admin's choice.
        models_to_try = [self.model]
        if self.model.endswith(":free"):
            models_to_try += [m for m in FREE_MODEL_FALLBACKS if m != self.model]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"},
        ]

        last_error: Exception | None = None
        for model in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={"model": model, "messages": messages},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
            except httpx.HTTPError as exc:
                last_error = exc
                continue
            except (KeyError, IndexError, ValueError) as exc:
                last_error = exc
                continue

        raise AIEngineError(f"OpenRouter request failed for all candidate models: {last_error}")
