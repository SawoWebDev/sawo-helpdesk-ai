import asyncio
import logging

from app.core.config import settings
from app.crud.settings import seed_default_settings
from app.crud.user import get_user_by_username
from app.db.base import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password

logger = logging.getLogger(__name__)


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        await seed_default_settings(db)

        existing_admin = await get_user_by_username(db, settings.initial_admin_username)
        if existing_admin is None:
            admin = User(
                username=settings.initial_admin_username,
                email=settings.initial_admin_email,
                password_hash=hash_password(settings.initial_admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            logger.info("Created initial admin user '%s'", settings.initial_admin_username)
        else:
            logger.info("Initial admin user already exists, skipping seed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
