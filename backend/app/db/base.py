import sqlite_vec
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)


async def _setup_connection(raw_connection) -> None:
    """Runs against aiosqlite's real async connection (not the sync-style
    DBAPI wrapper SQLAlchemy normally hands to a "connect" listener — aiosqlite
    only exposes enable_load_extension/load_extension as coroutines)."""
    await raw_connection.enable_load_extension(True)
    await raw_connection.load_extension(sqlite_vec.loadable_path())
    await raw_connection.enable_load_extension(False)
    await raw_connection.execute("PRAGMA foreign_keys = ON")


@event.listens_for(engine.sync_engine, "connect")
def _load_sqlite_vec(dbapi_connection, connection_record) -> None:
    dbapi_connection.run_async(_setup_connection)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
