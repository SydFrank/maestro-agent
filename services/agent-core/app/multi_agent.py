"""The multi-agent orchestration graph (LangGraph).

Flow:
    guard → supervise ⇄ dispatch(workers, parallel) → synthesize → critic → END
                 └────────── bounded loop (max_supervisor_rounds) ──────┘
                 critic may request ONE revision round → supervise

Design decisions you should be able to defend in an interview:
  - Supervisor/worker topology (central routing) → predictable & traceable,
    unlike a free-for-all agent network.
  - Workers run in PARALLEL when independent (asyncio.gather) → latency win.
  - Two safety bounds (supervisor rounds + per-worker iterations) → no runaway.
  - Critic as a separate gate → generation/review separation for reliability.
  - Cost tiering: routing on a cheap model, synthesis/critic on the strong one.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_common.logging import get_logger
from agent_common.schemas import AgentStep, TokenUsage
from app.agents import supervisor as sup
from app.agents.roster import WORKERS
from app.guardrails import detect_prompt_injection
from app.settings import settings

log = get_logger("multi-agent")


def _merge_results(a: dict, b: dict) -> dict:
    return {**a, **b}


class MAState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    question: str
    ctx: dict[str, Any]
    prior_results: Annotated[dict[str, str], _merge_results]
    dispatch: list[str]
    rounds: int
    revisions: int
    steps: Annotated[list[AgentStep], lambda a, b: a + b]
    usage: TokenUsage
    answer: str
    critic: dict
    used_rag: bool
    blocked: bool


def _add_usage(state: MAState, usage: TokenUsage) -> None:
    cur = state.get("usage") or TokenUsage()
    cur.input_tokens += usage.input_tokens
    cur.output_tokens += usage.output_tokens
    cur.cost_usd = round(cur.cost_usd + usage.cost_usd, 6)
    state["usage"] = cur


async def guard_input(state: MAState) -> MAState:
    suspicious, pattern = detect_prompt_injection(state["question"])
    if suspicious:
        return {
            "blocked": True,
            "answer": "检测到可能的提示词注入，请求已被安全网关拦截。",
            "steps": [AgentStep(kind="final", name="guardrail",
                                content="prompt injection blocked", meta={"pattern": pattern})],
        }
    return {"blocked": False, "rounds": 0, "revisions": 0, "prior_results": {}}


async def supervise(state: MAState) -> MAState:
    decision, usage = await sup.route(state["question"], state.get("prior_results", {}))
    _add_usage(state, usage)
    return {
        "dispatch": decision.dispatch,
        "rounds": state.get("rounds", 0) + 1,
        "steps": [AgentStep(kind="plan", name="supervisor",
                            content=decision.reasoning or "路由决策",
                            meta={"dispatch": decision.dispatch, "done": decision.done})],
    }


async def dispatch_workers(state: MAState) -> MAState:
    """Run the chosen workers in parallel and collect their results."""
    names = [w for w in state.get("dispatch", []) if w in WORKERS]
    if not names:
        return {}

    async def _run(name: str):
        return await WORKERS[name].run(state["question"], state["ctx"])

    results = await asyncio.gather(*[_run(n) for n in names])

    new_results: dict[str, str] = {}
    steps: list[AgentStep] = []
    for r in results:
        new_results[r.name] = r.answer
        steps.extend(r.steps)
        _add_usage(state, r.usage)
    return {"prior_results": new_results, "steps": steps}


async def synthesize(state: MAState) -> MAState:
    answer, usage = await sup.synthesize(
        state["question"], state.get("prior_results", {}), state.get("tenant_id")
    )
    _add_usage(state, usage)
    return {"answer": answer,
            "steps": [AgentStep(kind="final", name="synthesize", content="整合各工人结论")]}


async def critic_review(state: MAState) -> MAState:
    """Coding critic = the objective test gate.

    The agent can't *claim* a fix — the only acceptable evidence is the sandbox
    test suite passing. If tests weren't run or didn't pass, the Critic rejects
    and the graph gets one bounded revision round to try again.
    """
    last_test = state["ctx"].get("_last_test")
    if last_test is None:
        verdict = {"approved": False, "method": "test-gate",
                   "passed": False, "issues": "尚未运行测试验证修复"}
    elif last_test.get("passed"):
        verdict = {"approved": True, "method": "test-gate",
                   "passed": True, "issues": ""}
    else:
        verdict = {"approved": False, "method": "test-gate",
                   "passed": False, "issues": "测试仍未通过，需继续修复"}
    return {
        "critic": verdict,
        "steps": [AgentStep(kind="final", name="critic",
                            content=("测试通过 ✓" if verdict["approved"]
                                     else f"未通过: {verdict['issues']}"),
                            meta=verdict)],
    }


# ---- routing ----
def _after_guard(state: MAState) -> str:
    return "blocked" if state.get("blocked") else "supervise"


def _after_supervise(state: MAState) -> str:
    if state.get("dispatch") and state.get("rounds", 0) <= settings.max_supervisor_rounds:
        return "dispatch"
    return "synthesize"  # no more work to dispatch, or budget hit


def _after_critic(state: MAState) -> str:
    verdict = state.get("critic", {})
    if not verdict.get("approved", True) and state.get("revisions", 0) < 1:
        state["revisions"] = state.get("revisions", 0) + 1
        return "revise"  # one bounded self-correction round
    return "done"


def build_multi_agent_graph():
    g = StateGraph(MAState)
    g.add_node("guard", guard_input)
    g.add_node("supervise", supervise)
    g.add_node("dispatch", dispatch_workers)
    g.add_node("synthesize", synthesize)
    g.add_node("critic", critic_review)

    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", _after_guard, {"blocked": END, "supervise": "supervise"})
    g.add_conditional_edges("supervise", _after_supervise,
                            {"dispatch": "dispatch", "synthesize": "synthesize"})
    g.add_edge("dispatch", "supervise")
    g.add_edge("synthesize", "critic")
    g.add_conditional_edges("critic", _after_critic, {"revise": "supervise", "done": END})
    return g.compile()


multi_agent_graph = build_multi_agent_graph()
