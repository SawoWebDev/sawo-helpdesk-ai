"""Splits extracted document text into overlapping chunks for embedding.
Uses a word-count proxy for tokens (~0.75 words/token is the usual rule of
thumb inverted, i.e. ~1.3 tokens/word for English) rather than a real
tokenizer, since exact token boundaries don't matter for chunk quality here
and it avoids pulling in a model-specific tokenizer dependency."""

from dataclasses import dataclass

WORDS_PER_CHUNK = 650  # ~500-1000 tokens
OVERLAP_WORDS = 80


@dataclass
class Chunk:
    index: int
    text: str


def chunk_text(text: str, words_per_chunk: int = WORDS_PER_CHUNK, overlap_words: int = OVERLAP_WORDS) -> list[Chunk]:
    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    start = 0
    index = 0
    step = max(words_per_chunk - overlap_words, 1)
    while start < len(words):
        segment = words[start : start + words_per_chunk]
        chunk_str = " ".join(segment).strip()
        if chunk_str:
            chunks.append(Chunk(index=index, text=chunk_str))
            index += 1
        if start + words_per_chunk >= len(words):
            break
        start += step
    return chunks
