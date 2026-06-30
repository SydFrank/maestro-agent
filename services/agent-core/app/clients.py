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


class OrderClient:
    """Client to the (mock) order business system."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.order_service_url, timeout=15.0
        )

    async def get_order(self, order_id: str) -> dict:
        resp = await self._client.get(f"/v1/orders/{order_id}", headers=_trace_headers())
        if resp.status_code == 404:
            return {"error": f"未找到订单 {order_id}"}
        resp.raise_for_status()
        return resp.json()

    async def list_orders(self, *, tenant_id: str, user_id: str) -> dict:
        resp = await self._client.get(
            "/v1/orders",
            params={"tenant_id": tenant_id, "user_id": user_id},
            headers=_trace_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def request_refund(self, order_id: str, reason: str) -> dict:
        resp = await self._client.post(
            f"/v1/orders/{order_id}/refund",
            json={"reason": reason},
            headers=_trace_headers(),
        )
        if resp.status_code == 404:
            return {"error": f"未找到订单 {order_id}"}
        resp.raise_for_status()
        return resp.json()


llm_client = LLMClient()
rag_client = RagClient()
order_client = OrderClient()

