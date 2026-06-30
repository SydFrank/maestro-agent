"""calculator tool — safe arithmetic evaluation.

Demonstrates a deterministic, side-effect-free tool. Uses an AST whitelist
instead of ``eval`` so the model can't smuggle arbitrary code through arguments.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from app.tools.base import Tool, ToolContext, registry

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


async def _run(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    expr = str(args["expression"])
    try:
        value = _eval(ast.parse(expr, mode="eval").body)
        return {"expression": expr, "value": value}
    except Exception as exc:  # surfaced back to the model as an observation
        return {"expression": expr, "error": f"无法计算: {exc}"}


registry.register(
    Tool(
        name="calculator",
        description="计算一个算术表达式，支持 + - * / ** %。用于精确数值计算。",
        input_schema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "如 (12.5 * 8) + 3"}
            },
            "required": ["expression"],
        },
        run=_run,
    )
)
