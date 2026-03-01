"""
Trace ID for end-to-end visibility of deduction/cache/late fee/reconciliation flows.
Generate at start of each scheduler run; include in all related log lines.
"""
import uuid
import contextvars

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
