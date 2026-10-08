import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique ID to every HTTP request and emits structured
    request/response log lines at INFO level.

    - Reads ``X-Request-ID`` from incoming headers (allows client correlation)
      or generates a fresh UUID4.
    - Exposes the ID via ``request.state.request_id``.
    - Sets ``request_id_var`` context variable so every log line during
      this request is automatically tagged with the ID.
    - Echoes the ID back in the ``X-Request-ID`` response header.
    - Logs request start and response with elapsed_ms.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            logger.info(
                "request started",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                },
            )
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request completed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                },
            )
            return response
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "elapsed_ms": elapsed_ms,
                },
            )
            raise
        finally:
            request_id_var.reset(token)
