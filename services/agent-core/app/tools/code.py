"""Code tools — the coding agent's hands on the workspace.

Read tools (search_code / read_file) locate the bug; write tool (edit_code)
changes it; run_tests is the ground-truth oracle that says whether the fix
actually works. Letting tests be the oracle is what keeps the agent honest —
it can't "claim" a fix; the sandbox proves it.
"""

from __future__ import annotations

from typing import Any

from app.clients import sandbox_client
from app.tools.base import Tool, ToolContext, registry


async def _search_code(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return await sandbox_client.search(str(args["query"]), int(args.get("max_results", 25)))


async def _read_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return await sandbox_client.read_file(str(args["path"]))


async def _edit_code(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return await sandbox_client.edit_file(
        str(args["path"]), str(args["old"]), str(args["new"])
    )


async def _run_tests(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    result = await sandbox_client.run_tests()
    # Record the latest test verdict so the graph/Critic can gate on real results.
    ctx["_last_test"] = {"passed": result.get("passed", False)}
    return result


registry.register(Tool(
    name="search_code",
    description="在代码仓库中按关键词搜索，返回匹配的 文件:行:内容，用于定位相关代码。",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜索词，如函数名/变量名/报错信息"}},
        "required": ["query"],
    },
    run=_search_code,
))

registry.register(Tool(
    name="read_file",
    description="读取仓库中某个文件的内容（带行号），用于查看代码细节。",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "相对路径，如 src/calc.py"}},
        "required": ["path"],
    },
    run=_read_file,
))

registry.register(Tool(
    name="edit_code",
    description=(
        "对文件做精确的查找-替换修改。old 必须在文件中唯一匹配，否则会报错——"
        "请带足够上下文保证唯一定位。这是有副作用的操作。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要修改的文件相对路径"},
            "old": {"type": "string", "description": "要被替换的原始代码片段（需唯一）"},
            "new": {"type": "string", "description": "替换后的新代码"},
        },
        "required": ["path", "old", "new"],
    },
    run=_edit_code,
))

registry.register(Tool(
    name="run_tests",
    description="在沙箱里运行仓库的测试套件，返回是否通过及输出。这是判断修复是否成功的唯一标准。",
    input_schema={"type": "object", "properties": {}},
    run=_run_tests,
))
