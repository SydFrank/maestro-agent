"""Order tools — the agent's bridge to the (mock) order business system.

Split into read tools (查订单/查物流, no side effects) and a write tool
(发起退款, side effect → Human-in-the-Loop). The refund tool deliberately
cannot complete a refund: it can only create a ``pending_approval`` request, so
a human stays in the loop for money-moving actions.
"""

from __future__ import annotations

from typing import Any

from app.clients import order_client
from app.tools.base import Tool, ToolContext, registry


async def _query_order(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return await order_client.get_order(str(args["order_id"]))


async def _list_my_orders(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return await order_client.list_orders(
        tenant_id=ctx["tenant_id"], user_id=ctx["user_id"]
    )


async def _request_refund(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    result = await order_client.request_refund(
        str(args["order_id"]), str(args.get("reason", ""))
    )
    # Make the HITL nature explicit in the observation fed back to the model.
    if "error" not in result:
        result["note"] = "退款已提交，处于待人工审批状态，不会自动到账。"
    return result


registry.register(
    Tool(
        name="query_order",
        description="按订单号查询订单详情（商品、金额、状态、物流）。",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "订单号，如 ORD-1001"}},
            "required": ["order_id"],
        },
        run=_query_order,
    )
)

registry.register(
    Tool(
        name="list_my_orders",
        description="列出当前用户的全部订单（无需参数，自动按登录用户过滤）。",
        input_schema={"type": "object", "properties": {}},
        run=_list_my_orders,
    )
)

registry.register(
    Tool(
        name="request_refund",
        description=(
            "为指定订单发起退款申请。注意：这是有副作用的动作，只会创建一条"
            "待人工审批的退款单，不会立即退款。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "要退款的订单号"},
                "reason": {"type": "string", "description": "退款原因"},
            },
            "required": ["order_id"],
        },
        run=_request_refund,
    )
)
