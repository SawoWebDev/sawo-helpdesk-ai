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

# Unicode-aware on purpose: an ASCII-only class erased every Chinese, Cyrillic,
# etc. character, so any question in those scripts collapsed to "" or a short
# leftover like "sawo" and was answered as small talk, never retrieved for.
_NORMALIZE_RE = re.compile(r"[^\w\s]")


def is_filler(text: str) -> bool:
    normalized = _NORMALIZE_RE.sub("", text.strip().lower()).strip()
    if not normalized:
        return True
    if normalized in FILLER_PHRASES:
        return True
    # A single short word (<=4 chars) that isn't itself a real question is very
    # unlikely to be a genuine support query (e.g. "test", "meh", "abc").
    # Latin letters only: one Chinese character is a whole word, so "保修期"
    # (warranty period) is a complete question. Non-Latin small talk goes on
    # to the relevance check like any other message.
    if " " not in normalized and len(normalized) <= 4 and normalized.isascii():
        return True
    return False
