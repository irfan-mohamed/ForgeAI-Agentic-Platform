"""
ForgeAI AI Service — FastAPI application entry point.

Responsibilities:
  - Engineering Agent (RAG-powered chat with repository context)
  - Conversation management (create, list, get, delete)
  - SSE streaming for real-time AI responses
  - Agent run tracking (token counts, retrieved chunks, status)
  - Pull request code review (Code Review Agent, background jobs)
  - Test assistance (Testing Agent)

Port: 8002 (API=8000, Repository=8001, AI=8002)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.base import Base
from app.db.database import engine

# Ensure all models are imported so their tables are created
import app.models.conversation  # noqa: F401
import app.models.review  # noqa: F401
import app.models.plan  # noqa: F401 — ImplementationPlan + ImplementationApproval

from app.services import review_service

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info(
        "ForgeAI AI Service starting",
        extra={"version": settings.VERSION, "port": 8002},
    )
    # Create AI service owned tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Database tables ready",
        extra={
            "tables": [
                "conversations",
                "messages",
                "agent_runs",
                "pull_requests",
                "code_reviews",
                "review_findings",
                "implementation_plans",
                "implementation_approvals",
            ]
        },
    )

    # Reviews left QUEUED/RUNNING by a crash or restart must not hang forever.
    expired = review_service.fail_stale_reviews_on_startup()
    if expired:
        logger.warning("Marked stale code reviews as failed", extra={"count": expired})

    yield
    logger.info("ForgeAI AI Service shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Engineering AI, code review, test assistance, and conversation management",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", tags=["Health"])
    def root():
        return {"service": settings.PROJECT_NAME, "version": settings.VERSION}

    return app


app = create_app()
