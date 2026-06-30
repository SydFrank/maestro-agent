"""客服服务自动化的专职工人花名册。

工人按**能力域**切分（不按任务步骤切），这样每个工人都是 Supervisor 能清晰
推理的"专家"。加一个能力 = 加一条记录，编排图无需改动。

三个可派发工人：
  - knowledge : 政策/FAQ 知识检索专家（RAG，带引用溯源）—— 只读
  - order     : 订单与物流查询专家（调订单业务系统）—— 只读
  - action    : 业务动作执行专家（发起退款等）—— 有副作用，落到人工审批

注：综合答复由 Supervisor 的 synthesize 节点完成，事实/合规核查由 Critic 完成，
因此它们不在可派发工人列表里（避免与编排层职责重叠）。
"""

from __future__ import annotations

from app.agents.worker import WorkerAgent

# 知识 Agent：政策/FAQ 检索专家。只配 knowledge_search（RAG）。
KNOWLEDGE = WorkerAgent(
    name="knowledge",
    persona=(
        "你是客服知识专家。职责：用 knowledge_search 在退换货政策、配送、保修等"
        "FAQ/政策库中找到依据，给出**带引用**的准确回答。"
        "政策类问题必须基于检索到的资料，资料没写的绝不臆测。"
    ),
    tool_names=["knowledge_search"],
)

# 订单 Agent：订单与物流查询专家。只读，不做任何有副作用的操作。
ORDER = WorkerAgent(
    name="order",
    persona=(
        "你是订单查询专家。职责：用 query_order / list_my_orders 查询用户的订单"
        "状态、金额、物流信息。只陈述查到的真实信息，不编造，不执行退款等动作。"
    ),
    tool_names=["query_order", "list_my_orders"],
)

# 动作 Agent：执行有副作用的业务动作（退款）。退款只会进入待人工审批状态。
ACTION = WorkerAgent(
    name="action",
    persona=(
        "你是业务动作执行专家。职责：当用户明确要求且符合政策时，用 request_refund"
        "发起退款申请。务必清楚告知用户：退款需人工审批，不会立即到账。"
        "不要在政策不允许或信息不足时擅自发起动作。"
    ),
    tool_names=["request_refund"],
)

# 可被 Supervisor 派发的专职工人。
WORKERS: dict[str, WorkerAgent] = {
    KNOWLEDGE.name: KNOWLEDGE,
    ORDER.name: ORDER,
    ACTION.name: ACTION,
}

# Supervisor 用于路由决策的能力清单。
WORKER_CATALOG = {
    "knowledge": "回答政策/FAQ 类问题（退换货、配送、保修等），带引用溯源",
    "order": "查询用户的订单状态、金额与物流信息",
    "action": "执行业务动作：为订单发起退款申请（需人工审批）",
}
