"""Claude provider (primary) — Opus 4.8 via the Anthropic SDK.

Handles the Anthropic-specific quirks (system prompt is a top-level arg, tool
calls come back as ``tool_use`` content blocks) and normalises everything to the
platform's shared ``LLMResponse``.
"""

from __future__ import annotations

import anthropic

from agent_common.schemas import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    Role,
    TokenUsage,
    ToolCall,
)
from app.pricing import estimate_cost
from app.settings import settings


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.request_timeout_s,
            max_retries=0,  # retries handled centrally in the router
        )

    @staticmethod
    def _split_messages(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """Anthropic takes ``system`` separately from the message list."""
        system: str | None = None
        out: list[dict] = []
        for m in messages:
            if m.role == Role.system:
                system = m.content if system is None else f"{system}\n{m.content}"
            else:
                role = "assistant" if m.role == Role.assistant else "user"
                out.append({"role": role, "content": m.content})
        return system, out

    async def complete(self, req: LLMRequest) -> LLMResponse:
        model = req.model or settings.anthropic_model
        system, msgs = self._split_messages(req.messages)

        kwargs: dict = {
            "model": model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system
        if req.tools:
            kwargs["tools"] = req.tools

        resp = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input or {})
                )

        usage = TokenUsage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cost_usd=estimate_cost(
                model, resp.usage.input_tokens, resp.usage.output_tokens
            ),
        )
        return LLMResponse(
            content="".join(text_parts),
            provider=self.name,
            model=model,
            finish_reason=resp.stop_reason or "stop",
            tool_calls=tool_calls,
            usage=usage,
        )
