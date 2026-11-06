"""
review_service.py — Persistence and background execution of code reviews.

Reviews run as FastAPI background tasks: the POST endpoint creates a QUEUED
review and returns 202; ``run_review_job`` then moves it through
RUNNING → COMPLETED / FAILED using its own database sessions.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import db_session
from app.models.review import (
    ACTIVE_REVIEW_STATUSES,
    CodeReview,
    PullRequest,
    ReviewFinding,
    ReviewStatus,
)
from app.services import llm
from app.services.code_review_agent import ReviewParseError, generate_review

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _public_error(exc: Exception) -> str:
    """A safe message to show the user; the full error goes to the logs."""
    if isinstance(exc, llm.LLMNotConfigured):
        return "The AI provider is not configured."
    if isinstance(exc, ReviewParseError):
        return "The AI returned a review that could not be understood. Please try again."
    return "The review failed. Please try again."


def upsert_pull_request(
    db: Session,
    org_id: int,
    repository_id: int,
    pr: dict,
) -> PullRequest:
    """Creates or refreshes the stored metadata for a pull request."""
    number = int(pr["number"])
    row = (
        db.query(PullRequest)
        .filter(PullRequest.repository_id == repository_id, PullRequest.number == number)
        .first()
    )
    if row is None:
        row = PullRequest(org_id=org_id, repository_id=repository_id, number=number)
        db.add(row)

    row.title = (pr.get("title") or f"Pull request #{number}")[:500]
    row.author = (pr.get("author") or None)
    row.source_branch = pr.get("source_branch")
    row.target_branch = pr.get("target_branch")
    row.state = pr.get("state") or "open"
    row.head_sha = pr.get("head_sha")
    row.html_url = pr.get("html_url")
    db.flush()
    return row


def expire_stale(db: Session, reviews: list[CodeReview]) -> None:
    """Marks reviews that never finished (crash, restart) as FAILED."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.REVIEW_STALE_MINUTES)
    changed = False
    for review in reviews:
        if review.status in ACTIVE_REVIEW_STATUSES and _as_utc(review.created_at) < cutoff:
            review.status = ReviewStatus.FAILED.value
            review.error_message = "The review did not finish in time. Please run it again."
            review.completed_at = datetime.now(timezone.utc)
            changed = True
    if changed:
        db.commit()


def find_active_review(db: Session, pull_request_id: int) -> CodeReview | None:
    """Returns a queued/running review for the pull request, if any."""
    candidates = (
        db.query(CodeReview)
        .filter(
            CodeReview.pull_request_id == pull_request_id,
            CodeReview.status.in_(ACTIVE_REVIEW_STATUSES),
        )
        .all()
    )
    expire_stale(db, candidates)
    for review in candidates:
        if review.status in ACTIVE_REVIEW_STATUSES:
            return review
    return None


def fail_stale_reviews_on_startup() -> int:
    """Startup sweep so crashed reviews do not stay RUNNING forever."""
    with db_session() as db:
        stale = (
            db.query(CodeReview)
            .filter(CodeReview.status.in_(ACTIVE_REVIEW_STATUSES))
            .all()
        )
        before = sum(1 for r in stale if r.status in ACTIVE_REVIEW_STATUSES)
        expire_stale(db, stale)
        after = sum(1 for r in stale if r.status in ACTIVE_REVIEW_STATUSES)
        return before - after


def run_review_job(
    review_id: str,
    org_id: int,
    repository_id: int,
    repository_name: str,
    pr: dict,
) -> None:
    """Background task: runs the Code Review Agent and stores the outcome."""
    with db_session() as db:
        review = db.get(CodeReview, review_id)
        if review is None or review.status != ReviewStatus.QUEUED.value:
            return
        review.status = ReviewStatus.RUNNING.value
        review.started_at = datetime.now(timezone.utc)

    logger.info(
        "Code review started",
        extra={"review_id": review_id, "repository_id": repository_id, "pr": pr.get("number")},
    )

    try:
        result = generate_review(
            org_id=org_id,
            repository_id=repository_id,
            repository_name=repository_name,
            pr=pr,
        )
    except Exception as exc:
        logger.exception("Code review failed", extra={"review_id": review_id})
        with db_session() as db:
            review = db.get(CodeReview, review_id)
            if review is not None:
                review.status = ReviewStatus.FAILED.value
                review.error_message = _public_error(exc)
                review.completed_at = datetime.now(timezone.utc)
        return

    with db_session() as db:
        review = db.get(CodeReview, review_id)
        if review is None:
            return
        for position, finding in enumerate(result.findings):
            db.add(
                ReviewFinding(
                    code_review_id=review.id,
                    position=position,
                    category=finding.category,
                    severity=finding.severity,
                    title=finding.title,
                    description=finding.description,
                    file_path=finding.file_path,
                    line_start=finding.line_start,
                    line_end=finding.line_end,
                    recommendation=finding.recommendation,
                )
            )
        review.summary = result.summary
        review.overall_score = result.overall_score
        review.assessment = result.assessment
        review.files_reviewed = result.files_reviewed
        review.files_omitted = result.files_omitted
        review.total_tokens = result.total_tokens
        review.status = ReviewStatus.COMPLETED.value
        review.completed_at = datetime.now(timezone.utc)

    logger.info(
        "Code review completed",
        extra={"review_id": review_id, "findings": len(result.findings)},
    )
