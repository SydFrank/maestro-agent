from __future__ import annotations

from agent_common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "sandbox-runner"

    workspace_dir: str = "/tmp/agent-workspace"
    run_timeout_s: int = 30  # hard cap on test execution


settings = Settings()
