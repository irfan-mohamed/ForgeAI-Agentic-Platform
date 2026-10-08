"""
dependencies.py — FastAPI dependency functions for the Repository Service.

Provides:
  - get_current_user_id : decodes JWT → user_id (int)
  - get_org_membership  : verifies user is an active member of the org
                          by reading the memberships table directly

Design note:
  The memberships table is owned by the api service but lives in the same
  shared PostgreSQL instance. We read it as a read-only cross-service query.
  This avoids an inter-service HTTP call for every request.
"""

import logging
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db

logger = logging.getLogger(__name__)

# Points clients to the api service login endpoint for token acquisition.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8000/api/v1/auth/login")


# ── User Identity ─────────────────────────────────────────────────────────────

def get_current_user_id(
    token: str = Depends(oauth2_scheme),
) -> int:
    """
    Decodes the HS256 JWT issued by the api service.

    Returns the user_id (int) extracted from the 'sub' claim.
    Raises HTTP 401 if the token is invalid or expired.
    """
    try:
        user_id_str = decode_access_token(token)
        return int(user_id_str)
    except (ValueError, TypeError):
        logger.warning("Token validation failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Organization Membership ───────────────────────────────────────────────────

def _check_membership(user_id: int, org_id: int, db: Session) -> None:
    """
    Reads the memberships table (owned by api service) to verify that
    the user is an active member of the organization.

    Raises HTTP 403 if the user is not a member.
    """
    # Raw SQL query to avoid importing api service models into this service.
    result = db.execute(
        text(
            "SELECT id FROM memberships "
            "WHERE user_id = :user_id "
            "  AND organization_id = :org_id "
            "  AND status = 'active' "
            "LIMIT 1"
        ),
        {"user_id": user_id, "org_id": org_id},
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization.",
        )


def get_org_membership(
    org_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> int:
    """
    Dependency that verifies the current user is an active member of ``org_id``.

    Returns ``user_id`` so callers can use it without re-fetching.
    Raises HTTP 403 if the user is not a member.

    Usage in a route:
        @router.get("/{org_id}/repositories")
        def list_repositories(
            org_id: int,
            user_id: int = Depends(get_org_membership),
            db: Session = Depends(get_db),
        ):
            ...
    """
    _check_membership(user_id, org_id, db)
    return user_id


def require_org_membership(org_id_param: str = "org_id") -> Callable:
    """
    Factory that creates a dependency verifying org membership.
    Useful when the org_id comes from a path parameter with a custom name.
    """
    def _dependency(
        org_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
    ) -> int:
        _check_membership(user_id, org_id, db)
        return user_id

    return _dependency
