"""Typed application errors mapped to HTTP responses.

Reliable, traceable error handling is an explicit JD requirement: every failure
has a stable ``code`` the frontend can branch on and that shows up in logs.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected (handled) application errors."""

    code: str = "app_error"
    http_status: int = 500

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class AuthError(AppError):
    code = "auth_error"
    http_status = 401


class PermissionError_(AppError):  # noqa: N801 - avoid shadowing builtin
    code = "permission_denied"
    http_status = 403


class GuardrailError(AppError):
    """Raised when input/output fails a safety guardrail (e.g. prompt injection)."""

    code = "guardrail_blocked"
    http_status = 400


class UpstreamError(AppError):
    """An upstream dependency (LLM provider, another service) failed."""

    code = "upstream_error"
    http_status = 502


class RateLimitError(AppError):
    code = "rate_limited"
    http_status = 429
