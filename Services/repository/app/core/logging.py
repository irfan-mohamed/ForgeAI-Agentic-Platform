import json
import logging
import sys
from contextvars import ContextVar

# Shared context variable — set by RequestIDMiddleware on each request.
# Readable from anywhere in the call stack during that request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JSONFormatter(logging.Formatter):
    """
    Emits one JSON object per log line.

    Fields included:
    - level      : log level name
    - message    : the formatted message
    - logger     : logger name (module path)
    - request_id : current request ID from context
    - extras     : any extra kwargs passed to the logger (e.g. repo_id)
    """

    _SKIP = frozenset(
        {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        payload: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "request_id": request_id_var.get(),
        }

        for key, val in vars(record).items():
            if key not in self._SKIP:
                payload[key] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure root logger with JSON output to stdout.

    Silences uvicorn's own handlers so they don't double-emit log lines
    alongside our JSON formatter.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
