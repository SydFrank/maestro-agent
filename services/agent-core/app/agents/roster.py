"""自动 Bug 修复 Agent 的专职工人花名册（coding 编制）。

工人按**能力域**切分，每个是 Supervisor 能清晰推理的"专家"。加能力 = 加一条
记录，编排图无需改动。

修复一个 bug 的典型协作：
  Coder 定位并改 → Tester 跑测试 → 没过则 Fixer 再改 → Tester 复测 → Reviewer 审查
Supervisor 按工人返回的结果决定下一步派谁（顺序、可循环，受 max_supervisor_rounds 约束）。

关键设计：测试是唯一的"对错裁判"（run_tests）。Agent 不能"声称"修好了，
必须让沙箱里的测试真的通过——这从根上压制了幻觉。
"""

from __future__ import annotations

from app.agents.worker import WorkerAgent

# Coder：定位 bug 并提出修复。能搜、能读、能改。
CODER = WorkerAgent(
    name="coder",
    persona=(
        "你是资深工程师，负责定位并修复 bug。流程：先用 search_code/read_file 找到"
        "相关代码和根因，再用 edit_code 做最小化修改。改完简述你改了什么、为什么。"
        "不要臆测，一切基于你读到的真实代码。"
    ),
    tool_names=["search_code", "read_file", "edit_code"],
    max_iterations=8,
)

# Tester：在沙箱跑测试，给出客观结果。只读 + 执行，不改代码。
TESTER = WorkerAgent(
    name="tester",
    persona=(
        "你是测试工程师。职责：用 run_tests 在沙箱运行测试套件，如实汇报通过与否"
        "及失败信息。必要时用 read_file 查看测试。你不修改业务代码。"
    ),
    tool_names=["run_tests", "read_file"],
    max_iterations=3,
)

# Fixer：测试仍失败时，结合失败信息再次修复。
FIXER = WorkerAgent(
    name="fixer",
    persona=(
        "你是调试专家。当测试仍然失败时介入：阅读失败输出和相关代码，找出上一次"
        "修复为何不奏效，用 edit_code 做针对性修正。基于真实报错，不要瞎猜。"
    ),
    tool_names=["search_code", "read_file", "edit_code", "run_tests"],
    max_iterations=8,
)

# Reviewer：审查最终改动的质量与副作用（只读）。
REVIEWER = WorkerAgent(
    name="reviewer",
    persona=(
        "你是代码评审者。职责：用 read_file 查看最终改动，评估修复是否合理、是否引入"
        "副作用或破坏其他功能、是否符合最小改动原则。只读，给出评审意见。"
    ),
    tool_names=["read_file", "search_code"],
    max_iterations=4,
)

WORKERS: dict[str, WorkerAgent] = {
    CODER.name: CODER,
    TESTER.name: TESTER,
    FIXER.name: FIXER,
    REVIEWER.name: REVIEWER,
}

WORKER_CATALOG = {
    "coder": "定位 bug 根因并提出修复（搜索/读取/修改代码）",
    "tester": "在沙箱运行测试，客观判断当前代码是否通过",
    "fixer": "测试仍失败时，结合报错做针对性再修复",
    "reviewer": "审查最终改动的质量与副作用（只读）",
}
