"""Tool framework: schema + async executor, with a simple registry.

Each tool exposes an Anthropic-style JSON schema (``name`` / ``description`` /
``input_schema``) that is passed straight to the LLM for tool calling, plus an
async ``run`` that executes it. Decoupling schema from execution keeps tool
definitions declarative and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Execution context carried through a single agent run (tenant scoping, etc.).
ToolContext = dict[str, Any]
ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: ToolFn

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]


registry = ToolRegistry()
