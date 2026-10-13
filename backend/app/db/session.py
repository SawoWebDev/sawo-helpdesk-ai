from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """For work that outlives the request handler, such as a streamed
    response body: on this FastAPI version, get_db's session is closed
    before a StreamingResponse starts sending, so that work opens its own."""
    return AsyncSessionLocal
