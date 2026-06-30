"""HTTP clients to the other microservices (llm-gateway, rag-service).

Trace headers are propagated so a single conversation can be followed across
service boundaries in the logs.
"""

from __future__ import annotations

import httpx

from agent_common.errors import UpstreamError
from agent_common.logging import request_id_ctx, trace_id_ctx
from agent_common.schemas import (
    Citation,
    LLMRequest,
    LLMResponse,
    RetrieveResponse,
)
from app.settings import settings


def _trace_headers() -> dict[str, str]:
    headers = {}
    if (rid := request_id_ctx.get()) is not None:
        headers["X-Request-Id"] = rid
    if (tid := trace_id_ctx.get()) is not None:
        headers["X-Trace-Id"] = tid
    return headers


class LLMClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_gateway_url, timeout=90.0
        )

    async def complete(self, req: LLMRequest) -> LLMResponse:
        try:
            resp = await self._client.post(
                "/v1/chat", json=req.model_dump(), headers=_trace_headers()
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("llm-gateway call failed", detail={"error": str(exc)})
        return LLMResponse.model_validate(resp.json())


class RagClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.rag_service_url, timeout=30.0
        )

    async def retrieve(self, *, tenant_id: str, query: str, top_k: int = 5) -> list[Citation]:
        try:
            resp = await self._client.post(
                "/v1/retrieve",
                json={"tenant_id": tenant_id, "query": query, "top_k": top_k},
                headers=_trace_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("rag-service call failed", detail={"error": str(exc)})
        return RetrieveResponse.model_validate(resp.json()).citations


class SandboxClient:
    """Client to the sandbox-runner: the agent's code workspace + test runner."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.sandbox_runner_url, timeout=60.0
        )

    async def search(self, query: str, max_results: int = 25) -> dict:
        resp = await self._client.post(
            "/v1/search",
            json={"query": query, "max_results": max_results},
            headers=_trace_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def read_file(self, path: str) -> dict:
        resp = await self._client.get(
            "/v1/file", params={"path": path}, headers=_trace_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def edit_file(self, path: str, old: str, new: str) -> dict:
        resp = await self._client.post(
            "/v1/edit",
            json={"path": path, "old": old, "new": new},
            headers=_trace_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def run_tests(self) -> dict:
        resp = await self._client.post("/v1/run", headers=_trace_headers())
        resp.raise_for_status()
        return resp.json()


llm_client = LLMClient()
rag_client = RagClient()
sandbox_client = SandboxClient()

