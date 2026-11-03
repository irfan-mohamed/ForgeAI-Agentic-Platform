"""
security.py — GitHub App JWT generation for the Worker Service.

The worker needs to generate installation access tokens to clone
private repositories from GitHub during synchronization.

This is identical in purpose to the repository service's security module
but is self-contained to avoid cross-service imports.
"""

import time

from app.core.config import settings


def create_github_app_jwt() -> str:
    """
    Creates a short-lived RS256 JWT for authenticating AS the GitHub App.

    Used to exchange for installation access tokens that allow the worker
    to clone or fetch files from private GitHub repositories.

    Private key resolution order:
      1. GITHUB_APP_PRIVATE_KEY_FILE — mounted PEM file (Docker preferred).
      2. GITHUB_APP_PRIVATE_KEY     — raw PEM string from env (local dev).

    Raises RuntimeError if neither is configured or GITHUB_APP_ID is missing.
    """
    if not settings.GITHUB_APP_ID:
        raise RuntimeError(
            "GITHUB_APP_ID must be configured before calling create_github_app_jwt()"
        )

    # ── Resolve the private key ───────────────────────────────────────────────
    if settings.GITHUB_APP_PRIVATE_KEY_FILE:
        try:
            with open(settings.GITHUB_APP_PRIVATE_KEY_FILE, "r") as f:
                private_key = f.read().strip()
        except OSError as exc:
            raise RuntimeError(
                f"Could not read GitHub App private key file "
                f"'{settings.GITHUB_APP_PRIVATE_KEY_FILE}': {exc}"
            )
    elif settings.GITHUB_APP_PRIVATE_KEY:
        private_key = settings.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
    else:
        raise RuntimeError(
            "Set either GITHUB_APP_PRIVATE_KEY_FILE (Docker) or "
            "GITHUB_APP_PRIVATE_KEY (local dev) to enable GitHub App auth."
        )

    now = int(time.time())
    payload = {
        "iat": now - 60,        # 60s in the past to account for clock skew
        "exp": now + (9 * 60),  # 9-minute expiry (GitHub max is 10)
        "iss": settings.GITHUB_APP_ID,
    }

    import jwt as pyjwt  # PyJWT — RS256 support
    return pyjwt.encode(payload, private_key, algorithm="RS256")
