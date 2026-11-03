"""
github_service.py — GitHub API client for the Worker Service.

Responsibilities:
  - Generate installation access tokens (used to clone private repos)
  - Build authenticated clone URLs for git operations
  - Fetch repository tree (list of files) via GitHub API
  - Fetch individual file content via GitHub API

The Worker uses these tokens to:
  1. Clone the repository locally for file processing.
  2. Optionally use the REST API for file listing (for incremental syncs).

Authentication flow:
    GitHub App JWT (RS256)
        → POST /app/installations/{id}/access_tokens
        → Short-lived token (~1 hour)
        → Used as git clone password OR API Bearer token
"""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.security import create_github_app_jwt

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


def _check_response(response: httpx.Response, context: str) -> None:
    """Raises RuntimeError with detail if GitHub returned an error response."""
    if response.is_error:
        logger.error(
            "GitHub API error",
            extra={
                "context": context,
                "status_code": response.status_code,
                "body": response.text[:400],
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

    This token is used to:
      - Authenticate git clone operations (as HTTP basic auth password)
      - Make GitHub REST API calls on behalf of the installation

    Tokens expire in ~1 hour. We generate a fresh one per sync job.
    Raises RuntimeError on failure.
    """
    url = f"{GITHUB_API}/app/installations/{github_installation_id}/access_tokens"
    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, headers=_app_headers())

    _check_response(response, "get_installation_access_token")
    data = response.json()
    token = data.get("token")
    if not token:
        raise RuntimeError("GitHub did not return an access token in the response.")

    logger.info(
        "GitHub installation token obtained",
        extra={"github_installation_id": github_installation_id},
    )
    return token


def build_clone_url(token: str, full_name: str) -> str:
    """
    Builds an HTTPS clone URL with the installation token embedded.

    Format: https://x-access-token:{token}@github.com/{owner}/{repo}.git

    Git uses the token as the HTTP Basic Auth password, which GitHub accepts
    for installation tokens. This avoids SSH key management in the worker.
    """
    return f"https://x-access-token:{token}@github.com/{full_name}.git"


def get_repository_tree(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    recursive: bool = True,
) -> list[dict[str, Any]]:
    """
    Returns the full file tree of a repository using GitHub's Git Trees API.

    This is more efficient than listing the clone directory for large repos
    and allows incremental sync planning without cloning first.

    Returns a list of file objects:
        [{ "path": "src/foo.py", "type": "blob", "size": 1234, "sha": "..." }, ...]

    Only "blob" (file) entries are relevant; "tree" (directory) entries are filtered out.
    Raises RuntimeError on failure.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_installation_headers(token))

    _check_response(response, "get_repository_tree")
    data = response.json()

    if data.get("truncated"):
        logger.warning(
            "GitHub tree response was truncated — large repo, falling back to clone listing",
            extra={"owner": owner, "repo": repo, "branch": branch},
        )

    # Only return file blobs, not directory entries.
    return [
        item for item in data.get("tree", [])
        if item.get("type") == "blob"
    ]


def get_file_content(token: str, owner: str, repo: str, path: str, ref: str) -> str | None:
    """
    Fetches raw file content from the GitHub API for a specific file path.

    Returns decoded UTF-8 string, or None if the file is binary or cannot be decoded.
    Used as a fallback when a local clone is not available.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            url,
            headers={**_installation_headers(token), "Accept": "application/vnd.github.raw+json"},
        )

    if response.status_code == 404:
        return None

    _check_response(response, f"get_file_content:{path}")

    try:
        return response.text
    except Exception:
        return None


def get_latest_commit_sha(token: str, owner: str, repo: str, branch: str) -> str:
    """
    Returns the SHA of the latest commit on the given branch.

    Used to record which commit was indexed during a sync.
    Raises RuntimeError on failure.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/commits/{branch}"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=_installation_headers(token))

    _check_response(response, "get_latest_commit_sha")
    data = response.json()
    sha = data.get("sha")
    if not sha:
        raise RuntimeError(f"Could not retrieve commit SHA for {owner}/{repo}@{branch}")
    return sha
