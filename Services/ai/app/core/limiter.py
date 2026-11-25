"""
Rate limiter singleton shared across all route modules.

Defined here (not in main.py) to avoid circular imports:
  main.py → api_router → routes/messages.py → main.py  (cycle!)

Usage in a route:
    from app.core.limiter import limiter
    @limiter.limit("20/minute")
    def my_route(request: Request, ...): ...
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    enabled=settings.RATE_LIMIT_ENABLED,
)
