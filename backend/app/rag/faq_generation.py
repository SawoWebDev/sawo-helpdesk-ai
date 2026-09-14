"""Automated FAQ extraction: given a chunk of ingested Library text, asks the
configured AI engine to produce high-yield Question/Answer pairs grounded
only in that chunk, then parses the model's JSON response defensively (free
models occasionally wrap JSON in prose or code fences)."""

import json
import re

from app.ai.base import AIEngine, AIEngineError

FAQ_GENERATION_SYSTEM_PROMPT = (
    "You are an assistant that writes helpdesk FAQ entries from internal "
    "documentation. Read the provided document excerpt and extract clear, "
    "high-yield question-and-answer pairs a customer or employee might "
    "search for. Rules:\n"
    "- Only use facts stated in the excerpt. Do not invent information.\n"
    "- Each answer must be a direct, self-contained answer (don't say "
    "'as mentioned above').\n"
    "- Skip the excerpt entirely if it has no useful support/product content "
    "(e.g. it's a table of contents, legal boilerplate, or navigation text).\n"
    "- Produce at most 8 pairs.\n"
    "Respond with ONLY a JSON array, no prose, no markdown code fences, in "
    'exactly this shape: [{"question": "...", "answer": "..."}]. If there is '
    "nothing worth extracting, respond with exactly: []"
)

MAX_PAIRS_PER_CHUNK = 8
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


class FAQPair:
    __slots__ = ("question", "answer")

    def __init__(self, question: str, answer: str):
        self.question = question
        self.answer = answer


def _parse_pairs(raw: str) -> list[FAQPair]:
    candidate = raw.strip()
    match = _JSON_ARRAY_RE.search(candidate)
    if match:
        candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    pairs: list[FAQPair] = []
    for item in data[:MAX_PAIRS_PER_CHUNK]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if len(question) < 5 or len(answer) < 2:
            continue
        pairs.append(FAQPair(question=question, answer=answer))
    return pairs


async def generate_faqs_from_chunk(engine: AIEngine, chunk_text: str) -> list[FAQPair]:
    try:
        raw = await engine.generate(FAQ_GENERATION_SYSTEM_PROMPT, chunk_text, "Extract FAQ pairs.")
    except AIEngineError:
        return []
    return _parse_pairs(raw)
