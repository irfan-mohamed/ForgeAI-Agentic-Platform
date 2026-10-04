import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique ID to every HTTP request.

    1. Reads ``X-Request-ID`` from the incoming headers (lets clients correlate
       retries) or generates a fresh UUID.
    2. Exposes the ID on ``request.state.request_id`` for use in route handlers.
    3. Sets ``request_id_var`` context variable so every log line emitted during
       this request is automatically tagged with the ID.
    4. Echoes the ID back in the ``X-Request-ID`` response header so clients
       (and the frontend) can include it in bug reports.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        token = request_id_var.set(request_id)
        try:
            logger.debug("→ %s %s", request.method, request.url.path)
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.debug(
                "← %s %s [%d]",
                request.method,
                request.url.path,
                response.status_code,
            )
            return response
        finally:
            request_id_var.reset(token)
