import re

MAX_TITLE_LENGTH = 80


def make_conversation_title(question: str) -> str:
    """Deterministic conversation title from a staff member's first question.
    No LLM call — just whitespace/markdown cleanup and a length cap, since a
    title only needs to be recognizable in a sidebar list, not polished."""
    text = re.sub(r"\s+", " ", question).strip()
    text = text.strip("*_`#> ")
    if len(text) > MAX_TITLE_LENGTH:
        text = text[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
    return text or "New conversation"
