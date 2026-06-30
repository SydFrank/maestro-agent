from __future__ import annotations

import uuid

from agent_common.observability import create_app
from agent_common.schemas import (
    AgentRequest,
    AgentResponse,
    ChatMessage,
    Citation,
    Role,
    TokenUsage,
)
from app.memory import append, load_history
from app.multi_agent import multi_agent_graph
from app.settings import settings

app = create_app(settings.service_name, log_level=settings.log_level)


@app.post("/v1/agent/chat", response_model=AgentResponse)
async def chat(req: AgentRequest) -> AgentResponse:
    conversation_id = req.conversation_id or str(uuid.uuid4())
    history = await load_history(conversation_id)

    # ctx is the per-run scratch space shared with workers/tools (citations land here).
    ctx = {"tenant_id": req.tenant_id, "user_id": req.user_id, "_citations": []}

    state = await multi_agent_graph.ainvoke(
        {
            "tenant_id": req.tenant_id,
            "user_id": req.user_id,
            "question": req.message,
            "ctx": ctx,
        }
    )

    answer = state.get("answer", "")
    # Citations the knowledge worker gathered (de-dup by chunk, best score first).
    raw = state.get("ctx", {}).get("_citations", [])
    dedup: dict[str, Citation] = {}
    for c in raw:
        cit = Citation.model_validate(c)
        if cit.chunk_id not in dedup or cit.score > dedup[cit.chunk_id].score:
            dedup[cit.chunk_id] = cit
    citations = sorted(dedup.values(), key=lambda c: c.score, reverse=True)

    usage = state.get("usage") or TokenUsage()

    # Persist the turn (skip if blocked by guardrail).
    if not state.get("blocked"):
        await append(conversation_id, ChatMessage(role=Role.user, content=req.message))
        await append(conversation_id, ChatMessage(role=Role.assistant, content=answer))

    return AgentResponse(
        answer=answer,
        citations=citations,
        steps=state.get("steps", []),
        usage=usage,
        conversation_id=conversation_id,
    )
