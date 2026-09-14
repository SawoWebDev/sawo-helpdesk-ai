#!/bin/sh
set -e

echo "Running migrations..."
alembic upgrade head

echo "Seeding initial admin and settings..."
python -m app.seed

echo "Re-embedding any entries missing an embedding..."
python -m app.reindex_stale

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
