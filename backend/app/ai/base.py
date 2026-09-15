from abc import ABC, abstractmethod


class AIEngineError(Exception):
    """Raised when the configured AI engine cannot be reached or fails."""


class AIEngine(ABC):
    name: str

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    async def generate(
        self, system_prompt: str, context: str, user_query: str, temperature: float | None = None
    ) -> str:
        """Generate a grounded answer from the given context. Pass
        temperature=0 for classification-style calls (yes/no, pick-a-number)
        where a consistent judgment matters more than varied phrasing."""
