"""End-to-end Library ingestion for one HarvestSource: extract text, chunk
it, and store each chunk as a memory-enabled VaultEntry (embedded immediately
so it's searchable via RAG right away). Runs as a FastAPI background task —
there's no separate worker process in this deployment, so each source is
processed in-process after the HTTP response for the upload/crawl request is
sent.

Library content is searched live by RAG, not pre-digested into FAQ entries —
FAQ is a separate, admin-curated Q&A source."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.crud.vault import create_vault_entry
from app.db.session import AsyncSessionLocal
from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.models.harvest_source import HarvestSource
from app.services.chunking import chunk_text
from app.services.library_parsers import (
    ParseError,
    extract_html_text,
    extract_text_for_file,
    fetch_url,
)

logger = logging.getLogger(__name__)

# How many sources process at once instead of one strictly sequential chain.
# Each one is still its own independent fetch + embed + DB-write cycle (own
# AsyncSessionLocal — see process_url_source/process_file_source), so this is
# safe to run concurrently; it's capped rather than unbounded so a huge batch
# doesn't hammer the crawled site or the embedding API with thousands of
# simultaneous requests.
DEFAULT_CRAWL_CONCURRENCY = 5


async def _mark_failed(db: AsyncSession, source: HarvestSource, message: str) -> None:
    source.status = "failed"
    source.error_message = message[:2000]
    source.processed_at = datetime.now(timezone.utc)
    await db.commit()


async def process_file_source(source_id: int) -> None:
    async with AsyncSessionLocal() as db:
        source = await db.get(HarvestSource, source_id)
        if source is None:
            return
        source.status = "processing"
        await db.commit()

        try:
            with open(source.file_path, "rb") as f:
                data = f.read()
            # PDF/DOCX/XLSX parsing is synchronous CPU work — run it off the
            # event loop so it can't stall other requests (chat included)
            # while a large batch is being ingested. Same reasoning as the
            # HTML extraction in process_url_source below.
            text = await asyncio.to_thread(extract_text_for_file, source.original_filename or "", data)
        except (ParseError, OSError) as exc:
            await _mark_failed(db, source, str(exc))
            return

        await _ingest_text(db, source, text, title_prefix=source.original_filename or "Document")


async def process_url_source(source_id: int) -> None:
    """Fetches and indexes exactly the one URL on the source — no link
    following. Simpler and more predictable than crawling multiple hops:
    the admin picks exactly which pages go into the Library by giving each
    one its own URL, rather than the crawler guessing which linked pages are
    relevant."""
    async with AsyncSessionLocal() as db:
        source = await db.get(HarvestSource, source_id)
        if source is None:
            return
        source.status = "processing"
        await db.commit()

        try:
            html, final_url = await fetch_url(source.origin_url)
        except ParseError as exc:
            await _mark_failed(db, source, str(exc))
            return

        # BeautifulSoup/lxml parsing is synchronous CPU work. Run it in a
        # worker thread rather than inline: this function runs sequentially,
        # one page at a time, for potentially tens of thousands of pages in a
        # batch, and every millisecond spent parsing HTML inline blocks the
        # single event loop this process shares with live chat requests —
        # which is what was making chat intermittently time out while a big
        # crawl was in progress.
        text = await asyncio.to_thread(extract_html_text, html)
        await _ingest_text(db, source, text, title_prefix=final_url or source.origin_url or "Web page")


async def _ingest_text(db: AsyncSession, source: HarvestSource, text: str, title_prefix: str) -> None:
    text = text.strip()
    source.extracted_char_count = len(text)

    if not text:
        await _mark_failed(db, source, "No extractable text content was found in this source.")
        return

    chunks = chunk_text(text)
    if not chunks:
        await _mark_failed(db, source, "Content was too short to chunk.")
        return

    try:
        embedding_engine = await get_embedding_engine(db)
        vectors = await embedding_engine.embed([c.text for c in chunks])
    except AIEngineError as exc:
        await _mark_failed(db, source, f"Embedding failed: {exc}")
        return

    entries = []
    for chunk, vector in zip(chunks, vectors):
        title = f"{title_prefix} (part {chunk.index + 1}/{len(chunks)})" if len(chunks) > 1 else title_prefix
        entry = await create_vault_entry(
            db,
            title=title[:500],
            content=chunk.text,
            category_id=source.category_id,
            tags=[],
            source_type="library",
            source_id=source.id,
            source_url=source.origin_url,
        )
        entry.memory_enabled = True
        await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector)
        entry.has_embedding = True
        entries.append(entry)

    source.chunk_count = len(entries)
    source.status = "indexed"
    source.processed_at = datetime.now(timezone.utc)
    await db.commit()


async def process_sources_concurrently(
    sources: list[tuple[int, str]], concurrency: int = DEFAULT_CRAWL_CONCURRENCY
) -> None:
    """Processes many sources at once, bounded by `concurrency` workers
    running in parallel — a batch can be tens of thousands of pages, and
    running them one strictly-sequential chain (the previous behavior) would
    take an impractically long time to finish. `sources` is a list of
    (source_id, source_type) pairs. One failing/erroring source never stops
    the rest — each is isolated and logged independently, same as the
    per-source failure handling process_url_source/process_file_source
    already do internally."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(source_id: int, source_type: str) -> None:
        async with semaphore:
            try:
                if source_type == "file":
                    await process_file_source(source_id)
                else:
                    await process_url_source(source_id)
            except Exception:
                logger.exception("Failed to process Library source %d", source_id)

    await asyncio.gather(*(_run_one(source_id, source_type) for source_id, source_type in sources))
