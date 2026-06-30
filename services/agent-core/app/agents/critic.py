"""Critic — the quality-gate agent.

Separating *generation* from *review* is the key reliability move in a
multi-agent design: the same model that wrote an answer is a poor judge of it,
so a dedicated Critic re-checks every outgoing answer for groundedness and
safety before it reaches the user. It can send the answer back for one revision
round if it fails — a cheap, bounded self-correction loop.
"""

from __future__ import annotations

import json
import re

from agent_common.logging import get_logger
from agent_common.schemas import (
    ChatMessage,
    Citation,
    LLMRequest,
    Role,
    TokenUsage,
)
from app.clients import llm_client
from app.guardrails import check_groundedness
from app.settings import settings

log = get_logger("critic")


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else None


async def review(
    *, question: str, answer: str, citations: list[Citation], used_rag: bool
) -> tuple[dict, TokenUsage]:
    """Return a verdict dict: {approved, score, issues, ...}."""
    # 1) cheap deterministic groundedness gate (no LLM cost)
    grounded = check_groundedness(answer, citations, used_rag=used_rag)
    if not grounded["grounded"]:
        return (
            {
                "approved": False,
                "method": "heuristic",
                "issues": grounded["reason"],
                "score": grounded["score"],
            },
            TokenUsage(),
        )

    # 2) LLM-as-judge for subtler issues (relevance, safety, overclaiming)
    system = (
        "你是答案审查员。判断给定答案是否：①直接回答了问题 ②没有编造未提供的事实 "
        "③无不当/越权内容。只输出 JSON："
        '{"approved": true/false, "issues": "若不通过，说明问题"}'
    )
    user = f"问题：{question}\n\n待审答案：{answer}"
    resp = await llm_client.complete(
        LLMRequest(
            messages=[
                ChatMessage(role=Role.system, content=system),
                ChatMessage(role=Role.user, content=user),
            ],
            model=settings.model,
            temperature=0.0,
            max_tokens=300,
        )
    )
    parsed = _extract_json(resp.content) or {"approved": True, "issues": ""}
    verdict = {
        "approved": bool(parsed.get("approved", True)),
        "method": "llm-judge",
        "issues": parsed.get("issues", ""),
        "score": grounded["score"],
    }
    log.info("critic_verdict", approved=verdict["approved"])
    return verdict, resp.usage
