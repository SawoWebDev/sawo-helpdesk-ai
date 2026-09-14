import httpx

from app.ai.base import AIEngine, AIEngineError

TIMEOUT = httpx.Timeout(120.0, connect=10.0)
EMBED_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_query}"},
        ]
        try:
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
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            raise AIEngineError(f"OpenRouter request failed: {exc}") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise AIEngineError(f"OpenRouter response malformed: {exc}") from exc
