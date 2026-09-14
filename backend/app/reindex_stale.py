"""Re-embed FAQ/vault entries left with a null embedding — e.g. right after a
migration that resized the vector column (old vectors can't be reinterpreted
at a new dimension, so they're nulled out instead). Safe to run on every
boot: a no-op once nothing has a null embedding."""

import asyncio
import logging

from sqlalchemy import exists, select

from app.ai.base import AIEngineError
from app.db.base import AsyncSessionLocal
from app.models.faq import FAQEntry
from app.models.vault_entry import VaultEntry
from app.rag.reindex import reindex_all
from app.rag.vault_reindex import reindex_all_vault

logger = logging.getLogger(__name__)


async def reindex_stale() -> None:
    async with AsyncSessionLocal() as db:
        has_stale_faq = (
            await db.execute(select(exists().where(FAQEntry.embedding.is_(None))))
        ).scalar()
        has_stale_vault = (
            await db.execute(
                select(
                    exists().where(
                        VaultEntry.embedding.is_(None), VaultEntry.memory_enabled.is_(True)
                    )
                )
            )
        ).scalar()

        if not has_stale_faq and not has_stale_vault:
            return

        try:
            if has_stale_faq:
                count = await reindex_all(db)
                logger.info("Re-embedded %d FAQ entries", count)
            if has_stale_vault:
                count = await reindex_all_vault(db)
                logger.info("Re-embedded %d vault entries", count)
        except AIEngineError as exc:
            logger.warning("Stale-embedding reindex failed, will retry next boot: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(reindex_stale())
