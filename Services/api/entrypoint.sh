#!/bin/bash
set -e

echo "[ForgeAI API] Running Alembic migrations..."
alembic upgrade head

echo "[ForgeAI API] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
