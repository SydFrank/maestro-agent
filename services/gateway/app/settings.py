from __future__ import annotations

from agent_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "gateway"

    jwt_secret: str = "change-me-in-prod-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120

    agent_core_url: str = "http://agent-core:8000"
    rag_service_url: str = "http://rag-service:8000"

    # Rate limit: requests per window per user.
    rate_limit_requests: int = 30
    rate_limit_window_s: int = 60


settings = Settings()
