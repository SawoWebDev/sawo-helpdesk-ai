import httpx

from app.ai.base import AIEngine, AIEngineError
from app.ai.ollama_engine import OllamaEngine

TIMEOUT = httpx.Timeout(120.0, connect=10.0)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterEngine(AIEngine):
    name = "openrouter"

    def __init__(self, api_key: str, model: str, ollama_engine: OllamaEngine):
        self.api_key = api_key
        self.model = model
        # Embeddings always go through Ollama per spec, to keep vector dimensions consistent.
        self._embedding_engine = ollama_engine

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embedding_engine.embed(texts)

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
                    OPENROUTER_URL,
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
