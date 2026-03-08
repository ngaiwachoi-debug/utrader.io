"""
Logging utilities: trace IDs and structured logging configuration.
"""
import logging
import os
import sys
import uuid
import contextvars
from logging.handlers import RotatingFileHandler

_trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    """Return a unique trace ID (e.g. trace-123e4567-e89b-12d3-a456-426614174000)."""
    return "trace-" + str(uuid.uuid4())


def set_trace_id(trace_id: str) -> None:
    """Set the current trace ID (e.g. at start of a scheduler run)."""
    _trace_id_ctx.set(trace_id)


def get_trace_id() -> str | None:
    """Return the current trace ID, or None if not set."""
    return _trace_id_ctx.get(None)


def configure_logging() -> None:
    """Set up structured logging for production.

    - JSON-ish format with timestamp, level, logger, message
    - stdout for container/cloud environments
    - Optional rotating file handler (set LOG_FILE=path in env)
    - Log level controlled by LOG_LEVEL env (default INFO)
    """
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S%z"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    log_file = os.getenv("LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=5,
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )
