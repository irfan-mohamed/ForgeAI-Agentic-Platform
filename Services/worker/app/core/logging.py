import json
import logging
import sys
from contextvars import ContextVar

# Tracks current job/event context across async tasks.
job_id_var: ContextVar[str] = ContextVar("job_id", default="-")
event_var: ContextVar[str] = ContextVar("event", default="-")


class _JSONFormatter(logging.Formatter):
    """
    Emits one JSON object per log line.
    Matches the JSON logging format used by the Repository Service
    for consistent log parsing across the platform.
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
            "job_id": job_id_var.get(),
            "event": event_var.get(),
        }

        for key, val in vars(record).items():
            if key not in self._SKIP:
                payload[key] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with JSON output to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy external library loggers.
    for noisy in ("aiokafka", "git", "httpx", "openai", "qdrant_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
