"""Structured JSON logging with request-scoped context (structlog).

Why structlog: enterprise observability needs machine-parseable logs that carry
a ``trace_id`` / ``request_id`` through every log line so a single request can be
reconstructed across microservices.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog

# Request-scoped context shared across async tasks.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)


def _inject_context(_logger, _name, event_dict):
    """structlog processor: attach request/trace ids to every event."""
    if (rid := request_id_ctx.get()) is not None:
        event_dict["request_id"] = rid
    if (tid := trace_id_ctx.get()) is not None:
        event_dict["trace_id"] = tid
    return event_dict


def configure_logging(service_name: str, level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Bind the service name once so every line is attributable.
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
