"""Canonical text form of a question, for exact-repeat lookups.

Only removes differences that can never change what is being asked: letter
case, Unicode look-alikes, quote marks and apostrophes ("won't" == "wont"),
runs of whitespace, and punctuation at the very start/end ("E1??" == "E1").
Everything inside the question — dashes, digits, "- - - -", "L L P L N",
units — is kept, so two questions that differ technically never normalize to
the same text.

Stored in faq_entries.question_normalized (kept in sync by an ORM hook in
models/faq.py) so the exact-repeat check is an indexed equality lookup.
"""

import re
import unicodedata

_QUOTES_RE = re.compile(r"[\"'`‘’‚‛“”„´]")
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"})
_EDGE_PUNCT = " \t\n?!.,;:"


def normalize_question(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.translate(_DASHES)
    s = _QUOTES_RE.sub("", s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(_EDGE_PUNCT)
    return s
