import re

# Common greetings, pleasantries, and filler words that are never real support
# questions. Checked verbatim (after normalizing) before doing any embedding /
# vector search, since with a small knowledge base these can score similarly
# to genuine-but-vague questions on pure similarity alone.
FILLER_PHRASES = {
    "hi",
    "hello",
    "hey",
    "hey there",
    "yo",
    "sup",
    "howdy",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "how are you doing",
    "how's it going",
    "what's up",
    "test",
    "testing",
    "ping",
    "thanks",
    "thank you",
    "thx",
    "ty",
    "ok",
    "okay",
    "k",
    "yes",
    "no",
    "yep",
    "nope",
    "bye",
    "goodbye",
    "see ya",
    "cya",
    "nice",
    "cool",
    "great",
    "lol",
    "haha",
}

_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]")


def is_filler(text: str) -> bool:
    normalized = _NORMALIZE_RE.sub("", text.strip().lower()).strip()
    if not normalized:
        return True
    if normalized in FILLER_PHRASES:
        return True
    # A single short word (<=4 chars) that isn't itself a real question is very
    # unlikely to be a genuine support query (e.g. "test", "meh", "abc").
    if " " not in normalized and len(normalized) <= 4:
        return True
    return False
