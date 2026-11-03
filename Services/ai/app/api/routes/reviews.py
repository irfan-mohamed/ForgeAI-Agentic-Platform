"""
Code review routes.

POST /api/v1/organizations/{org_id}/code-reviews        — start a review (202)
GET  /api/v1/organizations/{org_id}/code-reviews        — list reviews
GET  /api/v1/code-reviews/{review_id}                   — review with findings

The pull request itself is read through the Repository Service (which owns
GitHub access); the review runs in the background and is polled by status:
QUEUED → RUNNING → COMPLETED | FAILED.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.access import get_repository, parse_id, require_org_member
from app.core.security import BearerToken, UserId
from app.db.database import get_db
from app.models.review import CodeReview, PullRequest, ReviewFinding
from app.services import repository_client, review_service

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class StartReviewRequest(BaseModel):
    repository_id: int = Field(ge=1)
    pull_number: int = Field(ge=1)


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    severity: str
    title: str
    description: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    recommendation: str | None


class CodeReviewSummary(BaseModel):
    id: str
    repository_id: int
    pull_number: int
    pull_title: str
    pull_url: str | None
    status: str
    assessment: str | None
    overall_score: float | None
    summary: str | None
    head_sha: str | None
    files_reviewed: int
    files_omitted: int
    severity_counts: SeverityCounts
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CodeReviewDetail(CodeReviewSummary):
    findings: list[FindingOut]


class CodeReviewListResponse(BaseModel):
    reviews: list[CodeReviewSummary]
    total: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _severity_counts(db: Session, review_ids: list[str]) -> dict[str, SeverityCounts]:
    counts = {rid: SeverityCounts() for rid in review_ids}
    if not review_ids:
        return counts
    rows = (
        db.query(ReviewFinding.code_review_id, ReviewFinding.severity, func.count(ReviewFinding.id))
        .filter(ReviewFinding.code_review_id.in_(review_ids))
        .group_by(ReviewFinding.code_review_id, ReviewFinding.severity)
        .all()
    )
    for review_id, severity, count in rows:
        setattr(counts[review_id], severity.lower(), count)
    return counts


def _summary_fields(review: CodeReview, counts: SeverityCounts) -> dict:
    pr = review.pull_request
    return {
        "id": review.id,
        "repository_id": review.repository_id,
        "pull_number": pr.number,
        "pull_title": pr.title,
        "pull_url": pr.html_url,
        "status": review.status,
        "assessment": review.assessment,
        "overall_score": review.overall_score,
        "summary": review.summary,
        "head_sha": review.head_sha,
        "files_reviewed": review.files_reviewed,
        "files_omitted": review.files_omitted,
        "severity_counts": counts,
        "error_message": review.error_message,
        "created_at": review.created_at,
        "completed_at": review.completed_at,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/organizations/{org_id}/code-reviews",
    response_model=CodeReviewSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_code_review(
    org_id: str,
    body: StartReviewRequest,
    user_id: UserId,
    token: BearerToken,
    background_tasks: BackgroundTasks,
    db: DB,
):
    """Queue an AI review of a pull request in a connected repository."""
    org = parse_id(org_id, "organization id")
    require_org_member(db, user_id, org)
    repo = get_repository(db, org, body.repository_id, require_ready=True)

    pr = repository_client.get_pull_request(repo.id, body.pull_number, token)
    pr_row = review_service.upsert_pull_request(db, org, repo.id, pr)

    if review_service.find_active_review(db, pr_row.id):
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A review of this pull request is already queued or running.",
        )

    review = CodeReview(
        org_id=org,
        repository_id=repo.id,
        pull_request_id=pr_row.id,
        requested_by=str(user_id),
        head_sha=pr.get("head_sha"),
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    background_tasks.add_task(
        review_service.run_review_job,
        review.id,
        org,
        repo.id,
        repo.full_name,
        pr,
    )

    return _summary_fields(review, SeverityCounts())


@router.get(
    "/organizations/{org_id}/code-reviews",
    response_model=CodeReviewListResponse,
)
def list_code_reviews(
    org_id: str,
    user_id: UserId,
    db: DB,
    repository_id: int | None = Query(None, ge=1),
    pull_number: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List reviews in an organization, newest first."""
    org = parse_id(org_id, "organization id")
    require_org_member(db, user_id, org)

    query = db.query(CodeReview).filter(CodeReview.org_id == org)
    if repository_id is not None:
        query = query.filter(CodeReview.repository_id == repository_id)
    if pull_number is not None:
        query = query.join(PullRequest, CodeReview.pull_request_id == PullRequest.id).filter(
            PullRequest.number == pull_number
        )

    total = query.count()
    reviews = (
        query.order_by(CodeReview.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    review_service.expire_stale(db, reviews)

    counts = _severity_counts(db, [r.id for r in reviews])
    return {
        "reviews": [_summary_fields(r, counts[r.id]) for r in reviews],
        "total": total,
    }


@router.get(
    "/code-reviews/{review_id}",
    response_model=CodeReviewDetail,
)
def get_code_review(
    review_id: str,
    user_id: UserId,
    db: DB,
):
    """Get one review with all its findings."""
    review = db.get(CodeReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Code review not found")
    # Members of the owning organization may read it; others get the same 404.
    try:
        require_org_member(db, user_id, review.org_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Code review not found")

    review_service.expire_stale(db, [review])
    counts = _severity_counts(db, [review.id])[review.id]
    return {
        **_summary_fields(review, counts),
        "findings": review.findings,
    }
