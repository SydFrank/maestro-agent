from __future__ import annotations

from agent_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "rag-service"

    # Embeddings
    embedding_provider: str = "openai"  # openai | anthropic-compatible | local
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 120


settings = Settings()
