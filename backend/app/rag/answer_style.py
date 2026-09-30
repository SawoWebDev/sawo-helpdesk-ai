"""Removes the "talking about its own sources" phrasing small models add to
answers: "Based on the context, ...", "Possible causes and fixes from the
knowledge base:", "..., as listed in the documentation, ...".

SYSTEM_PROMPT asks the model not to write these, but the cheap models this app
runs on don't reliably obey style instructions (they didn't for the strict
grounding rules either — see pipeline._is_grounded), so the same cleanup is
applied to the text afterwards. It only ever deletes phrasing that refers to
the source material; every fact in the answer is left exactly as generated.
"""

import re

_SOURCE_NOUN = (
    r"(?:(?:provided|given|available|internal|above)\s+)*"
    r"(?:knowledge[- ]base|documentation|documented (?:information|content)|context|information|excerpts?|kb)"
)

# "Based on the context, ..." / "According to the internal knowledge base: ..."
_LEADING_SOURCE_RE = re.compile(
    rf"^\s*(?:based on|according to|from|per|as per)\s+(?:the\s+)?{_SOURCE_NOUN}\b[^,:\n]*[,:]\s*",
    re.I,
)

# Whole lines that only introduce the list that follows.
_INTRO_LINE_RES = (
    re.compile(r"^\s*(?:here(?:'s| is| are)\s+)?(?:the\s+)?(?:possible\s+)?causes?\s+and\s+(?:fixes|solutions?)\b[^\n]*:\s*$", re.I),
    re.compile(
        rf"^\s*(?:possible\s+)?(?:troubleshooting steps|causes|fixes|solutions?)\b[^\n]{{0,40}}\b(?:from|in)\s+the\s+[^\n]{{0,30}}{_SOURCE_NOUN}\b[^\n]*:\s*$",
        re.I,
    ),
    re.compile(rf"^\s*(?:here(?:'s| is| are)|the following)\b[^\n]{{0,80}}\b{_SOURCE_NOUN}\b[^\n]{{0,40}}:\s*$", re.I),
)

# "..., as listed in the knowledge base, ..." and "(from the knowledge base)"
_INLINE_SOURCE_RES = (
    re.compile(rf",?\s*\b(?:as|which is|that is)?\s*(?:listed|documented|described|stated|found|given|provided|mentioned)\s+in\s+the\s+{_SOURCE_NOUN}\b,?", re.I),
    re.compile(rf"\s*\((?:from|in|per|based on)\s+the\s+{_SOURCE_NOUN}\)", re.I),
)


def strip_source_talk(text: str) -> str:
    original = text
    text = text.strip()

    stripped_prefix = False
    while True:
        new = _LEADING_SOURCE_RE.sub("", text, count=1)
        if new == text:
            break
        text, stripped_prefix = new, True

    lines = [line for line in text.split("\n") if not any(r.match(line) for r in _INTRO_LINE_RES)]
    text = "\n".join(lines)

    for pattern in _INLINE_SOURCE_RES:
        text = pattern.sub("", text)

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if stripped_prefix and text:
        text = text[0].upper() + text[1:]
    # Never turn a real answer into nothing: if cleanup consumed everything, keep the original.
    return text or original.strip()
