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
