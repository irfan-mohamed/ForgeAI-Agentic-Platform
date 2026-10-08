"""
github.py — Routes for GitHub App integration.

Endpoints:
  GET  /organizations/{org_id}/github/install     → Start GitHub App installation
  GET  /github/callback                           → Handle GitHub App callback
  GET  /organizations/{org_id}/github             → Check connection status
  GET  /organizations/{org_id}/github/repositories → List available repos
  POST /github/webhook                            → Receive GitHub App events
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_org_membership
from app.core.config import settings
from app.db.database import get_db
from app.schemas.github import (
    GitHubAvailableReposResponse,
    GitHubConnectionStatus,
    GitHubInstallationResponse,
    WebhookAckResponse,
)
from app.services import github_service
from app.services.repository_service import RepositoryService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GitHub Integration"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_state_token(org_id: int, user_id: int) -> str:
    """
    Creates a simple CSRF state token: base64-encoded JSON signed with HMAC.

    For production, replace with a proper signed JWT or Redis-stored nonce.
    """
    import base64
    import time

    payload = json.dumps({"org_id": org_id, "user_id": user_id, "ts": int(time.time())})
    mac = hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    raw = json.dumps({"payload": payload, "mac": mac})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_state_token(state: str) -> dict:
    """
    Decodes and validates a state token from _make_state_token.

    Raises HTTPException 400 if invalid or tampered.
    """
    import base64
    import time

    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        obj = json.loads(raw)
        payload = obj["payload"]
        mac = obj["mac"]
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state token.")

    expected_mac = hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(mac, expected_mac):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State token tampered.")

    data = json.loads(payload)

    # Reject tokens older than 10 minutes.
    if int(time.time()) - data.get("ts", 0) > 600:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State token expired.")

    return data


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/github/install",
    summary="Get GitHub App installation URL",
    status_code=status.HTTP_200_OK,
)
def start_github_installation(
    org_id: int,
    user_id: int = Depends(get_org_membership),
):
    """
    Returns the GitHub App installation URL as JSON.

    The frontend fetches this endpoint (with Bearer token) and then navigates
    the browser to the returned URL via window.location.href.
    This pattern is required because browsers strip Authorization headers on
    navigation requests, making a server-side redirect impossible to authenticate.

    Response:
        { "install_url": "https://github.com/apps/<app>/installations/new?state=..." }
    """
    state = _make_state_token(org_id=org_id, user_id=user_id)
    url = github_service.build_app_installation_url(state=state)
    return {"install_url": url}


@router.get(
    "/github/callback",
    summary="GitHub App installation callback",
)
def github_callback(
    installation_id: int = Query(..., description="Installation ID from GitHub"),
    setup_action: str = Query(default="install"),
    state: str = Query(..., description="CSRF state token"),
    db: Session = Depends(get_db),
):
    """
    Receives the redirect from GitHub after the user installs the App.

    Validates the state token, fetches installation info from GitHub,
    saves the GitHubInstallation record, then redirects the user to
    the frontend.

    Note: This endpoint does NOT require a JWT — GitHub calls it directly.
    The CSRF protection comes from the signed state parameter.
    """
    # Validate and decode the state token.
    state_data = _decode_state_token(state)
    org_id = state_data["org_id"]

    # Fetch installation metadata from GitHub to get account info.
    try:
        install_info = github_service.get_installation_info(installation_id)
    except RuntimeError as exc:
        logger.error(
            "Failed to fetch installation info from GitHub",
            extra={"installation_id": installation_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve installation information from GitHub.",
        )

    account = install_info.get("account", {})

    # Save the installation record.
    RepositoryService.create_or_update_installation(
        organization_id=org_id,
        github_installation_id=installation_id,
        github_account_id=account.get("id", 0),
        github_account_login=account.get("login", ""),
        account_type=account.get("type", "User"),
        db=db,
    )

    logger.info(
        "GitHub App installed successfully",
        extra={"org_id": org_id, "installation_id": installation_id},
    )

    # Redirect to the frontend with success indicator.
    redirect_url = f"{settings.GITHUB_CALLBACK_REDIRECT_URL}?org_id={org_id}&status=connected"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get(
    "/organizations/{org_id}/github",
    response_model=GitHubConnectionStatus,
    summary="Get GitHub connection status",
)
def get_github_status(
    org_id: int,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
):
    """
    Returns whether the organization has an active GitHub App installation.

    If connected, also returns the GitHub account login and type.
    """
    return RepositoryService.get_connection_status(organization_id=org_id, db=db)


@router.get(
    "/organizations/{org_id}/github/repositories",
    response_model=GitHubAvailableReposResponse,
    summary="List available GitHub repositories",
)
def list_available_repositories(
    org_id: int,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
):
    """
    Lists all repositories available to ForgeAI through the GitHub App installation.

    These are candidate repositories — they are visible to ForgeAI but not yet
    connected. The user selects from this list to connect a repository.

    Fetches live data from GitHub API using the installation access token.
    """
    repos = RepositoryService.list_available_repositories(
        organization_id=org_id,
        db=db,
    )
    return GitHubAvailableReposResponse(repositories=repos)


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post(
    "/github/webhook",
    response_model=WebhookAckResponse,
    summary="GitHub App webhook receiver",
)
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives all GitHub App webhook events.

    Security: Validates the X-Hub-Signature-256 HMAC header before processing.
    Any request with an invalid or missing signature is rejected with HTTP 401.

    Handled events:
      - installation.deleted                → revoke all org repositories
      - installation_repositories.removed  → revoke specific repositories
      - push                               → trigger repository re-sync
      - pull_request (opened/synchronize)  → future: trigger AI code review

    All other events return 200 immediately (acknowledged but ignored).
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    # ── Signature validation (MANDATORY) ─────────────────────────────────────
    if not github_service.validate_webhook_signature(raw_body, signature):
        logger.warning(
            "Webhook rejected — invalid signature",
            extra={"signature": signature},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        )

    action = payload.get("action", "")
    installation_id = payload.get("installation", {}).get("id")

    logger.info(
        "GitHub webhook received",
        extra={"event": event_type, "action": action, "installation_id": installation_id},
    )

    # ── Route by event type ───────────────────────────────────────────────────

    if event_type == "installation" and action == "deleted":
        if installation_id:
            RepositoryService.handle_installation_deleted(
                github_installation_id=installation_id,
                db=db,
            )

    elif event_type == "installation_repositories" and action == "removed":
        removed = payload.get("repositories_removed", [])
        removed_ids = [str(r["id"]) for r in removed]
        if installation_id and removed_ids:
            RepositoryService.handle_installation_repos_removed(
                github_installation_id=installation_id,
                removed_github_repo_ids=removed_ids,
                db=db,
            )

    elif event_type == "push":
        repo_data = payload.get("repository", {})
        github_repo_id = str(repo_data.get("id", ""))
        commit_sha = payload.get("after", "")
        if installation_id and github_repo_id and commit_sha:
            RepositoryService.handle_push_event(
                github_installation_id=installation_id,
                github_repository_id=github_repo_id,
                commit_sha=commit_sha,
                db=db,
            )

    elif event_type == "pull_request" and action in ("opened", "synchronize"):
        # Future: publish pull_request event for AI Code Review service.
        logger.info(
            "Pull request event received (not yet handled — future AI review)",
            extra={"pr_number": payload.get("number"), "action": action},
        )

    # All other events are acknowledged and ignored.
    return WebhookAckResponse(received=True)
