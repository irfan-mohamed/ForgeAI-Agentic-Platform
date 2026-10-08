"""
Pydantic schemas for Repository management endpoints.

Covers:
- Connecting a repository (request + response)
- Listing connected repositories
- Repository sync status
- Disconnect (no body, 204 response)
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ── Connect Repository ────────────────────────────────────────────────────────

class RepositoryConnectRequest(BaseModel):
    """
    Body for POST /organizations/{org_id}/repositories.
    The client supplies the GitHub repository ID obtained from the
    available-repos listing endpoint.
    """
    github_repository_id: str


# ── Repository Response ───────────────────────────────────────────────────────

class RepositoryResponse(BaseModel):
    """Full public representation of a connected repository."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    github_repository_id: str
    name: str
    full_name: str
    owner: str
    description: str | None
    visibility: str
    default_branch: str
    status: str
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    """Response for GET /organizations/{org_id}/repositories"""
    repositories: list[RepositoryResponse]


# ── Sync ──────────────────────────────────────────────────────────────────────

class RepositorySyncResponse(BaseModel):
    """
    Returned immediately after a sync is requested.
    The actual sync runs asynchronously in the Worker.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    status: str
    trigger: str
    created_at: datetime


class SyncProgressDetail(BaseModel):
    """Nested progress counters inside sync status."""
    files_discovered: int
    files_processed: int
    files_failed: int


class RepositorySyncStatusResponse(BaseModel):
    """
    Response for GET /repositories/{repo_id}/sync/status.
    Clients poll this to track sync progress.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    status: str
    trigger: str
    commit_sha: str | None
    started_at: datetime | None
    completed_at: datetime | None
    progress: SyncProgressDetail
    error_message: str | None
    created_at: datetime
