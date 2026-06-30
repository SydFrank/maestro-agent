from __future__ import annotations

from agent_common.config import BaseServiceSettings
from agent_common.errors import AppError
from agent_common.observability import create_app
from pydantic import BaseModel

from app import store


class Settings(BaseServiceSettings):
    service_name: str = "order-service"


settings = Settings()
app = create_app(settings.service_name, log_level=settings.log_level)


class NotFound(AppError):
    code = "order_not_found"
    http_status = 404


@app.get("/v1/orders/{order_id}")
async def get_order(order_id: str) -> store.Order:
    order = store.get_order(order_id)
    if order is None:
        raise NotFound(f"订单 {order_id} 不存在")
    return order


@app.get("/v1/orders")
async def list_orders(tenant_id: str, user_id: str) -> dict:
    orders = store.list_orders(tenant_id=tenant_id, user_id=user_id)
    return {"orders": [o.model_dump() for o in orders]}


class RefundBody(BaseModel):
    reason: str = ""


@app.post("/v1/orders/{order_id}/refund")
async def request_refund(order_id: str, body: RefundBody) -> store.RefundRequest:
    """Create a refund request — lands in pending_approval (HITL gate)."""
    refund = store.create_refund(order_id, body.reason)
    if refund is None:
        raise NotFound(f"订单 {order_id} 不存在")
    return refund


class ApproveBody(BaseModel):
    approve: bool = True


@app.post("/v1/refunds/{refund_id}/approve")
async def approve_refund(refund_id: str, body: ApproveBody) -> store.RefundRequest:
    """Human approval endpoint (would be a back-office UI in production)."""
    refund = store.approve_refund(refund_id, approve=body.approve)
    if refund is None:
        raise NotFound(f"退款单 {refund_id} 不存在")
    return refund
