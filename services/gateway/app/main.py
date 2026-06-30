from __future__ import annotations

import httpx
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_common.errors import GuardrailError, UpstreamError
from agent_common.observability import create_app
from agent_common.schemas import AgentResponse
from app.ratelimit import enforce
from app.security import User, authenticate, create_token, current_user, require_role
from app.settings import settings

app = create_app(settings.service_name, log_level=settings.log_level)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten per-environment in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = httpx.AsyncClient(base_url=settings.agent_core_url, timeout=120.0)
_rag = httpx.AsyncClient(base_url=settings.rag_service_url, timeout=60.0)

# Minimal injection pre-filter at the edge (defence in depth; agent-core also checks).
import re  # noqa: E402

_EDGE_INJECTION = re.compile(
    r"ignore\s+previous\s+instructions|忽略.{0,4}(指令|提示)|reveal\s+system\s+prompt",
    re.IGNORECASE,
)


# ---- auth ------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    role: str


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    user = authenticate(req.username, req.password)
    return TokenResponse(
        access_token=create_token(user), tenant_id=user.tenant_id, role=user.role
    )


@app.get("/me", response_model=User)
async def me(user: User = Depends(current_user)) -> User:
    return user


# ---- chat (proxy to agent-core) -------------------------------------------
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@app.post("/v1/chat", response_model=AgentResponse)
async def chat(req: ChatRequest, user: User = Depends(current_user)) -> AgentResponse:
    await enforce(f"{user.tenant_id}:{user.username}")

    if _EDGE_INJECTION.search(req.message or ""):
        raise GuardrailError("输入包含可疑指令，已被网关拦截")

    payload = {
        "message": req.message,
        "conversation_id": req.conversation_id,
        "tenant_id": user.tenant_id,  # tenant is taken from the token, never the client
        "user_id": user.username,
    }
    try:
        resp = await _agent.post("/v1/agent/chat", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise UpstreamError("agent-core 不可用", detail={"error": str(exc)})
    return AgentResponse.model_validate(resp.json())


# ---- knowledge base ingestion (admin only) --------------------------------
class DocumentRequest(BaseModel):
    source: str
    title: str = ""
    content: str


@app.post("/v1/documents")
async def ingest(
    req: DocumentRequest, user: User = Depends(require_role("admin"))
) -> dict:
    payload = {
        "tenant_id": user.tenant_id,
        "source": req.source,
        "title": req.title,
        "content": req.content,
    }
    try:
        resp = await _rag.post("/v1/ingest", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise UpstreamError("rag-service 不可用", detail={"error": str(exc)})
    return resp.json()
