from __future__ import annotations

from agent_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "llm-gateway"

    # Provider selection
    llm_provider: str = "anthropic"  # anthropic | openai

    # Anthropic (primary)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # OpenAI (fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # Resilience
    request_timeout_s: float = 60.0
    max_retries: int = 2


settings = Settings()
