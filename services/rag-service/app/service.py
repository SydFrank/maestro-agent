"""Ingestion and retrieval logic (kept out of the HTTP layer)."""

from __future__ import annotations

from sqlalchemy import select

from agent_common.logging import get_logger
from agent_common.schemas import Citation
from app.chunking import chunk_text
from app.db import Chunk, Document, SessionLocal
from app.embeddings import embedder

log = get_logger("rag")


async def ingest_document(
    *, tenant_id: str, source: str, title: str, content: str
) -> dict:
    """Split → embed → persist. Returns the created document id and chunk count."""
    chunks = chunk_text(content)
    if not chunks:
        return {"document_id": None, "chunks": 0}

    vectors = await embedder.embed(chunks)

    async with SessionLocal() as session:
        doc = Document(tenant_id=tenant_id, source=source, title=title)
        session.add(doc)
        await session.flush()  # assign doc.id

        for i, (text_, vec) in enumerate(zip(chunks, vectors)):
            session.add(
                Chunk(
                    document_id=doc.id,
                    tenant_id=tenant_id,
                    ordinal=i,
                    content=text_,
                    embedding=vec,
                )
            )
        await session.commit()
        log.info("ingested", document_id=doc.id, chunks=len(chunks), tenant_id=tenant_id)
        return {"document_id": doc.id, "chunks": len(chunks)}


async def retrieve(*, tenant_id: str, query: str, top_k: int = 5) -> list[Citation]:
    """Cosine-similarity search scoped to the tenant, returned as citations."""
    (query_vec,) = await embedder.embed([query])

    async with SessionLocal() as session:
        # pgvector cosine distance operator <=> ; similarity = 1 - distance.
        distance = Chunk.embedding.cosine_distance(query_vec).label("distance")
        stmt = (
            select(Chunk, Document.source, distance)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.tenant_id == tenant_id)
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await session.execute(stmt)).all()

    citations: list[Citation] = []
    for chunk, source, dist in rows:
        citations.append(
            Citation(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                source=source,
                score=round(1.0 - float(dist), 4),
                snippet=chunk.content[:400],
            )
        )
    return citations
