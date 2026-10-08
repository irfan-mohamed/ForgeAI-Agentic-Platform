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

from app.api.routes import github, repositories

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
    yield
    logger.info("ForgeAI Repository Service shutting down")


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
