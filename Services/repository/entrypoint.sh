#!/bin/bash
set -e

echo "[ForgeAI Repository] Running Alembic migrations..."
alembic upgrade head

echo "[ForgeAI Repository] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8001
