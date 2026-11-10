"""
repository_client.py — HTTP client for the Repository Service.

The Repository Service owns every GitHub call. When the AI Service needs pull
request data it asks the Repository Service and forwards the caller's JWT, so
the Repository Service performs its own membership check as well.

Expected response of GET /api/v1/repositories/{id}/pull-requests/{number}:
    {
      "number": 42, "title": "...", "body": "...", "state": "open",
      "author": "dev", "source_branch": "feat", "target_branch": "main",
      "head_sha": "abc...", "html_url": "https://github.com/...",
      "additions": 10, "deletions": 2, "changed_files": 3,
      "files": [{"filename": "...", "status": "modified",
                 "additions": 1, "deletions": 1, "patch": "@@ ..."}],
      "files_truncated": false
    }
"""
import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_pull_request(repository_id: int, number: int, token: str) -> dict:
    """Fetches one pull request (with changed files and patches)."""
    url = (
        f"{settings.REPOSITORY_SERVICE_URL.rstrip('/')}"
        f"/api/v1/repositories/{repository_id}/pull-requests/{number}"
    )
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        logger.error(
            "Repository service unreachable",
            extra={"url": url, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The repository service is unavailable. Please try again.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pull request not found.",
        )
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=response.status_code,
            detail="Not allowed to read this pull request.",
        )
    if response.is_error:
        logger.error(
            "Repository service error",
            extra={"status_code": response.status_code, "body": response.text[:300]},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to load the pull request from GitHub.",
        )

    return response.json()


# ── RepositoryClient class (Phase 4 Build Execution) ─────────────────────────

class RepositoryClient:
    """
    Object-oriented client for the Repository Service internal API.

    Used by the Phase 4 build execution graph to fetch a short-lived clone URL
    and open pull requests. Requests carry a JWT for the user who triggered the
    build so the Repository Service can enforce org membership and tenant
    isolation on every call.
    """

    def __init__(self, user_id: int | None = None):
        self._base = settings.REPOSITORY_SERVICE_URL.rstrip("/")
        self._user_id = user_id

    def _make_token(self) -> str:
        if not self._user_id:
            return ""
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        payload = {
            "sub": str(self._user_id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        return jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    def _headers(self) -> dict[str, str]:
        token = self._make_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_clone_info(self, org_id: int, repository_id: int) -> dict:
        """
        Fetch repository metadata plus a short-lived, token-embedded clone URL.
        Returns {} on failure.
        """
        url = (
            f"{self._base}/api/v1/internal/organizations/{org_id}"
            f"/repositories/{repository_id}/clone-info"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.get(url, headers=self._headers())
                if r.is_error:
                    logger.warning(
                        "get_clone_info failed: %s %s", r.status_code, r.text[:200]
                    )
                    return {}
                return r.json()
        except Exception as exc:
            logger.warning("get_clone_info exception: %s", exc)
            return {}

    def create_pull_request(
        self,
        org_id: int,
        repository_id: int,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        draft: bool = False,
    ) -> dict:
        """Ask the Repository Service to open a Pull Request. Returns {} on failure."""
        url = (
            f"{self._base}/api/v1/internal/organizations/{org_id}"
            f"/repositories/{repository_id}/pull-requests"
        )
        payload = {
            "head": head_branch,
            "base": base_branch,
            "title": title,
            "body": body,
            "draft": draft,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json=payload, headers=self._headers())
                if r.is_error:
                    logger.warning(
                        "create_pull_request failed: %s %s", r.status_code, r.text[:300]
                    )
                    return {}
                return r.json()
        except Exception as exc:
            logger.warning("create_pull_request exception: %s", exc)
            return {}

