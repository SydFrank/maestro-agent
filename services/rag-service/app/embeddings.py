"""Embedding client with a deterministic local fallback.

In production we call OpenAI's embedding endpoint. When no key is configured
(demo / CI), we fall back to a deterministic hashing embedding so the whole RAG
pipeline still runs end-to-end without external dependencies.
"""

from __future__ import annotations

import hashlib

import numpy as np
from openai import AsyncOpenAI

from agent_common.logging import get_logger
from app.settings import settings

log = get_logger("embeddings")


class Embedder:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        if settings.openai_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        else:
            log.warning("embeddings_fallback", reason="no OPENAI_API_KEY, using local hash embeddings")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is not None:
            resp = await self._client.embeddings.create(
                model=settings.embedding_model, input=texts
            )
            return [d.embedding for d in resp.data]
        return [self._local_embed(t) for t in texts]

    def _local_embed(self, text_: str) -> list[float]:
        """Deterministic, normalised pseudo-embedding (bag-of-hashed-tokens)."""
        dim = settings.embedding_dim
        vec = np.zeros(dim, dtype=np.float32)
        for token in text_.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()


embedder = Embedder()
