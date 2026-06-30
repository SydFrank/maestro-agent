"""WorkerAgent — a focused, self-contained ReAct sub-agent.

A *worker* is the unit the Supervisor dispatches to. Each worker:
  - has its own persona (system prompt) and its own *subset* of tools,
  - runs a small, bounded ReAct loop on a single sub-task,
  - returns a structured result (answer + steps + any citations it gathered).

Why workers are isolated mini-agents (interview point):
  Giving every worker only the tools and context it needs keeps each agent's
  reasoning narrow and reliable, prevents one worker's failure from cascading,
  and bounds the token cost per worker — the three biggest risks of going
  multi-agent (context bloat / error propagation / cost blow-up).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agent_common.logging import get_logger
from agent_common.schemas import AgentStep, ChatMessage, LLMRequest, Role, TokenUsage
from app.clients import llm_client
from app.settings import settings
from app.tools.base import registry

log = get_logger("worker")


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


@dataclass
class WorkerResult:
    name: str
    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    success: bool = True


class WorkerAgent:
    def __init__(
        self,
        *,
        name: str,
        persona: str,
        tool_names: list[str],
        model: str | None = None,
        max_iterations: int = 4,
    ) -> None:
        self.name = name
        self.persona = persona
        self.tool_names = tool_names
        # Workers can run on a cheaper model than the final synthesis (cost tiering).
        self.model = model or settings.model
        self.max_iterations = max_iterations

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [
            t.schema()
            for n in self.tool_names
            if (t := registry.get(n)) is not None
        ]

    def _system_prompt(self) -> str:
        tools = "\n".join(
            f"- {s['name']}: {s['description']}" for s in self._tool_schemas()
        )
        return (
            f"{self.persona}\n"
            "按 ReAct 工作，每步只输出一个 JSON 对象：\n"
            '{"thought": "推理", "action": "工具名或final", "action_input": <对象或字符串>}\n'
            f"你可用的工具：\n{tools or '（无工具，直接基于已知信息作答）'}\n"
            "信息足够时 action 设为 final，action_input 为字符串答案。"
        )

    async def run(self, task: str, ctx: dict[str, Any]) -> WorkerResult:
        """Execute one sub-task and return a structured result."""
        messages = [
            ChatMessage(role=Role.system, content=self._system_prompt()),
            ChatMessage(role=Role.user, content=task),
        ]
        steps: list[AgentStep] = []
        usage = TokenUsage()

        for _ in range(self.max_iterations):
            resp = await llm_client.complete(
                LLMRequest(
                    messages=messages,
                    model=self.model,
                    temperature=0.1,
                    max_tokens=1000,
                    tenant_id=ctx.get("tenant_id"),
                )
            )
            usage.input_tokens += resp.usage.input_tokens
            usage.output_tokens += resp.usage.output_tokens
            usage.cost_usd = round(usage.cost_usd + resp.usage.cost_usd, 6)

            parsed = _extract_json(resp.content)
            if parsed is None:  # model broke protocol → treat as final answer
                steps.append(AgentStep(kind="final", name=self.name, content=resp.content))
                return WorkerResult(self.name, resp.content, steps, usage)

            thought = str(parsed.get("thought", ""))
            action = str(parsed.get("action", "final"))
            action_input = parsed.get("action_input", "")

            if action == "final":
                answer = (
                    action_input
                    if isinstance(action_input, str)
                    else json.dumps(action_input, ensure_ascii=False)
                )
                steps.append(AgentStep(kind="final", name=self.name, content=thought))
                return WorkerResult(self.name, answer, steps, usage)

            # ---- execute the chosen tool ----
            steps.append(
                AgentStep(kind="tool_call", name=action, content=thought,
                          meta={"worker": self.name, "input": action_input})
            )
            tool = registry.get(action)
            if tool is None or action not in self.tool_names:
                observation = {"error": f"工人 {self.name} 无权使用工具 {action}"}
            else:
                args = action_input if isinstance(action_input, dict) else {"input": action_input}
                try:
                    observation = await tool.run(args, ctx)
                except Exception as exc:
                    observation = {"error": f"工具失败: {exc}"}

            obs_text = json.dumps(observation, ensure_ascii=False)
            steps.append(AgentStep(kind="tool_result", name=action, content=obs_text,
                                   meta={"worker": self.name}))
            messages.append(ChatMessage(role=Role.assistant, content=json.dumps(parsed, ensure_ascii=False)))
            messages.append(ChatMessage(role=Role.user, content=f"工具 {action} 观察结果: {obs_text}"))

        # Hit the iteration bound — return best effort.
        log.warning("worker_max_iters", worker=self.name)
        return WorkerResult(
            self.name, "（该子任务未在步数预算内完成）", steps, usage, success=False
        )
