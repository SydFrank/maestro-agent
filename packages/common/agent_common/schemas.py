"""Shared Pydantic schemas — the contract between microservices.

Keeping these in one place means gateway, agent-core, rag-service and the
frontend all agree on the wire format (structured output is a JD requirement).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class ChatMessage(BaseModel):
    role: Role
    content: str


# ---- LLM gateway contract -------------------------------------------------

class LLMRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    provider: Literal["anthropic", "openai"] | None = None
    temperature: float = 0.2
    max_tokens: int = 1024
    tools: list[dict[str, Any]] | None = None
    # Pass-through tenant/user for cost attribution.
    tenant_id: str | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    finish_reason: str = "stop"
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


# ---- RAG contract ---------------------------------------------------------

class Citation(BaseModel):
    """A traceable source span backing an answer (引用溯源)."""

    document_id: str
    chunk_id: str
    source: str
    score: float
    snippet: str


class RetrieveRequest(BaseModel):
    query: str
    tenant_id: str
    top_k: int = 5


class RetrieveResponse(BaseModel):
    citations: list[Citation]


# ---- Agent contract -------------------------------------------------------

class AgentRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    tenant_id: str
    user_id: str


class AgentStep(BaseModel):
    """One observable step in the agent's reasoning loop (for Trace UI)."""

    kind: Literal["plan", "tool_call", "tool_result", "retrieve", "final"]
    name: str | None = None
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    conversation_id: str
