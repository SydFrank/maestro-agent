from __future__ import annotations

from agent_common.observability import create_app
from pydantic import BaseModel

from app import workspace
from app.settings import settings

app = create_app(settings.service_name, log_level=settings.log_level)


@app.on_event("startup")
async def _startup() -> None:
    workspace.reset_workspace()


@app.post("/v1/workspace/reset")
async def reset() -> dict:
    workspace.reset_workspace()
    return {"ok": True, "note": "workspace 已重置到种子状态"}


class SearchBody(BaseModel):
    query: str
    max_results: int = 25


@app.post("/v1/search")
async def search(body: SearchBody) -> dict:
    return {"matches": workspace.search(body.query, body.max_results)}


@app.get("/v1/file")
async def read_file(path: str) -> dict:
    return workspace.read_file(path)


class EditBody(BaseModel):
    path: str
    old: str
    new: str


@app.post("/v1/edit")
async def edit(body: EditBody) -> dict:
    return workspace.edit_file(body.path, body.old, body.new)


@app.post("/v1/run")
async def run() -> dict:
    return workspace.run_tests()
