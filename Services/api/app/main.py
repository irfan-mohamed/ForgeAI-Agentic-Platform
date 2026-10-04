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

from app.api.routes import auth, users, organizations

# ── Logging ────────────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Startup: create DB tables.
    Shutdown: (future) close connection pools, flush queues, etc.

    Using a lifespan event (rather than module-level create_all) prevents the
    app from trying to connect to PostgreSQL when tests import the module,
    since tests override the DB engine before the lifespan runs.
    """
    logger.info("FlowForge API starting", extra={"version": "0.1.0"})
    Base.metadata.create_all(bind=engine)
    yield
    logger.info("FlowForge API shutting down")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "FlowForge — AI-powered employee onboarding and knowledge orchestration. "
        "Release 0: Foundation."
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


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Liveness check — returns 200 if the API is running."""
    return {"status": "ok", "service": settings.PROJECT_NAME}


app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(organizations.router, prefix=settings.API_V1_STR)