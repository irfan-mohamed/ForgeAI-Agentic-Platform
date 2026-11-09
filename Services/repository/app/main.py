import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.db.base import Base
from app.db.database import engine

# Import all models so SQLAlchemy registers them with Base.metadata
import app.models  # noqa: F401 — side-effect import

from app.api.routes import github, pull_requests, repositories, internal

# ── Logging ────────────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Startup: create DB tables owned by this service.
    Shutdown: (future) close connection pools, flush Kafka producer, etc.

    Tables created:
      - github_installations
      - repositories
      - repository_syncs

    Tables read-only (owned by api service):
      - memberships  (used for org membership checks in dependencies.py)
    """
    logger.info(
        "ForgeAI Repository Service starting",
        extra={"version": "0.1.0", "port": 8001},
    )
    Base.metadata.create_all(bind=engine)
    _ensure_readiness_columns(engine)
    yield
    logger.info("ForgeAI Repository Service shutting down")


def _ensure_readiness_columns(engine) -> None:
    """
    Adds the readiness checkpoint columns to an existing ``repositories`` table.

    ``Base.metadata.create_all`` only creates missing tables — it never alters
    an existing one. We keep this hand-rolled (rather than adding Alembic) to
    match the rest of the deployment, and make it idempotent so every startup
    can run it safely. Only PostgreSQL is migrated; SQLite test databases are
    created from the current model and already have the columns.
    """
    if engine.dialect.name != "postgresql":
        return

    from sqlalchemy import text

    statements = (
        "ALTER TABLE repositories ADD COLUMN IF NOT EXISTS repo_map_ready_at TIMESTAMPTZ",
        "ALTER TABLE repositories ADD COLUMN IF NOT EXISTS chat_ready_at TIMESTAMPTZ",
        "ALTER TABLE repositories ADD COLUMN IF NOT EXISTS index_ready_at TIMESTAMPTZ",
    )
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        logger.info("Repository readiness columns verified")
    except Exception as exc:  # pragma: no cover - depends on live PostgreSQL
        logger.warning(
            "Could not add repository readiness columns",
            extra={"error": str(exc)},
        )


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "ForgeAI Repository Service — manages GitHub App installations, "
        "repository connections, synchronization lifecycle, and webhook events."
    ),
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ───────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Liveness check — returns 200 if the service is running."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": "0.1.0",
    }

# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(github.router, prefix=settings.API_V1_STR)
app.include_router(repositories.router, prefix=settings.API_V1_STR)
app.include_router(pull_requests.router, prefix=settings.API_V1_STR)
app.include_router(internal.router, prefix=settings.API_V1_STR)
