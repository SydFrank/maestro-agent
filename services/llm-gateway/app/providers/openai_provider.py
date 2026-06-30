"""OpenAI provider (fallback) — normalised to the same ``LLMResponse``.

Also reachable for any OpenAI-compatible endpoint by overriding ``OPENAI_BASE_URL``
(self-hosted / proxy), which keeps the door open for future model choices.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

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


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_s,
            max_retries=0,
        )

    @staticmethod
    def _to_openai_messages(messages: list[ChatMessage]) -> list[dict]:
        role_map = {
            Role.system: "system",
            Role.user: "user",
            Role.assistant: "assistant",
            Role.tool: "tool",
        }
        return [{"role": role_map[m.role], "content": m.content} for m in messages]

    @staticmethod
    def _to_openai_tools(tools: list[dict] | None) -> list[dict] | None:
        """Adapt the platform's Anthropic-shaped tool schema to OpenAI's."""
        if not tools:
            return None
        adapted = []
        for t in tools:
            adapted.append(
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
            )
        return adapted

    async def complete(self, req: LLMRequest) -> LLMResponse:
        model = req.model or settings.openai_model
        kwargs: dict = {
            "model": model,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "messages": self._to_openai_messages(req.messages),
        }
        if (tools := self._to_openai_tools(req.tools)) is not None:
            kwargs["tools"] = tools

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]

        tool_calls: list[ToolCall] = []
        for tc in choice.message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = TokenUsage(
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            cost_usd=estimate_cost(
                model,
                resp.usage.prompt_tokens if resp.usage else 0,
                resp.usage.completion_tokens if resp.usage else 0,
            ),
        )
        return LLMResponse(
            content=choice.message.content or "",
            provider=self.name,
            model=model,
            finish_reason=choice.finish_reason or "stop",
            tool_calls=tool_calls,
            usage=usage,
        )
