# Agentic RAG Platform · 企业级 AI Agent 平台

> 一个**可落地、可演示、可上线**的企业级 Agentic RAG 平台。
> 覆盖：前端 + 后端 + 微服务 + Docker + 云端(K8s) + 深度 AI-Agent 技术栈。
> 主模型 **Claude Opus 4.8**，OpenAI 为备选，通过 LLM 网关统一抽象、按需切换。

---

## 1. 这个项目证明了什么（对应岗位要求）

| 能力要求 | 在本项目中的落点 |
|---|---|
| Python 后端 + 系统工程 | `services/*` 全部 FastAPI + Pydantic v2 |
| Agent 架构（ReAct / Planning / Tool Use / Memory） | `services/agent-core`（LangGraph 状态机） |
| Tool Calling / 结构化输出 | `agent-core/app/tools/*` + Pydantic 工具签名 |
| RAG + 引用溯源 | `services/rag-service`（pgvector + 带 citation 的检索） |
| 模型评测 / 评测集 | `evals/`（离线评测 + 在线护栏） |
| 异常处理 + 运行监控 + Trace + 成本 | `packages/common/observability`（OTel + 结构化日志 + token 计费） |
| 幻觉治理 + Prompt Injection 防护 + 权限 | `services/gateway/security` + `agent-core/app/guardrails` |
| FastAPI + PostgreSQL + Redis + 向量库 | `docker-compose.yml` 全栈编排 |
| Docker / CI-CD / 云端 | `Dockerfile` ×N + `.github/workflows` + `deploy/k8s` |
| 前端全栈 | `frontend/`（React + TS + Vite） |
| 微服务 / 分布式 | 4 个独立服务，HTTP + Redis 解耦 |

---

## 2. 系统架构

```
                          ┌──────────────────────┐
                          │   frontend (React)   │  聊天 UI / 文档上传 / Trace 查看
                          └───────────┬──────────┘
                                      │ HTTPS
                          ┌───────────▼──────────┐
                          │   gateway (FastAPI)  │  鉴权(JWT) · RBAC · 限流
                          │                      │  Prompt-Injection 网关 · BFF
                          └─────┬───────────┬────┘
                                │           │
              ┌─────────────────▼──┐    ┌───▼───────────────────┐
              │  agent-core        │    │  rag-service          │
              │  LangGraph 编排     │◄──►│  ingest / embed /     │
              │  Planner→ReAct→Tool│    │  retrieve (引用溯源)   │
              │  Memory / Guardrail│    └───────────┬───────────┘
              └─────────┬──────────┘                │
                        │                           │
              ┌─────────▼───────────────────────────▼──────────┐
              │              llm-gateway (FastAPI)              │
              │   Claude Opus 4.8 (主) / OpenAI (备)            │
              │   重试 · 熔断 · token & 成本计量 · 缓存           │
              └─────────────────────────────────────────────────┘

   基础设施：PostgreSQL + pgvector · Redis · OpenTelemetry Collector
```

### 微服务划分理由
- **gateway**：所有外部流量唯一入口，集中做安全（鉴权/RBAC/防注入/限流），其余服务只在内网通信。
- **agent-core**：Agent 编排核心，是项目的"大脑"，独立伸缩。
- **rag-service**：知识库的写入与检索独立，便于单独扩容向量计算。
- **llm-gateway**：模型供应商抽象层，切换 Claude/OpenAI、统一计费与限速、屏蔽上游差异。

---

## 3. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 · TypeScript · Vite · TailwindCSS |
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · uvicorn |
| Agent | LangGraph（状态机编排）· Anthropic SDK |
| 数据 | PostgreSQL 16 + pgvector · Redis 7 |
| 可观测 | OpenTelemetry · structlog · Prometheus 指标 |
| 容器 | Docker · docker-compose |
| 云端 | Kubernetes 清单（`deploy/k8s`）· GitHub Actions CI |

---

## 4. 快速开始

```bash
cp .env.example .env          # 填入 ANTHROPIC_API_KEY
docker compose up -d --build  # 一键拉起全部服务
# 前端  http://localhost:5173
# 网关  http://localhost:8080/docs
```

详见 [docs/architecture.md](docs/architecture.md) 与各服务目录下的 README。

## 5. 目录结构

```
.
├── frontend/            # React + TS 聊天前端
├── services/
│   ├── gateway/         # 入口网关：鉴权 / RBAC / 限流 / 防注入
│   ├── agent-core/      # LangGraph Agent 编排
│   ├── rag-service/     # RAG 入库与检索（引用溯源）
│   └── llm-gateway/     # 模型抽象与计费
├── packages/common/     # 共享：配置 / 日志 / 追踪 / Schema
├── evals/               # 评测集与离线评测
├── deploy/k8s/          # Kubernetes 部署清单
├── docs/                # 架构与设计文档
└── docker-compose.yml
```
