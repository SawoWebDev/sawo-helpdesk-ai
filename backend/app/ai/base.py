from abc import ABC, abstractmethod


class AIEngineError(Exception):
    """Raised when the configured AI engine cannot be reached or fails."""


class AIEngine(ABC):
    name: str

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    async def generate(self, system_prompt: str, context: str, user_query: str) -> str:
        """Generate a grounded answer from the given context."""
