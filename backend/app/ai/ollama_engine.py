import httpx

from app.ai.base import AIEngine, AIEngineError

EMBED_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
# Generation on CPU-only Ollama hosts can take well over a minute per request.
GENERATE_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class OllamaEngine(AIEngine):
    name = "ollama"

    def __init__(self, base_url: str, embedding_model: str, generation_model: str):
        self.base_url = base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.generation_model = generation_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                for text in texts:
                    resp = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.embedding_model, "prompt": text},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    vectors.append(data["embedding"])
        except httpx.HTTPError as exc:
            raise AIEngineError(f"Ollama embedding request failed: {exc}") from exc
        except (KeyError, ValueError) as exc:
            raise AIEngineError(f"Ollama embedding response malformed: {exc}") from exc
        return vectors

    async def generate(self, system_prompt: str, context: str, user_query: str) -> str:
        prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {user_query}\nAnswer:"
        try:
            async with httpx.AsyncClient(timeout=GENERATE_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.generation_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "").strip()
        except httpx.HTTPError as exc:
            raise AIEngineError(f"Ollama generation request failed: {exc}") from exc
        except ValueError as exc:
            raise AIEngineError(f"Ollama generation response malformed: {exc}") from exc
