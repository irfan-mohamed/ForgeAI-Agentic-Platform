"""
pull_requests.py — Read pull requests of a connected repository from GitHub.

Endpoints:
  GET /repositories/{repo_id}/pull-requests            → list (open/closed/all)
  GET /repositories/{repo_id}/pull-requests/{number}   → detail with changed files

The AI Service calls the detail endpoint (forwarding the user's JWT) to get
the diff for code review and test assistance, so GitHub access stays in this
service.
"""

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id
from app.db.database import get_db
from app.models.github_installation import GitHubInstallation, InstallationStatus
from app.models.repository import Repository, RepositoryStatus
from app.schemas.pull_request import (
    PullRequestDetail,
    PullRequestFile,
    PullRequestListResponse,
    PullRequestSummary,
)
from app.services import github_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pull Requests"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _authorized_repository(
    repo_id: int,
    user_id: int,
    db: Session,
) -> tuple[Repository, GitHubInstallation]:
    """
    Returns the repository and its installation if the user belongs to the
    owning organization and GitHub access is still active.

    Unknown repositories and repositories of other organizations both return
    404 so IDs of other tenants are not revealed.
    """
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    member = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id AND organization_id = :org_id "
            "AND status = 'active' LIMIT 1"
        ),
        {"user_id": user_id, "org_id": repo.organization_id},
    ).fetchone()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    if repo.status in (
        RepositoryStatus.DISCONNECTED.value,
        RepositoryStatus.ACCESS_REVOKED.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This repository is no longer connected to GitHub.",
        )

    installation = db.get(GitHubInstallation, repo.github_installation_id)
    if installation is None or installation.status != InstallationStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The GitHub installation for this repository is not active.",
        )
    return repo, installation


def _summary(raw: dict[str, Any]) -> PullRequestSummary:
    head = raw.get("head") or {}
    base = raw.get("base") or {}
    state = "merged" if raw.get("merged_at") else raw.get("state", "open")
    return PullRequestSummary(
        number=raw["number"],
        title=raw.get("title") or "",
        state=state,
        draft=bool(raw.get("draft")),
        author=(raw.get("user") or {}).get("login"),
        source_branch=head.get("ref"),
        target_branch=base.get("ref"),
        head_sha=head.get("sha"),
        html_url=raw.get("html_url"),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


def _github_unavailable(exc: Exception, context: str) -> HTTPException:
    logger.error("GitHub call failed", extra={"context": context, "error": str(exc)})
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Failed to read pull requests from GitHub. Please try again.",
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/repositories/{repo_id}/pull-requests",
    response_model=PullRequestListResponse,
    summary="List pull requests",
)
def list_pull_requests(
    repo_id: int,
    state: Literal["open", "closed", "all"] = Query("open"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Lists pull requests of a connected repository, most recently updated first."""
    repo, installation = _authorized_repository(repo_id, user_id, db)

    try:
        token = github_service.get_installation_access_token(
            installation.github_installation_id
        )
        raw = github_service.list_pull_requests(
            token, repo.full_name, state=state, page=page, per_page=limit
        )
    except github_service.GitHubNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found on GitHub.")
    except RuntimeError as exc:
        raise _github_unavailable(exc, "list_pull_requests")

    return PullRequestListResponse(
        pull_requests=[_summary(item) for item in raw],
        page=page,
        limit=limit,
    )


@router.get(
    "/repositories/{repo_id}/pull-requests/{number}",
    response_model=PullRequestDetail,
    summary="Get a pull request with its diff",
)
def get_pull_request(
    repo_id: int,
    number: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Returns pull request metadata and the changed files with their patches."""
    repo, installation = _authorized_repository(repo_id, user_id, db)

    try:
        token = github_service.get_installation_access_token(
            installation.github_installation_id
        )
        raw = github_service.get_pull_request(token, repo.full_name, number)
        files, truncated = github_service.list_pull_request_files(
            token, repo.full_name, number
        )
    except github_service.GitHubNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pull request not found.")
    except RuntimeError as exc:
        raise _github_unavailable(exc, "get_pull_request")

    summary = _summary(raw)
    return PullRequestDetail(
        **summary.model_dump(),
        body=raw.get("body"),
        additions=raw.get("additions", 0) or 0,
        deletions=raw.get("deletions", 0) or 0,
        changed_files=raw.get("changed_files", len(files)) or 0,
        files=[
            PullRequestFile(
                filename=f.get("filename", ""),
                status=f.get("status", "modified"),
                additions=f.get("additions", 0) or 0,
                deletions=f.get("deletions", 0) or 0,
                patch=f.get("patch"),
            )
            for f in files
        ],
        files_truncated=truncated,
    )
