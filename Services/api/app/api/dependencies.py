import logging
from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User
from app.models.membership import Membership, MemberRole

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── User identity ─────────────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolves and returns the authenticated User from the JWT bearer token."""
    try:
        user_id = decode_access_token(token)
    except ValueError:
        logger.warning("Token validation failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id))
    if user is None:
        logger.warning("Token user not found", extra={"user_id": user_id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not active.",
        )

    return user


# ── Organization membership & RBAC ────────────────────────────────────────────

def get_org_membership(
    org_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    """
    Verifies the current user is an active member of the given organization.

    Used as a base dependency for all organization-scoped routes.
    Raises 403 if the user is not a member.
    """
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == current_user.id,
            Membership.organization_id == org_id,
            Membership.status == "active",
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization.",
        )

    return membership


def require_roles(*allowed_roles: MemberRole) -> Callable:
    """
    Factory that returns a FastAPI dependency enforcing role-based access.

    Usage in a route:
        @router.post("/sensitive")
        def sensitive_action(
            membership: Membership = Depends(require_roles(MemberRole.COMPANY_ADMIN, MemberRole.HR_ADMIN))
        ):
            ...
    """

    def _check_role(
        membership: Membership = Depends(get_org_membership),
    ) -> Membership:
        allowed = {r.value for r in allowed_roles}
        if membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires one of these roles: "
                    f"{', '.join(r.value for r in allowed_roles)}."
                ),
            )
        return membership

    return _check_role