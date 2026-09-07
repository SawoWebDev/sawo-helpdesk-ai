#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def wait():
    for _ in range(30):
        try:
            engine = create_async_engine(settings.database_url)
            async with engine.connect() as conn:
                pass
            await engine.dispose()
            return
        except Exception:
            time.sleep(2)
    sys.exit('Database not reachable')

asyncio.run(wait())
"

echo "Running migrations..."
alembic upgrade head

echo "Seeding initial admin and settings..."
python -m app.seed

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
