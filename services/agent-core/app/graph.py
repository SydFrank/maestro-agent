"""The agent's reasoning graph (LangGraph StateGraph).

Flow:  guard_input → plan → [reason ⇄ act]* → finalize

- guard_input : prompt-injection gate (blocks malicious input early)
- plan        : one-shot task decomposition into a short plan
- reason      : ReAct step — the model emits a *structured* JSON action
                (validated by Pydantic) choosing a tool or the final answer
- act         : execute the chosen tool, feed the observation back
- finalize    : groundedness check + assemble the response

The loop is bounded by ``max_tool_iterations`` so a misbehaving model can never
spin forever — reliability is an explicit JD requirement.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

from agent_common.logging import get_logger
from agent_common.schemas import (
    AgentStep,
    ChatMessage,
    Citation,
    LLMRequest,
    Role,
    TokenUsage,
)
from app.clients import llm_client
from app.guardrails import check_groundedness, detect_prompt_injection
from app.settings import settings
from app.tools import registry

log = get_logger("graph")


# --- structured action the model must emit each reasoning step --------------
class AgentAction(BaseModel):
    thought: str
    action: str  # a tool name or "final"
    action_input: dict[str, Any] | str = ""


class GraphState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    conversation_id: str
    question: str
    history: list[ChatMessage]
    scratchpad: list[ChatMessage]  # reasoning trace fed back to the model
    steps: Annotated[list[AgentStep], lambda a, b: a + b]
    iterations: int
    used_rag: bool
    ctx: dict[str, Any]
    usage: TokenUsage
    answer: str
    blocked: bool


def _system_prompt() -> str:
    tool_docs = "\n".join(
        f"- {t['name']}: {t['description']} 入参 schema: {json.dumps(t['input_schema'], ensure_ascii=False)}"
        for t in registry.schemas()
    )
    return (
        "你是一个企业级智能助手，擅长用工具检索企业知识库并严谨作答。\n"
        "你必须按 ReAct 方式工作：每一步只输出一个 JSON 对象，不要输出多余文字。\n"
        "JSON 格式：{\"thought\": \"你的简短推理\", \"action\": \"工具名或final\", "
        "\"action_input\": <对象或字符串>}\n"
        f"可用工具：\n{tool_docs}\n"
        "- 当需要依据企业资料回答时，先用 knowledge_search 检索。\n"
        "- 当已经掌握足够信息时，action 设为 \"final\"，action_input 为字符串形式的最终答案。\n"
        "- 最终答案要基于检索到的资料，并在结尾用[来源N]标注引用；资料不足时如实说明，不要编造。"
    )


def _accumulate_usage(state: GraphState, usage: TokenUsage) -> None:
    cur = state.get("usage") or TokenUsage()
    cur.input_tokens += usage.input_tokens
    cur.output_tokens += usage.output_tokens
    cur.cost_usd = round(cur.cost_usd + usage.cost_usd, 6)
    state["usage"] = cur


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


# --- nodes -----------------------------------------------------------------
async def guard_input(state: GraphState) -> GraphState:
    suspicious, pattern = detect_prompt_injection(state["question"])
    if suspicious:
        log.warning("prompt_injection_blocked", pattern=pattern)
        return {
            "blocked": True,
            "answer": "检测到可能的提示词注入，请求已被安全网关拦截。",
            "steps": [
                AgentStep(
                    kind="final",
                    name="guardrail",
                    content="prompt injection blocked",
                    meta={"pattern": pattern},
                )
            ],
        }
    return {"blocked": False}


async def plan(state: GraphState) -> GraphState:
    messages = [
        ChatMessage(
            role=Role.system,
            content="将用户问题拆解为 1-3 步的简短计划，只列要点，不要回答问题本身。",
        ),
        ChatMessage(role=Role.user, content=state["question"]),
    ]
    resp = await llm_client.complete(
        LLMRequest(messages=messages, model=settings.model, max_tokens=300,
                   tenant_id=state["tenant_id"])
    )
    _accumulate_usage(state, resp.usage)
    return {
        "scratchpad": [],
        "iterations": 0,
        "used_rag": False,
        "steps": [AgentStep(kind="plan", name="planner", content=resp.content)],
    }


async def reason(state: GraphState) -> GraphState:
    messages: list[ChatMessage] = [ChatMessage(role=Role.system, content=_system_prompt())]
    messages += state.get("history", [])
    messages.append(ChatMessage(role=Role.user, content=state["question"]))
    messages += state.get("scratchpad", [])

    resp = await llm_client.complete(
        LLMRequest(messages=messages, model=settings.model, max_tokens=1200,
                   temperature=0.1, tenant_id=state["tenant_id"])
    )
    _accumulate_usage(state, resp.usage)

    parsed = _extract_json(resp.content)
    if parsed is None:
        # Model didn't follow the protocol — treat its text as the final answer.
        return {
            "answer": resp.content,
            "steps": [AgentStep(kind="final", name="reason", content=resp.content)],
            "scratchpad": state.get("scratchpad", [])
            + [ChatMessage(role=Role.assistant, content=resp.content)],
            "_decision": "final",  # type: ignore[typeddict-unknown-key]
        }
    try:
        action = AgentAction.model_validate(parsed)
    except ValidationError:
        return {
            "answer": resp.content,
            "steps": [AgentStep(kind="final", name="reason", content=resp.content)],
            "_decision": "final",  # type: ignore[typeddict-unknown-key]
        }

    scratch = state.get("scratchpad", []) + [
        ChatMessage(role=Role.assistant, content=json.dumps(parsed, ensure_ascii=False))
    ]

    if action.action == "final":
        answer = action.action_input if isinstance(action.action_input, str) else json.dumps(
            action.action_input, ensure_ascii=False
        )
        return {
            "answer": answer,
            "scratchpad": scratch,
            "steps": [AgentStep(kind="final", name="reason", content=action.thought)],
            "_decision": "final",  # type: ignore[typeddict-unknown-key]
        }

    return {
        "scratchpad": scratch,
        "_pending_action": action.model_dump(),  # type: ignore[typeddict-unknown-key]
        "steps": [
            AgentStep(
                kind="tool_call",
                name=action.action,
                content=action.thought,
                meta={"input": action.action_input},
            )
        ],
        "_decision": "act",  # type: ignore[typeddict-unknown-key]
    }


async def act(state: GraphState) -> GraphState:
    action = state["_pending_action"]  # type: ignore[typeddict-item]
    name = action["action"]
    raw_input = action.get("action_input") or {}
    args = raw_input if isinstance(raw_input, dict) else {"input": raw_input}

    tool = registry.get(name)
    iterations = state.get("iterations", 0) + 1
    used_rag = state.get("used_rag", False) or name == "knowledge_search"

    if tool is None:
        observation = {"error": f"未知工具: {name}"}
    else:
        try:
            observation = await tool.run(args, state["ctx"])
        except Exception as exc:  # tool failure becomes an observation, not a crash
            log.warning("tool_error", tool=name, error=str(exc))
            observation = {"error": f"工具执行失败: {exc}"}

    obs_text = json.dumps(observation, ensure_ascii=False)
    scratch = state.get("scratchpad", []) + [
        ChatMessage(role=Role.user, content=f"工具 {name} 的观察结果: {obs_text}")
    ]
    return {
        "iterations": iterations,
        "used_rag": used_rag,
        "scratchpad": scratch,
        "steps": [AgentStep(kind="tool_result", name=name, content=obs_text)],
    }


async def finalize(state: GraphState) -> GraphState:
    citations = [Citation.model_validate(c) for c in state["ctx"].get("_citations", [])]
    # de-duplicate by chunk_id, keep highest score
    dedup: dict[str, Citation] = {}
    for c in citations:
        if c.chunk_id not in dedup or c.score > dedup[c.chunk_id].score:
            dedup[c.chunk_id] = c
    citations = sorted(dedup.values(), key=lambda c: c.score, reverse=True)

    grounded = check_groundedness(
        state.get("answer", ""), citations, used_rag=state.get("used_rag", False)
    )
    return {
        "ctx": {**state["ctx"], "_final_citations": [c.model_dump() for c in citations]},
        "steps": [
            AgentStep(
                kind="final",
                name="groundedness",
                content=grounded["reason"],
                meta=grounded,
            )
        ],
    }


# --- routing ---------------------------------------------------------------
def _after_guard(state: GraphState) -> str:
    return "blocked" if state.get("blocked") else "plan"


def _after_reason(state: GraphState) -> str:
    decision = state.get("_decision")  # type: ignore[typeddict-item]
    if decision == "final":
        return "finalize"
    if state.get("iterations", 0) >= settings.max_tool_iterations:
        return "finalize"  # safety bound hit
    return "act"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("guard_input", guard_input)
    g.add_node("plan", plan)
    g.add_node("reason", reason)
    g.add_node("act", act)
    g.add_node("finalize", finalize)

    g.add_edge(START, "guard_input")
    g.add_conditional_edges(
        "guard_input", _after_guard, {"blocked": END, "plan": "plan"}
    )
    g.add_edge("plan", "reason")
    g.add_conditional_edges(
        "reason", _after_reason, {"act": "act", "finalize": "finalize"}
    )
    g.add_edge("act", "reason")
    g.add_edge("finalize", END)
    return g.compile()


agent_graph = build_graph()
