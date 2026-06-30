"""Importing this package registers all tools as a side effect."""

from app.tools import calculator, knowledge, order  # noqa: F401
from app.tools.base import registry

__all__ = ["registry"]
