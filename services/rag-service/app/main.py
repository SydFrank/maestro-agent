from __future__ import annotations

from pydantic import BaseModel

from agent_common.observability import create_app
from agent_common.schemas import RetrieveRequest, RetrieveResponse
from app.db import init_db
from app.service import ingest_document, retrieve
from app.settings import settings

app = create_app(settings.service_name, log_level=settings.log_level)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()


class IngestRequest(BaseModel):
    tenant_id: str
    source: str
    title: str = ""
    content: str


class IngestResponse(BaseModel):
    document_id: str | None
    chunks: int


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    result = await ingest_document(
        tenant_id=req.tenant_id,
        source=req.source,
        title=req.title,
        content=req.content,
    )
    return IngestResponse(**result)


@app.post("/v1/retrieve", response_model=RetrieveResponse)
async def retrieve_endpoint(req: RetrieveRequest) -> RetrieveResponse:
    citations = await retrieve(
        tenant_id=req.tenant_id, query=req.query, top_k=req.top_k
    )
    return RetrieveResponse(citations=citations)
