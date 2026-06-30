"""Workspace + sandboxed execution for the coding agent.

This service owns the code workspace the agent operates on and runs its tests.
It ships with a SEED buggy project so the whole 定位→修复→跑测试 loop is
self-contained and demoable out of the box.

Isolation note (be honest in interviews):
  v1 runs tests via a resource-limited subprocess with a hard timeout — enough
  to demonstrate the loop. v2 upgrades to a per-task Docker container
  (`--network none`, memory/cpu/pids limits) for true isolation. The `run_tests`
  interface is designed so swapping the executor is transparent.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.settings import settings

WORKSPACE = Path(settings.workspace_dir)

# --- the seed buggy project --------------------------------------------------
# A tiny package with one planted bug and a failing test. The agent should
# locate calc.py, fix `*` -> `/`, and make the test pass.
_SEED: dict[str, str] = {
    "src/calc.py": (
        '"""Simple calculator utilities."""\n\n\n'
        "def divide(a: float, b: float) -> float:\n"
        "    # BUG: uses multiplication instead of division\n"
        "    return a * b\n\n\n"
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n"
    ),
    "tests/test_calc.py": (
        "from src.calc import divide, add\n\n\n"
        "def test_divide():\n"
        "    assert divide(6, 2) == 3\n\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    ),
    "src/__init__.py": "",
}


def reset_workspace() -> None:
    """(Re)create the workspace from the seed project."""
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for rel, content in _SEED.items():
        path = WORKSPACE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _safe_path(rel: str) -> Path:
    """Resolve a path and refuse anything escaping the workspace (path traversal)."""
    target = (WORKSPACE / rel).resolve()
    if not str(target).startswith(str(WORKSPACE.resolve())):
        raise ValueError("path escapes workspace")
    return target


def search(query: str, max_results: int = 25) -> list[dict]:
    """Plain substring search across the workspace (file:line:text)."""
    hits: list[dict] = []
    for path in WORKSPACE.rglob("*.py"):
        try:
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if query in line:
                    hits.append({
                        "path": str(path.relative_to(WORKSPACE)).replace("\\", "/"),
                        "line": i,
                        "text": line.strip()[:200],
                    })
                    if len(hits) >= max_results:
                        return hits
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def read_file(rel: str) -> dict:
    path = _safe_path(rel)
    if not path.is_file():
        return {"error": f"文件不存在: {rel}"}
    lines = path.read_text(encoding="utf-8").splitlines()
    numbered = "\n".join(f"{i:>4} | {ln}" for i, ln in enumerate(lines, 1))
    return {"path": rel, "content": numbered, "lines": len(lines)}


def edit_file(rel: str, old: str, new: str) -> dict:
    """Targeted search-replace edit (must match exactly once)."""
    path = _safe_path(rel)
    if not path.is_file():
        return {"error": f"文件不存在: {rel}"}
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        return {"error": "未找到要替换的内容（old 未匹配）"}
    if count > 1:
        return {"error": f"old 匹配到 {count} 处，需提供更精确的上下文以唯一定位"}
    path.write_text(text.replace(old, new), encoding="utf-8")
    return {"ok": True, "path": rel, "note": "已修改"}


def run_tests() -> dict:
    """Run pytest in the workspace (v1: subprocess + timeout)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header"],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=settings.run_timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "timed_out": True,
                "output": f"测试超过 {settings.run_timeout_s}s 被终止"}
    output = (proc.stdout + proc.stderr)[-4000:]  # cap output size
    return {"passed": proc.returncode == 0, "returncode": proc.returncode, "output": output}
