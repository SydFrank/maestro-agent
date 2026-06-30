"""Provider routing: retries, primary→fallback, and cost metering.

This is the resilience layer the JDs ask for ("异常处理与运行监控"): transient
upstream errors are retried with backoff; if the primary provider stays down we
fail over to the secondary so the agent keeps working.
"""

from __future__ import annotations

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent_common.errors import UpstreamError
from agent_common.logging import get_logger
from agent_common.schemas import LLMRequest, LLMResponse
from app.providers import AnthropicProvider, LLMProvider, OpenAIProvider
from app.settings import settings

log = get_logger("llm-router")


class LLMRouter:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        if settings.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider()
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider()
        if not self._providers:
            # Allow boot without keys (dev/health), fail clearly on first call.
            log.warning("no_provider_configured")

    def _order(self, preferred: str | None) -> list[str]:
        primary = preferred or settings.llm_provider
        order = [primary] + [p for p in self._providers if p != primary]
        return [p for p in order if p in self._providers]

    async def complete(self, req: LLMRequest) -> LLMResponse:
        providers = self._order(req.provider)
        if not providers:
            raise UpstreamError("no LLM provider configured")

        last_err: Exception | None = None
        for name in providers:
            provider = self._providers[name]
            try:
                resp = await self._complete_with_retry(provider, req)
                log.info(
                    "llm_call",
                    provider=name,
                    model=resp.model,
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    cost_usd=resp.usage.cost_usd,
                    tenant_id=req.tenant_id,
                )
                return resp
            except Exception as exc:  # try next provider
                last_err = exc
                log.warning("provider_failed", provider=name, error=str(exc))

        raise UpstreamError(
            "all LLM providers failed", detail={"last_error": str(last_err)}
        )

    @retry(
        stop=stop_after_attempt(settings.max_retries + 1),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _complete_with_retry(
        self, provider: LLMProvider, req: LLMRequest
    ) -> LLMResponse:
        return await provider.complete(req)


router = LLMRouter()
