from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AIEngineError(Exception):
    """Raised when the configured AI engine cannot be reached or fails."""


class AIEngine(ABC):
    name: str

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        context: str,
        user_query: str,
        temperature: float | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        """Generate a grounded answer from the given context. Pass
        temperature=0 for classification-style calls (yes/no, pick-a-number)
        where a consistent judgment matters more than varied phrasing. Pass
        history as (question, answer) pairs, oldest first, to give the model
        real prior conversation turns — kept separate from `context` (the
        knowledge-base excerpts the grounding check validates against) so
        earlier dialogue never gets treated as something that needs to trace
        back to the KB."""

    async def generate_stream(
        self,
        system_prompt: str,
        context: str,
        user_query: str,
        temperature: float | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Same as generate(), but yields the reply in pieces as they arrive.
        Joined, the pieces equal what generate() would return (before its
        final .strip()). Engines without native streaming yield it whole."""
        yield await self.generate(system_prompt, context, user_query, temperature=temperature, history=history)
