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

    Private key resolution order:
      1. GITHUB_APP_PRIVATE_KEY_FILE — path to a mounted PEM file (Docker).
      2. GITHUB_APP_PRIVATE_KEY     — raw PEM string from env var (local dev).

    Raises RuntimeError if neither is configured or GITHUB_APP_ID is missing.
    """
    if not settings.GITHUB_APP_ID:
        raise RuntimeError(
            "GITHUB_APP_ID must be configured before calling create_github_app_jwt()"
        )

    # ── Resolve the private key ───────────────────────────────────────────────
    if settings.GITHUB_APP_PRIVATE_KEY_FILE:
        # Docker: PEM file mounted at a path — read it directly.
        # This is the preferred approach because Docker Compose env_file cannot
        # handle multi-line RSA keys (the parser treats each line as KEY=VALUE).
        try:
            with open(settings.GITHUB_APP_PRIVATE_KEY_FILE, "r") as f:
                private_key = f.read().strip()
        except OSError as exc:
            raise RuntimeError(
                f"Could not read GitHub App private key file "
                f"'{settings.GITHUB_APP_PRIVATE_KEY_FILE}': {exc}"
            )
    elif settings.GITHUB_APP_PRIVATE_KEY:
        # Local dev: PEM stored as an env var string.
        # Replace literal \n sequences that may have been introduced by the shell.
        private_key = settings.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
    else:
        raise RuntimeError(
            "Set either GITHUB_APP_PRIVATE_KEY_FILE (Docker) or "
            "GITHUB_APP_PRIVATE_KEY (local dev) to enable GitHub App auth."
        )

    now = int(time.time())
    payload = {
        "iat": now - 60,       # issued 60s ago to account for clock skew
        "exp": now + (9 * 60), # 9-minute expiry (GitHub max is 10)
        "iss": settings.GITHUB_APP_ID,
    }

    import jwt as pyjwt  # PyJWT — used for RS256 (python-jose RS256 needs extra deps)
    return pyjwt.encode(payload, private_key, algorithm="RS256")

