"""Which language an answer must be written in, and whether it was.

No prompt said anything about language, so the answer's language was left to
the model. The configured chat model (deepseek-v4-flash) was trained heavily
on Chinese, and with nothing anchoring it an English warranty question came
back in Chinese — including, when it had nothing to say, a Chinese "sorry,
not found" in place of the NOT_FOUND sentinel. That reply is neither the
sentinel nor checked by the fact-check (skipped for Library contexts), so it
reached the user as-is.

The rule, applied to every generated reply:
  * answer in the language the user explicitly asked for, if they did;
  * otherwise in the language of the question — never of the retrieved
    excerpts or of earlier turns;
  * product names, model numbers, error codes and measurements are copied, not
    translated.
The language is established from the question text itself (script, plus
English function words for Latin-script text), so no extra AI call is made.
A generated reply in the wrong writing system is rejected afterwards
(answer_matches), because the prompt alone is exactly what failed.
"""

import re
from dataclasses import dataclass

# Unicode letter ranges per writing system. Only the scripts a reply could
# plausibly drift into need to be here; anything unlisted counts as neither.
_SCRIPT_RANGES = {
    "latin": ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F)),
    "han": ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)),
    "kana": ((0x3040, 0x30FF),),
    "hangul": ((0x1100, 0x11FF), (0xAC00, 0xD7AF)),
    "cyrillic": ((0x400, 0x4FF),),
    "greek": ((0x370, 0x3FF),),
    "arabic": ((0x600, 0x6FF),),
    "hebrew": ((0x590, 0x5FF),),
    "thai": ((0xE00, 0xE7F),),
}

# Script a question is written in -> the language to name in the prompt, when
# the script alone settles it (Cyrillic, Arabic, ... do not, and are left as
# "the language of the question").
_SCRIPT_LANGUAGE = {"han": "Chinese", "kana": "Japanese", "hangul": "Korean", "greek": "Greek", "thai": "Thai", "hebrew": "Hebrew"}

# Languages a user can ask for by name -> (prompt name, script).
_NAMED_LANGUAGES = {
    "english": ("English", "latin"),
    "chinese": ("Chinese", "han"),
    "mandarin": ("Chinese", "han"),
    "finnish": ("Finnish", "latin"),
    "swedish": ("Swedish", "latin"),
    "german": ("German", "latin"),
    "french": ("French", "latin"),
    "spanish": ("Spanish", "latin"),
    "italian": ("Italian", "latin"),
    "dutch": ("Dutch", "latin"),
    "estonian": ("Estonian", "latin"),
    "polish": ("Polish", "latin"),
    "portuguese": ("Portuguese", "latin"),
    "russian": ("Russian", "cyrillic"),
    "japanese": ("Japanese", "kana"),
    "korean": ("Korean", "hangul"),
}
_LANG_ALT = "|".join(_NAMED_LANGUAGES)

# "answer in Chinese", "please reply in simplified Chinese", "translate it into
# Finnish", "in German please". A bare "in Finnish" is not enough — "what is
# it called in Finnish?" asks for a word, and "tell me if the manual is
# available in Chinese" asks about a manual — so only a few filler words may
# sit between the verb and the language.
_REQUEST_FILLER = r"(?:\s+(?:it|this|that|me|us|them|back|everything|all|the answer|your answer|the reply|your reply))*"
_REQUEST_RES = (
    re.compile(
        rf"\b(?:answer|reply|respond|write|explain|translate|say|tell me|describe)\b{_REQUEST_FILLER}"
        rf"\s+(?:in|into)\s+(?:simplified\s+|traditional\s+)?({_LANG_ALT})\b",
        re.I,
    ),
    re.compile(rf"\b(?:in|into)\s+(?:simplified\s+|traditional\s+)?({_LANG_ALT})\s*,?\s*(?:please|pls)\b", re.I),
    re.compile(rf"\b(?:please|pls)\s*,?\s*(?:in|into)\s+(?:simplified\s+|traditional\s+)?({_LANG_ALT})\b", re.I),
)
# Requests written in the language itself.
_NATIVE_REQUESTS = (
    (re.compile(r"用中文|中文回答|中文回复|请用中文"), ("Chinese", "han")),
    (re.compile(r"\bauf deutsch\b", re.I), ("German", "latin")),
    (re.compile(r"\bsuomeksi\b", re.I), ("Finnish", "latin")),
    (re.compile(r"\bpå svenska\b", re.I), ("Swedish", "latin")),
    (re.compile(r"\bin english\b", re.I), ("English", "latin")),
)

