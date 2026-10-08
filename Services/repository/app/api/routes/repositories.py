"""
repositories.py — Routes for repository management.

Endpoints:
  POST   /organizations/{org_id}/repositories          → Connect a GitHub repo
  GET    /organizations/{org_id}/repositories          → List connected repos
  GET    /repositories/{repo_id}                       → Get a single repo
  POST   /repositories/{repo_id}/sync                  → Request a re-sync
  GET    /repositories/{repo_id}/sync/status           → Poll sync progress
  DELETE /repositories/{repo_id}                       → Disconnect a repo
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_org_membership
from app.db.database import get_db
from app.schemas.repository import (
    RepositoryConnectRequest,
    RepositoryListResponse,
    RepositoryResponse,
    RepositorySyncResponse,
    RepositorySyncStatusResponse,
)
from app.services.repository_service import RepositoryService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Repositories"])


# ── Organization-scoped endpoints ─────────────────────────────────────────────

@router.post(
    "/organizations/{org_id}/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect a GitHub repository",
)
def connect_repository(
    org_id: int,
    body: RepositoryConnectRequest,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
):
    """
    Connects a GitHub repository to the ForgeAI organization.

    The ``github_repository_id`` must be obtained from the
    ``GET /organizations/{org_id}/github/repositories`` endpoint.

    The response status will be ``CONNECTING`` immediately.
    A sync job is queued asynchronously — poll
    ``GET /repositories/{id}/sync/status`` to track progress.
    """
    repo = RepositoryService.connect_repository(
        organization_id=org_id,
        github_repository_id=body.github_repository_id,
        db=db,
    )
    logger.info(
        "Repository connected via API",
        extra={"org_id": org_id, "repo_id": repo.id, "user_id": user_id},
    )
    return repo


@router.get(
    "/organizations/{org_id}/repositories",
    response_model=RepositoryListResponse,
    summary="List connected repositories",
)
def list_repositories(
    org_id: int,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
):
    """
    Returns all repositories connected to the organization.

    Excludes disconnected repositories. Includes repositories in all
    other states (CONNECTING, SYNCING, INDEXING, READY, FAILED, ACCESS_REVOKED).
    """
    repos = RepositoryService.list_org_repositories(
        organization_id=org_id,
        db=db,
    )
    return RepositoryListResponse(repositories=repos)


# ── Repository-scoped endpoints ───────────────────────────────────────────────

@router.get(
    "/repositories/{repo_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
)
def get_repository(
    repo_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Returns details of a single connected repository.

    Authorization is enforced via the repository's ``organization_id`` —
    the user must be a member of the organization that owns the repository.
    The membership check is performed inside ``RepositoryService.get_repository``.
    """
    # We need the org_id to verify membership. We get it from the repo itself.
    # First fetch the repo (may 404), then verify membership.
    from app.models.repository import Repository
    from fastapi import HTTPException

    raw_repo = db.get(Repository, repo_id)
    if not raw_repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # Verify the user is a member of the owning organization.
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id AND organization_id = :org_id "
            "AND status = 'active' LIMIT 1"
        ),
        {"user_id": user_id, "org_id": raw_repo.organization_id},
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    return raw_repo


@router.post(
    "/repositories/{repo_id}/sync",
    response_model=RepositorySyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a repository re-sync",
)
def request_sync(
    repo_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Queues a manual synchronization for the repository.

    Returns immediately with status ``QUEUED``.
    The actual sync runs asynchronously in the Worker service.

    Raises 409 if a sync is already running or queued.
    """
    from app.models.repository import Repository
    from fastapi import HTTPException

    raw_repo = db.get(Repository, repo_id)
    if not raw_repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # Verify org membership.
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id AND organization_id = :org_id "
            "AND status = 'active' LIMIT 1"
        ),
        {"user_id": user_id, "org_id": raw_repo.organization_id},
    ).fetchone()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    sync = RepositoryService.request_sync(
        repo_id=repo_id,
        organization_id=raw_repo.organization_id,
        db=db,
    )
    logger.info(
        "Sync requested via API",
        extra={"repo_id": repo_id, "sync_id": sync.id, "user_id": user_id},
    )
    return sync


@router.get(
    "/repositories/{repo_id}/sync/status",
    response_model=RepositorySyncStatusResponse,
    summary="Get repository sync status",
)
def get_sync_status(
    repo_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Returns the latest sync status for a repository.

    Clients should poll this endpoint to track sync progress.
    The ``progress`` field contains file-level counts updated by the Worker.
    """
    from app.models.repository import Repository
    from fastapi import HTTPException

    raw_repo = db.get(Repository, repo_id)
    if not raw_repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # Verify org membership.
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id AND organization_id = :org_id "
            "AND status = 'active' LIMIT 1"
        ),
        {"user_id": user_id, "org_id": raw_repo.organization_id},
    ).fetchone()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    return RepositoryService.get_sync_status(
        repo_id=repo_id,
        organization_id=raw_repo.organization_id,
        db=db,
    )


@router.delete(
    "/repositories/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect a repository",
)
def disconnect_repository(
    repo_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Disconnects a repository from ForgeAI.

    Marks the repository status as ``DISCONNECTED`` and publishes a
    ``repository.disconnected`` event. The repository record is preserved
    for audit history. Knowledge cleanup is handled separately.
    """
    from app.models.repository import Repository
    from fastapi import HTTPException

    raw_repo = db.get(Repository, repo_id)
    if not raw_repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # Verify org membership.
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id AND organization_id = :org_id "
            "AND status = 'active' LIMIT 1"
        ),
        {"user_id": user_id, "org_id": raw_repo.organization_id},
    ).fetchone()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    RepositoryService.disconnect_repository(
        repo_id=repo_id,
        organization_id=raw_repo.organization_id,
        db=db,
    )
    logger.info(
        "Repository disconnected via API",
        extra={"repo_id": repo_id, "user_id": user_id},
    )
