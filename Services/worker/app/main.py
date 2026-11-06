"""
main.py — Worker Service entry point.

This is a long-running async process (NOT a FastAPI/HTTP server).
It starts a Kafka consumer and dispatches events to the correct handlers.

Lifecycle:
  startup  → create DB tables, ensure Qdrant collection exists, start Kafka consumer
  running  → consume events in a loop, dispatch by event type
  shutdown → drain in-flight work, close connections cleanly

To run locally:
    python -m app.main
"""

import asyncio
import logging
import signal
import sys

from app.core.config import settings
from app.core.logging import setup_logging

# ── Logging must be set up FIRST before any other imports ─────────────────────
setup_logging()
logger = logging.getLogger(__name__)


async def _startup() -> None:
    """
    One-time startup tasks before the consumer begins processing.
    """
    # 1. Create worker-owned DB tables (repository_files, repository_knowledge)
    #    The mirror tables (repositories, repository_syncs, github_installations)
    #    are owned by the repository service — we do NOT create those here.
    logger.info("Creating worker-owned database tables...")
    from app.db.base import Base
    from app.db.database import engine
    import app.models  # noqa: F401 — registers all models with Base.metadata

    worker_table_names = [
        "repository_files",
        "repository_knowledge",
        "code_symbols",
        "code_relationships",
    ]
    worker_tables = [
        Base.metadata.tables[name]
        for name in worker_table_names
        if name in Base.metadata.tables
    ]

    Base.metadata.create_all(bind=engine, tables=worker_tables)
    logger.info(
        "Database tables ready",
        extra={"tables": worker_table_names},
    )

    # 1b. Add full-text search support to code_symbols (PostgreSQL only).
    #     Idempotent — safe to run every startup.
    _setup_symbol_fts(engine)

    # 2. Ensure Qdrant collection exists
    await _startup_qdrant()


def _setup_symbol_fts(engine) -> None:
    """
    Adds a tsvector search_vector column + update trigger to code_symbols.

    The trigger automatically recomputes the tsvector whenever a row is
    inserted or updated, using:
      - symbol_name   (weight A — highest priority)
      - qualified_name (weight B)
      - signature      (weight C)
      - docstring      (weight D)

    Only runs for PostgreSQL. Silently skips for SQLite (used in tests).
    """
    from sqlalchemy import text, inspect
    from app.db.database import get_db_session

    dialect = engine.dialect.name
    if dialect != "postgresql":
        logger.debug("Skipping FTS setup — not PostgreSQL", extra={"dialect": dialect})
        return

    logger.info("Setting up full-text search for code_symbols...")
    with get_db_session() as db:
        # Add column if missing
        db.execute(text("""
            ALTER TABLE code_symbols
            ADD COLUMN IF NOT EXISTS search_vector tsvector
        """))

        # Create GIN index for fast FTS queries (IF NOT EXISTS requires PG 9.5+)
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_syms_fts
            ON code_symbols
            USING GIN (search_vector)
        """))

        # Create the trigger function
        db.execute(text("""
            CREATE OR REPLACE FUNCTION code_symbols_fts_update()
            RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', coalesce(NEW.symbol_name, '')), 'A')
                    || setweight(to_tsvector('english', coalesce(NEW.qualified_name, '')), 'B')
                    || setweight(to_tsvector('english', coalesce(NEW.signature, '')), 'C')
                    || setweight(to_tsvector('english', coalesce(NEW.docstring, '')), 'D');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))

        # Create the trigger (DROP and recreate — idempotent)
        db.execute(text("""
            DROP TRIGGER IF EXISTS trg_code_symbols_fts
            ON code_symbols
        """))
        db.execute(text("""
            CREATE TRIGGER trg_code_symbols_fts
            BEFORE INSERT OR UPDATE ON code_symbols
            FOR EACH ROW EXECUTE FUNCTION code_symbols_fts_update()
        """))

        # Backfill existing rows
        db.execute(text("""
            UPDATE code_symbols SET search_vector =
                setweight(to_tsvector('english', coalesce(symbol_name, '')), 'A')
                || setweight(to_tsvector('english', coalesce(qualified_name, '')), 'B')
                || setweight(to_tsvector('english', coalesce(signature, '')), 'C')
                || setweight(to_tsvector('english', coalesce(docstring, '')), 'D')
            WHERE search_vector IS NULL
        """))

        db.commit()
    logger.info("Full-text search setup complete for code_symbols")


async def _startup_qdrant() -> None:
    """Ensure Qdrant collection exists."""
    logger.info("Ensuring Qdrant collection exists...")
    from app.services import vector_store
    vector_store.ensure_collection_exists()
    logger.info("Qdrant ready", extra={"collection": settings.QDRANT_COLLECTION_NAME})


async def _shutdown(consumer) -> None:
    """Gracefully stop the consumer on SIGINT / SIGTERM."""
    logger.info("Worker shutdown signal received — stopping consumer...")
    await consumer.stop()


async def main() -> None:
    logger.info(
        "ForgeAI Worker Service starting",
        extra={"version": "0.1.0"},
    )

    # Run startup tasks
    await _startup()

    # Start Kafka consumer
    from app.consumer.kafka_consumer import WorkerConsumer
    consumer = WorkerConsumer()
    await consumer.start()

    loop = asyncio.get_running_loop()

    # Register OS signal handlers for clean shutdown.
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(_shutdown(consumer)),
        )

    logger.info("Worker consumer running — waiting for events...")
    await consumer.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by KeyboardInterrupt")
        sys.exit(0)