# Words that mark Latin-script text as English. Two distinct ones are
# required, and words other languages share ("in", "die", "a") are left out, so
# "wat is de garantie" or "Was ist die Garantie" is not taken for English.
_ENGLISH_WORDS = frozenset(
    "the what how why which does doesn't don't is isn't are aren't my can can't could should would "
    "when where who there this that these with and for of to it its won't not please you your "
    "have has we our any".split()
)
_WORD_RE = re.compile(r"[a-z']+")

# A reply is "in the wrong writing system" when this share of its letters is
# foreign to the expected one. Model codes and units are Latin inside any
# language, so a Chinese reply is still mostly Han, and an English reply
# quoting one foreign term stays well below it.
_FOREIGN_SHARE_LIMIT = 0.2


@dataclass(frozen=True)
class ResponseLanguage:
    name: str | None  # "English", "Chinese"; None = mirror the question
    script: str  # writing system the reply must be in
    explicit: bool = False  # the user asked for it

    def reply_rule(self) -> str:
        if self.name and self.explicit:
            target = f"in {self.name}, as the user asked"
        elif self.name:
            target = f"in {self.name}, the language of the user's message"
        else:
            target = "in the same language as the user's message"
        return f"Write your entire reply {target}."

    def instruction(self) -> str:
        """reply_rule plus the rules for answers written from context."""
        return (
            f"{self.reply_rule()} The context excerpts and earlier conversation turns may be "
            "in other languages; their language never decides the language of your reply, so translate "
            "whatever you use from them. Copy product names, model numbers, error and display codes, part "
            "designators, measurements and units exactly as written in the context; never translate or "
            "alter them. If you cannot answer, reply with the exact sentinel you were given, not with an "
            "apology in any language."
        )


def _script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        code = ord(char)
        for script, ranges in _SCRIPT_RANGES.items():
            if any(lo <= code <= hi for lo, hi in ranges):
                counts[script] = counts.get(script, 0) + 1
                break
    return counts


def _dominant_script(text: str) -> str:
    counts = _script_counts(text)
    # Model codes are Latin inside a question in any language, and one Han
    # character carries a whole word, so any real run of a non-Latin script
    # decides it.
    non_latin = {s: n for s, n in counts.items() if s != "latin"}
    if non_latin:
        script, n = max(non_latin.items(), key=lambda item: item[1])
        if n >= 2 or not counts.get("latin"):
            return "kana" if script == "han" and counts.get("kana") else script
    return "latin"


def detect(question: str) -> ResponseLanguage:
    for pattern in _REQUEST_RES:
        match = pattern.search(question)
        if match:
            name, script = _NAMED_LANGUAGES[match.group(1).lower()]
            return ResponseLanguage(name, script, explicit=True)
    for pattern, (name, script) in _NATIVE_REQUESTS:
        if pattern.search(question):
            return ResponseLanguage(name, script, explicit=True)

    script = _dominant_script(question)
    if script != "latin":
        return ResponseLanguage(_SCRIPT_LANGUAGE.get(script), script)
    words = set(_WORD_RE.findall(question.lower().replace("’", "'")))
    if len(words & _ENGLISH_WORDS) >= 2:
        return ResponseLanguage("English", "latin")
    return ResponseLanguage(None, "latin")


def answer_matches(answer: str, language: ResponseLanguage) -> bool:
    """False when the reply is written in a different writing system than the
    one required — e.g. Chinese for an English question. Same-script mixups
    (Finnish for English) can't be told apart this cheaply and are left to
    the prompt."""
    counts = _script_counts(answer)
    total = sum(counts.values())
    if not total:
        return True
    expected = counts.get(language.script, 0)
    if language.script == "kana":  # Japanese is written with Han and kana together
        expected += counts.get("han", 0)
    if language.script == "latin":
        return (total - expected) / total <= _FOREIGN_SHARE_LIMIT
    return expected / total >= _FOREIGN_SHARE_LIMIT
