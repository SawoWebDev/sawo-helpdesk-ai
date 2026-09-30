"""Re-embed FAQ/vault entries whose `has_embedding` flag is False — e.g. right
after a migration that changed the embedding provider/dimension (old vectors
in the sqlite-vec tables get dropped since they can't be reinterpreted at a
new width). Safe to run on every boot: a no-op once nothing is stale."""

import asyncio
import logging

from sqlalchemy import exists, select

from app.ai.base import AIEngineError
from app.db.base import AsyncSessionLocal
from app.models.faq import FAQEntry
from app.models.vault_entry import VaultEntry
from app.rag.reindex import has_stale_faq_vectors, reindex_stale_faq
from app.rag.vault_reindex import reindex_stale_vault

logger = logging.getLogger(__name__)


async def reindex_stale() -> None:
    async with AsyncSessionLocal() as db:
        # Includes FAQs embedded before question-only vectors existed, and
        # phrasings whose embedding failed when they were added.
        has_stale_faq = await has_stale_faq_vectors(db)
        has_stale_vault = (
            await db.execute(
                select(
                    exists().where(
                        VaultEntry.has_embedding.is_(False), VaultEntry.memory_enabled.is_(True)
                    )
                )
            )
        ).scalar()

        if not has_stale_faq and not has_stale_vault:
            return

        try:
            if has_stale_faq:
                count = await reindex_stale_faq(db)
                logger.info("Re-embedded %d FAQ entries", count)
            if has_stale_vault:
                count = await reindex_stale_vault(db)
                logger.info("Re-embedded %d vault entries", count)
        except AIEngineError as exc:
            logger.warning("Stale-embedding reindex failed, will retry next boot: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(reindex_stale())
