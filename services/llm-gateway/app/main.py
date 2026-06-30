from __future__ import annotations

from agent_common.observability import create_app
from agent_common.schemas import LLMRequest, LLMResponse
from app.router import router as llm_router
from app.settings import settings

app = create_app(settings.service_name, log_level=settings.log_level)


@app.post("/v1/chat", response_model=LLMResponse)
async def chat(req: LLMRequest) -> LLMResponse:
    """Single entry point for all model calls in the platform."""
    return await llm_router.complete(req)


@app.get("/v1/providers")
async def providers() -> dict:
    return {
        "default": settings.llm_provider,
        "available": list(llm_router._providers.keys()),  # noqa: SLF001
        "primary_model": settings.anthropic_model,
    }
