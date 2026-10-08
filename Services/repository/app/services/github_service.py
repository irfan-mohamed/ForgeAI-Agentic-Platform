"""
github_service.py — All communication with the GitHub API.

Responsibilities:
  - Generate GitHub App JWTs (RS256, signed with App private key)
  - Exchange for short-lived installation access tokens
  - List repositories accessible through an installation
  - Fetch individual repository metadata
  - Build the GitHub App installation redirect URL
  - Validate incoming webhook signatures (HMAC-SHA256)

Authentication flow:
    GitHub App JWT  →  Installation Access Token  →  GitHub API calls
    (expires 10min)    (expires ~1 hour)

All GitHub API calls use httpx for sync compatibility with FastAPI's
default synchronous route handlers.
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.security import create_github_app_jwt
from app.schemas.github import GitHubAvailableRepo

logger = logging.getLogger(__name__)

GITHUB_API = settings.GITHUB_API_BASE_URL


# ── Internal helpers ──────────────────────────────────────────────────────────

def _app_headers() -> dict[str, str]:
    """Headers for calls authenticated as the GitHub App itself."""
    return {
        "Authorization": f"Bearer {create_github_app_jwt()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _installation_headers(token: str) -> dict[str, str]:
    """Headers for calls authenticated as a specific installation."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for_github_error(response: httpx.Response, context: str) -> None:
    """Raises RuntimeError with a helpful message if GitHub returned an error."""
    if response.is_error:
        logger.error(
            "GitHub API error",
            extra={
                "context": context,
                "status_code": response.status_code,
                "response_body": response.text[:500],
            },
        )
        raise RuntimeError(
            f"GitHub API error during '{context}': "
            f"HTTP {response.status_code} — {response.text[:200]}"
        )


# ── Public API ────────────────────────────────────────────────────────────────

def get_installation_access_token(github_installation_id: int) -> str:
    """
    Exchanges the GitHub App JWT for a short-lived installation access token.

    Installation tokens expire in approximately 1 hour.
    They are used to call GitHub APIs on behalf of a specific installation.

    Raises RuntimeError if GitHub is unavailable or returns an error.
    """
    url = f"{GITHUB_API}/app/installations/{github_installation_id}/access_tokens"
    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, headers=_app_headers())

    _raise_for_github_error(response, "get_installation_access_token")
    data = response.json()
    token = data.get("token")
    if not token:
        raise RuntimeError("GitHub did not return an access token in the response.")

    logger.info(
        "GitHub installation token obtained",
        extra={"github_installation_id": github_installation_id},
    )
    return token


def get_installation_info(github_installation_id: int) -> dict[str, Any]:
    """
    Fetches metadata about a GitHub App installation.

    Returns the raw GitHub API response dict which includes:
    - id, account (login, type, id), app_id, target_type, etc.
    """
    url = f"{GITHUB_API}/app/installations/{github_installation_id}"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=_app_headers())

    _raise_for_github_error(response, "get_installation_info")
    return response.json()


def list_installation_repositories(
    installation_token: str,
) -> list[GitHubAvailableRepo]:
    """
    Lists all repositories accessible through the given installation token.

    Handles GitHub's pagination automatically (up to 100 repos per page).
    Only returns repos the installation has been explicitly granted access to.
    """
    repos: list[GitHubAvailableRepo] = []
    page = 1
    per_page = 100

    with httpx.Client(timeout=30.0) as client:
        while True:
            url = (
                f"{GITHUB_API}/installation/repositories"
                f"?per_page={per_page}&page={page}"
            )
            response = client.get(url, headers=_installation_headers(installation_token))
            _raise_for_github_error(response, "list_installation_repositories")
            data = response.json()

            for repo in data.get("repositories", []):
                repos.append(
                    GitHubAvailableRepo(
                        github_repository_id=str(repo["id"]),
                        name=repo["name"],
                        full_name=repo["full_name"],
                        owner=repo["owner"]["login"],
                        visibility="private" if repo.get("private") else "public",
                        default_branch=repo.get("default_branch", "main"),
                        description=repo.get("description"),
                    )
                )

            # Stop if we've received all repositories.
            if len(data.get("repositories", [])) < per_page:
                break
            page += 1

    logger.info(
        "Repositories listed from GitHub installation",
        extra={"count": len(repos)},
    )
    return repos


def get_repository_metadata(
    installation_token: str,
    github_repository_id: str,
) -> dict[str, Any]:
    """
    Fetches full metadata for a specific repository by its GitHub numeric ID.

    Used when connecting a repository to ForgeAI to populate the Repository record.
    """
    url = f"{GITHUB_API}/repositories/{github_repository_id}"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=_installation_headers(installation_token))

    _raise_for_github_error(response, "get_repository_metadata")
    return response.json()


def build_app_installation_url(state: str) -> str:
    """
    Returns the GitHub URL that redirects a user to install the ForgeAI App.

    The ``state`` parameter is a signed token that encodes the org_id and
    prevents CSRF attacks during the OAuth callback.
    """
    return (
        f"https://github.com/apps/{settings.GITHUB_APP_NAME}/installations/new"
        f"?state={state}"
    )


def validate_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Validates the X-Hub-Signature-256 header on incoming GitHub webhooks.

    GitHub signs the raw request body with HMAC-SHA256 using the webhook secret.
    We compute the same signature and compare in constant time to prevent
    timing attacks.

    Returns True if the signature is valid, False otherwise.
    Always returns False if GITHUB_WEBHOOK_SECRET is not configured.
    """
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET not configured — rejecting all webhooks"
        )
        return False

    if not signature_header:
        return False

    # GitHub sends "sha256=<hex_digest>"
    if not signature_header.startswith("sha256="):
        return False

    expected_hex = signature_header[len("sha256="):]
    mac = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        msg=raw_body,
        digestmod=hashlib.sha256,
    )
    return hmac.compare_digest(mac.hexdigest(), expected_hex)
