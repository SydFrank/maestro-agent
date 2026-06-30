"""knowledge_search tool — RAG retrieval over the enterprise knowledge base.

Returns ranked snippets *with* their source ids so the model can cite them and
the final answer stays traceable (引用溯源).
"""

from __future__ import annotations

from typing import Any

from app.clients import rag_client
from app.tools.base import Tool, ToolContext, registry

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "自然语言检索词，用于在企业知识库中查找相关资料",
        },
        "top_k": {
            "type": "integer",
            "description": "返回的片段数量，默认 5",
            "default": 5,
        },
    },
    "required": ["query"],
}


async def _run(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    citations = await rag_client.retrieve(
        tenant_id=ctx["tenant_id"],
        query=args["query"],
        top_k=int(args.get("top_k", 5)),
    )
    # Stash citations on the context so the graph can surface them in the answer.
    ctx.setdefault("_citations", []).extend(c.model_dump() for c in citations)
    return {
        "results": [
            {
                "chunk_id": c.chunk_id,
                "source": c.source,
                "score": c.score,
                "snippet": c.snippet,
            }
            for c in citations
        ]
    }


registry.register(
    Tool(
        name="knowledge_search",
        description=(
            "在企业内部知识库中检索与问题相关的资料片段。"
            "当用户的问题需要依据公司文档/资料回答时调用。"
        ),
        input_schema=_INPUT_SCHEMA,
        run=_run,
    )
)
