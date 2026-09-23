"""Promotes a Library-grounded chat answer into a draft FAQ entry as a
FastAPI background task, run after the HTTP response is sent — same
convention as library_ingest.py. Kept off the request path because the
duplicate check embeds up to a handful of candidate questions and the
draft's own embed_entry call needs another embeddings round-trip, none of
which gives the asker anything.

Saved as a draft, not published: FAQ content normally skips the RAG
grounding check on the assumption it's admin-curated (see
rag/pipeline.py::_is_grounded), which no longer holds for content the LLM
wrote about itself. An admin reviewing and publishing from the FAQ admin UI
is what re-establishes that trust."""

import logging

from app.ai.base import AIEngineError
from app.crud.faq import create_faq, find_duplicate_faq
from app.db.session import AsyncSessionLocal
from app.rag.reindex import embed_entry

logger = logging.getLogger(__name__)


async def promote_answer_to_draft(
    question: str,
    answer: str,
    image_urls: list[str],
    reference_urls: list[str],
    source_id: int | None,
    query_vector: list[float],
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            # include_drafts=True: without it, the same question asked
            # repeatedly before anyone reviews the queue would create a new
            # draft every time.
            duplicate = await find_duplicate_faq(db, question, query_vector, include_drafts=True)
            if duplicate is not None:
                return
            faq_entry = await create_faq(
                db,
                question=question,
                answer=answer,
                category_id=None,
                image_urls=image_urls,
                reference_urls=reference_urls,
                source="chat_auto",
                source_label="Auto-saved from chat",
                source_id=source_id,
                status="draft",
            )
            await embed_entry(db, faq_entry)
            await db.commit()
        except AIEngineError:
            logger.warning("Failed to promote chat answer to draft FAQ", exc_info=True)
