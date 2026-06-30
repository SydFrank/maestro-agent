"""In-memory order store with seeded demo data.

This is a deliberately MOCK business system: the data lives in memory and is
seeded at startup. The point is a *realistic API boundary* the agent integrates
with — swapping this for a real order DB/ERP requires no change in agent-core.
Refunds model Human-in-the-Loop: the agent can only *request* a refund; it lands
in ``pending_approval`` and a human must approve it.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class Order(BaseModel):
    order_id: str
    tenant_id: str
    user_id: str
    product: str
    amount: float
    status: str  # paid | shipped | delivered | returned
    order_date: str
    logistics: str  # 物流状态
    refund_status: str = "none"  # none | pending_approval | approved | rejected


class RefundRequest(BaseModel):
    refund_id: str
    order_id: str
    reason: str
    amount: float
    status: str = "pending_approval"


# order_id -> Order
_ORDERS: dict[str, Order] = {}
# refund_id -> RefundRequest
_REFUNDS: dict[str, RefundRequest] = {}


def _seed() -> None:
    seed = [
        Order(order_id="ORD-1001", tenant_id="acme", user_id="alice",
              product="无线降噪耳机 Pro", amount=899.0, status="delivered",
              order_date="2026-06-18", logistics="已签收 (2026-06-21)"),
        Order(order_id="ORD-1002", tenant_id="acme", user_id="alice",
              product="机械键盘 87键", amount=399.0, status="shipped",
              order_date="2026-06-25", logistics="运输中 (预计 06-29 到达)"),
        Order(order_id="ORD-1003", tenant_id="acme", user_id="admin",
              product="4K 显示器 27寸", amount=1599.0, status="delivered",
              order_date="2026-06-10", logistics="已签收 (2026-06-13)"),
    ]
    for o in seed:
        _ORDERS[o.order_id] = o


_seed()


def get_order(order_id: str) -> Order | None:
    return _ORDERS.get(order_id)


def list_orders(*, tenant_id: str, user_id: str) -> list[Order]:
    return [
        o for o in _ORDERS.values()
        if o.tenant_id == tenant_id and o.user_id == user_id
    ]


def create_refund(order_id: str, reason: str) -> RefundRequest | None:
    order = _ORDERS.get(order_id)
    if order is None:
        return None
    refund = RefundRequest(
        refund_id=f"RF-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        reason=reason,
        amount=order.amount,
    )
    _REFUNDS[refund.refund_id] = refund
    order.refund_status = "pending_approval"
    return refund


def approve_refund(refund_id: str, *, approve: bool) -> RefundRequest | None:
    refund = _REFUNDS.get(refund_id)
    if refund is None:
        return None
    refund.status = "approved" if approve else "rejected"
    if (order := _ORDERS.get(refund.order_id)) is not None:
        order.refund_status = refund.status
        if approve:
            order.status = "returned"
    return refund
