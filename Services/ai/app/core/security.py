"""
JWT authentication dependency — shared secret with the API service.

The API service issues JWT tokens on login.
The AI service validates those same tokens using the shared SECRET_KEY.
No separate user store is needed here.

The token only identifies the user (``sub`` claim). It carries no organization
claim, so organization membership is always checked against the database —
see ``app.core.access``.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

_bearer = HTTPBearer(auto_error=True)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Returns the decoded JWT payload (``sub`` and ``exp``)."""
    return _decode_token(credentials.credentials)


def get_user_id(current_user: Annotated[dict, Depends(get_current_user)]) -> int:
    """Returns the authenticated user's numeric ID from the ``sub`` claim."""
    try:
        return int(current_user["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    """
    Returns the raw JWT so it can be forwarded to the Repository Service.

    The token is validated by ``get_user_id`` in the same request; this
    dependency only exposes the string.
    """
    return credentials.credentials


CurrentUser = Annotated[dict, Depends(get_current_user)]
UserId = Annotated[int, Depends(get_user_id)]
BearerToken = Annotated[str, Depends(get_bearer_token)]


def decode_token(token: str) -> dict:
    """Public alias for use outside FastAPI dependency injection (e.g. SSE query-param auth)."""
    return _decode_token(token)
