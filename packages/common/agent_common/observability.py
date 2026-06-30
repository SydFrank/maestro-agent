"""FastAPI wiring shared by every service: request context, metrics, errors.

``create_app`` gives each microservice the same production-grade middleware in
one line: structured logging, a propagated ``X-Request-Id`` / ``trace_id``,
Prometheus metrics at ``/metrics``, a ``/healthz`` probe and uniform error
responses for ``AppError`` subclasses.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from agent_common.errors import AppError
from agent_common.logging import (
    configure_logging,
    get_logger,
    request_id_ctx,
    trace_id_ctx,
)

_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["service", "method", "path", "status"]
)
_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency", ["service", "path"]
)

log = get_logger("http")


def create_app(service_name: str, *, log_level: str = "INFO", **kwargs) -> FastAPI:
    configure_logging(service_name, log_level)
    app = FastAPI(title=service_name, **kwargs)

    @app.middleware("http")
    async def _context_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        trace_id = request.headers.get("X-Trace-Id", request_id)
        request_id_ctx.set(request_id)
        trace_id_ctx.set(trace_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except AppError as exc:  # handled, expected failures
            response = JSONResponse(status_code=exc.http_status, content=exc.to_dict())
            log.warning("app_error", code=exc.code, message=exc.message)
        except Exception:  # unexpected: log with stack, return generic 500
            log.exception("unhandled_error", path=request.url.path)
            response = JSONResponse(
                status_code=500,
                content={"code": "internal_error", "message": "internal server error"},
            )

        elapsed = time.perf_counter() - start
        path = request.url.path
        _REQUESTS.labels(service_name, request.method, path, response.status_code).inc()
        _LATENCY.labels(service_name, path).observe(elapsed)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        log.info(
            "request",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok", "service": service_name}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
