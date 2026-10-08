"""
security.py — JWT verification only.

The repository service does NOT issue tokens or hash passwords.
Those are responsibilities of the api (auth) service.

This module provides:
  - decode_access_token : validates a HS256 JWT issued by the api service
  - create_github_app_jwt : creates a RS256 JWT for authenticating AS the GitHub App
"""

import time
from jose import jwt, JWTError
from app.core.config import settings


def decode_access_token(token: str) -> str:
    """
    Decodes a HS256 JWT issued by the api service.

    Returns the ``sub`` claim (user_id as a string) on success.
    Raises ValueError on any failure so callers can convert to HTTP 401.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        subject = payload.get("sub")
        if subject is None:
            raise ValueError("Token does not contain a 'sub' claim")
        return subject
    except JWTError as exc:
        raise ValueError("Could not validate credentials") from exc


def create_github_app_jwt() -> str:
    """
    Creates a short-lived RS256 JWT for authenticating AS the GitHub App.

    This is different from user JWTs:
    - Algorithm: RS256 (signed with GitHub App private key)
    - Issuer: GITHUB_APP_ID
    - Expiry: 10 minutes (GitHub's maximum)

    The returned token is used to obtain installation access tokens.

    Raises RuntimeError if GITHUB_APP_PRIVATE_KEY or GITHUB_APP_ID is not configured.
    """
    if not settings.GITHUB_APP_PRIVATE_KEY or not settings.GITHUB_APP_ID:
        raise RuntimeError(
            "GITHUB_APP_PRIVATE_KEY and GITHUB_APP_ID must be configured "
            "before calling create_github_app_jwt()"
        )

    now = int(time.time())
    payload = {
        "iat": now - 60,      # issued 60s ago to account for clock skew
        "exp": now + (9 * 60),  # 9-minute expiry (GitHub max is 10)
        "iss": settings.GITHUB_APP_ID,
    }

    # GitHub App JWTs are signed with the App's RSA private key using RS256.
    private_key = settings.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")

    import jwt as pyjwt  # PyJWT — used for RS256 (python-jose RS256 needs extra deps)
    return pyjwt.encode(payload, private_key, algorithm="RS256")
