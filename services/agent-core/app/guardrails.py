"""Safety guardrails: prompt-injection detection + groundedness check.

These are deliberately fast, deterministic heuristics that run on every request
(an LLM-based judge can be layered on top in ``evals/``). They map directly to
the JD requirements 幻觉治理 + Prompt Injection 防护.
"""

from __future__ import annotations

import re

from agent_common.schemas import Citation

# --- Prompt-injection patterns (input guard) -------------------------------
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
    r"disregard\s+(the\s+)?(system|previous)\s+",
    r"忽略(以上|之前|前面).{0,4}(指令|提示|要求)",
    r"你现在是|从现在起你是|forget\s+you\s+are",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions)",
    r"(打印|输出|告诉我).{0,6}(系统提示|system prompt|你的指令)",
    r"developer\s+mode|jailbreak|DAN\s+mode",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    """Return (is_suspicious, matched_pattern)."""
    m = _INJECTION_RE.search(text or "")
    return (True, m.group(0)) if m else (False, None)


# --- Groundedness / hallucination check (output guard) ---------------------

def check_groundedness(
    answer: str, citations: list[Citation], *, used_rag: bool
) -> dict:
    """Heuristic groundedness score.

    If the agent retrieved from the knowledge base but produced an answer with no
    citations, that's a hallucination risk worth flagging to the caller.
    """
    if not used_rag:
        return {"grounded": True, "score": 1.0, "reason": "no knowledge base used"}

    if not citations:
        return {
            "grounded": False,
            "score": 0.0,
            "reason": "答案缺少知识库引用，存在编造风险",
        }

    # Crude lexical overlap between answer and the cited snippets.
    answer_tokens = set(re.findall(r"\w+", answer.lower()))
    cited_tokens: set[str] = set()
    for c in citations:
        cited_tokens |= set(re.findall(r"\w+", c.snippet.lower()))
    if not answer_tokens:
        return {"grounded": True, "score": 1.0, "reason": "empty answer"}

    overlap = len(answer_tokens & cited_tokens) / len(answer_tokens)
    grounded = overlap >= 0.15 or max((c.score for c in citations), default=0) >= 0.6
    return {
        "grounded": grounded,
        "score": round(overlap, 3),
        "reason": "ok" if grounded else "答案与引用片段重合度低",
    }
