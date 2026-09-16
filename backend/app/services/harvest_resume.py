"""Re-queues Library sources left "pending" or "processing" from before a
restart. There's no separate worker/queue in this deployment (see
library_ingest.py) — a crawl or upload is driven entirely by FastAPI
BackgroundTasks tied to the request that queued it, which live only in that
process's memory. If the backend restarts mid-batch (a container rebuild,
a crash), every source still waiting its turn would otherwise stay stuck at
"pending" forever, with nothing left to ever pick it back up.

Runs on every boot; a no-op once nothing is left unfinished. Processes
sources with the same bounded concurrency as a fresh batch crawl (see
process_sources_concurrently), not one strictly sequential chain."""

import asyncio
import logging

from sqlalchemy import select

from app.crud.vault import delete_vault_entry
from app.db.base import AsyncSessionLocal
from app.models.harvest_source import HarvestSource
from app.models.vault_entry import VaultEntry
from app.services.library_ingest import process_sources_concurrently

logger = logging.getLogger(__name__)


async def _clear_partial_vault_entries(source_id: int) -> None:
    """A "processing" source may have committed some VaultEntry chunks before
    getting interrupted (each chunk is its own commit — see
    library_ingest._ingest_text). Clear them before reprocessing from scratch
    so restarting doesn't leave duplicates."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(VaultEntry).where(VaultEntry.source_id == source_id))
        for entry in result.scalars().all():
            await delete_vault_entry(db, entry)


async def resume_pending_sources() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(HarvestSource).where(HarvestSource.status.in_(["pending", "processing"]))
        )
        sources = list(result.scalars().all())

    if not sources:
        return

    logger.info("Resuming %d unfinished Library source(s) from before restart", len(sources))
    # Cleanup for interrupted-mid-flight sources happens up front, sequentially
    # (cheap DB-only work) — the actual re-fetch/re-embed work is then handed
    # to the same bounded-concurrency runner a fresh batch crawl uses.
    for source in sources:
        if source.status == "processing":
            try:
                await _clear_partial_vault_entries(source.id)
            except Exception:
                logger.exception("Failed to clear partial chunks for Library source %d", source.id)

    await process_sources_concurrently([(s.id, s.source_type) for s in sources])


def schedule_resume_pending_sources() -> None:
    """Fire-and-forget from the app's startup event — resuming a huge batch
    can take a very long time, so this must not block the app from becoming
    ready to serve requests."""
    asyncio.create_task(resume_pending_sources())
