from __future__ import annotations

from typing import Protocol

from agent_common.schemas import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    """Uniform interface every model provider implements.

    The agent and RAG services only ever see this interface — swapping Claude
    for OpenAI (or a local model later) requires no change upstream.
    """

    name: str

    async def complete(self, req: LLMRequest) -> LLMResponse: ...
