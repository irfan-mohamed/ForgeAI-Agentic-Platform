#!/bin/bash
set -e

echo "[ForgeAI AI] Running Alembic migrations..."
alembic upgrade head

echo "[ForgeAI AI] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8002
