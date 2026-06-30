"""Supervisor — the orchestrator brain of the multi-agent system.

It does three things, and *only* these three (keeping it light so it never
becomes the bottleneck):
  1. route    : look at the question + what's known so far, decide which
                worker(s) to dispatch next — or that we're done.
  2. (workers run — handled by the graph, possibly in parallel)
  3. synthesize: fuse the workers' results into one grounded final answer.

Routing is a *structured* decision (validated by Pydantic) so it's auditable
and testable — you can unit-test "this question routes to knowledge" without
running the whole system.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from agent_common.logging import get_logger
from agent_common.schemas import ChatMessage, LLMRequest, Role, TokenUsage
from app.agents.roster import WORKER_CATALOG
from app.clients import llm_client
from app.settings import settings

log = get_logger("supervisor")


class RouteDecision(BaseModel):
    reasoning: str = ""
    # Workers to dispatch this round (parallel if more than one). Empty = done.
    dispatch: list[str] = Field(default_factory=list)
    done: bool = False


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else None


def _catalog_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in WORKER_CATALOG.items())


async def route(question: str, prior_results: dict[str, str]) -> tuple[RouteDecision, TokenUsage]:
    """Decide which workers to dispatch next (or stop)."""
    known = (
        "\n".join(f"[{k} 已完成]: {v}" for k, v in prior_results.items())
        if prior_results
        else "（还没有任何工人结果）"
    )
    system = (
        "你是多 Agent 系统的编排者(Supervisor)。根据用户问题和已有结果，决定下一步"
        "派哪些专职工人去做，或判断信息已足够、可以收尾。\n"
        f"可用工人：\n{_catalog_text()}\n"
        "只输出一个 JSON：{\"reasoning\": \"\", \"dispatch\": [\"工人名\", ...], \"done\": false}\n"
        "- 可同时派多个相互独立的工人（它们会并行执行）。\n"
        "- 已有结果足够回答时，dispatch 为空、done 设为 true。\n"
        "- 不要重复派已经完成且结果可用的工人。"
    )
    user = f"用户问题：{question}\n\n当前已知：\n{known}"

    resp = await llm_client.complete(
        LLMRequest(
            messages=[
                ChatMessage(role=Role.system, content=system),
                ChatMessage(role=Role.user, content=user),
            ],
            # Routing is a cheap decision → run it on a cheaper model (cost tiering).
            model=settings.supervisor_model,
            temperature=0.0,
            max_tokens=400,
        )
    )
    parsed = _extract_json(resp.content) or {"dispatch": [], "done": True}
    try:
        decision = RouteDecision.model_validate(parsed)
    except Exception:
        decision = RouteDecision(dispatch=[], done=True)
    # Guard: only keep known workers.
    decision.dispatch = [w for w in decision.dispatch if w in WORKER_CATALOG]
    log.info("route", dispatch=decision.dispatch, done=decision.done)
    return decision, resp.usage


async def synthesize(question: str, results: dict[str, str], tenant_id: str | None) -> tuple[str, TokenUsage]:
    """Fuse worker outputs into one final, grounded answer."""
    joined = "\n\n".join(f"【{k} 的结论】\n{v}" for k, v in results.items())
    system = (
        "你是编排者，负责把各专职工人的结论整合成给用户的最终答案。"
        "要求：综合所有结论、保留来源引用标注、若工人间矛盾则指出并按可信度取舍、"
        "信息不足时如实说明。用中文简洁作答。"
    )
    resp = await llm_client.complete(
        LLMRequest(
            messages=[
                ChatMessage(role=Role.system, content=system),
                ChatMessage(role=Role.user, content=f"用户问题：{question}\n\n各工人结论：\n{joined}"),
            ],
            model=settings.model,  # final answer uses the strong model
            temperature=0.2,
            max_tokens=1200,
            tenant_id=tenant_id,
        )
    )
    return resp.content, resp.usage
