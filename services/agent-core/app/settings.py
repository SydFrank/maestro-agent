from __future__ import annotations

from agent_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "agent-core"

    llm_gateway_url: str = "http://llm-gateway:8000"
    rag_service_url: str = "http://rag-service:8000"
    order_service_url: str = "http://order-service:8000"

    model: str = "claude-opus-4-8"  # strong model: final synthesis + critic
    # Cost tiering: routing is a cheap decision, run it on a cheaper model.
    supervisor_model: str = "claude-haiku-4-5-20251001"
    max_tool_iterations: int = 6  # ReAct loop safety bound (single worker)
    max_supervisor_rounds: int = 3  # multi-agent loop safety bound
    memory_window: int = 12  # messages kept per conversation


settings = Settings()
