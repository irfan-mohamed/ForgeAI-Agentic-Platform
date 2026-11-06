"""
AI Service owned models for pull request code review:
  - PullRequest    : a GitHub pull request that has been reviewed (cached metadata)
  - CodeReview     : one ForgeAI review run of a pull request
  - ReviewFinding  : an individual issue found in a review

Tenant isolation: org_id and repository_id are stored on PullRequest and
CodeReview and checked against the caller's memberships on every request.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class ReviewStatus(str, PyEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


ACTIVE_REVIEW_STATUSES = (ReviewStatus.QUEUED.value, ReviewStatus.RUNNING.value)


class PullRequest(Base):
    """Pull request metadata, upserted whenever a review is requested."""
    __tablename__ = "pull_requests"

    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pull_request_repo_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # open | closed | merged
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    reviews: Mapped[list["CodeReview"]] = relationship(
        "CodeReview",
        back_populates="pull_request",
        cascade="all, delete-orphan",
    )


class CodeReview(Base):
    """One review run. Findings are stored separately so they can be queried."""
    __tablename__ = "code_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pull_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReviewStatus.QUEUED.value, index=True
    )
    # LOOKS_GOOD | NEEDS_ATTENTION | BLOCKING_ISSUES (derived from findings)
    assessment: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 0–10
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    files_reviewed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_omitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="reviews")
    findings: Mapped[list["ReviewFinding"]] = relationship(
        "ReviewFinding",
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ReviewFinding.position",
    )


class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code_review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("code_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Keeps findings in the order the agent ranked them (most severe first).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # BUG | SECURITY | CODE_QUALITY | ARCHITECTURE | PERFORMANCE | TESTING
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # CRITICAL | HIGH | MEDIUM | LOW | INFO
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    review: Mapped["CodeReview"] = relationship("CodeReview", back_populates="findings")
