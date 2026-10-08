"""
Pydantic schemas for GitHub integration endpoints.

These schemas cover:
- GitHub connection status responses
- Available repository listings (repos visible via the GitHub App installation)
- GitHub installation details returned after the OAuth callback
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ── GitHub Connection Status ──────────────────────────────────────────────────

class GitHubAccountInfo(BaseModel):
    """The GitHub account (user or org) that installed the ForgeAI App."""
    login: str
    account_type: str  # "User" | "Organization"


class GitHubConnectionStatus(BaseModel):
    """Response for GET /organizations/{org_id}/github"""
    connected: bool
    account: GitHubAccountInfo | None = None


# ── Installation Response ─────────────────────────────────────────────────────

class GitHubInstallationResponse(BaseModel):
    """Returned after the GitHub App installation callback is processed."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    github_installation_id: int
    github_account_login: str
    account_type: str
    status: str
    installed_at: datetime


# ── Available Repositories ────────────────────────────────────────────────────

class GitHubAvailableRepo(BaseModel):
    """
    A single repository visible through the GitHub App installation.
    These are repos that GitHub has granted the installation access to.
    They are NOT yet connected to ForgeAI — they are candidates.
    """
    github_repository_id: str
    name: str
    full_name: str
    owner: str
    visibility: str        # "public" | "private"
    default_branch: str
    description: str | None = None


class GitHubAvailableReposResponse(BaseModel):
    """Response for GET /organizations/{org_id}/github/repositories"""
    repositories: list[GitHubAvailableRepo]


# ── Webhook ───────────────────────────────────────────────────────────────────

class WebhookAckResponse(BaseModel):
    """Standard acknowledgement response for webhook endpoints."""
    received: bool = True
