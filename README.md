# Maestro · 多 Agent 自动 Bug 修复平台

> 一个**可落地、可演示、可上线**的企业级多 Agent 编排平台，首发场景为 **自动 Bug 修复（auto bug-fix）**。
> 给定一个代码仓库 + 一个失败的测试，平台用 **Supervisor 编排 Coder / Tester / Reviewer / Fixer** 多个专职 Agent 协作，**自动定位、修复、并在沙箱中跑测试验证**，产出一份能通过测试的改动。
>
> 主模型 **Claude Opus 4.8**，OpenAI 为备选，通过 LLM 网关统一抽象、按需切换。
> 技术范围覆盖：**Agent 编排 · 工具调用 · 沙箱执行 · 上下文工程 · 评测(Harness) · 安全 · 可观测 · 微服务 · 全栈 · 容器化**。

> 状态图例：✅ 已实现　🔨 规划中（设计已定，按路线图推进）

---

## 1. 设计哲学：测试是唯一的"对错裁判"

普通 LLM 会"声称"自己修好了 bug——这是幻觉的温床。Maestro 的核心约束是：

> **Agent 不能声称修复成功，必须让沙箱里的测试真的通过。** `run_tests` 的结果是唯一的客观裁判（Critic 测试门禁），从根上压制幻觉。

这条原则贯穿整个架构——它是"能演示的玩具"和"可信赖的工程系统"的分界。

---

## 2. 系统架构（详细）

### 2.1 服务拓扑（微服务 + 基础设施）

```
                          ┌────────────────────────────────────────┐
                          │        frontend  (React + TS + Vite)    │   对话 UI · Agent 协作轨迹/Trace 可视化
                          └───────────────────┬────────────────────┘
                                              │ HTTPS / REST (JSON)
                          ┌───────────────────▼────────────────────┐
                          │            gateway  (FastAPI)           │   唯一入口 · 安全收口
                          │  JWT 鉴权 │ RBAC 权限 │ Redis 限流        │
                          │  Prompt-Injection 边界过滤 │ BFF 聚合      │
                          └───────────────────┬────────────────────┘
                                              │ 内网 HTTP（X-Trace-Id 全链路透传）
                          ┌───────────────────▼─────────────────────────────────┐
                          │                 agent-core  (FastAPI)                │
                          │           LangGraph 多 Agent 编排状态机               │
                          │  ┌────────────────────────────────────────────────┐ │
                          │  │ Supervisor(路由/聚合) ─► Coder ─► Tester         │ │
                          │  │        ▲                 │         │            │ │
                          │  │        └──── Fixer ◄─────┘    Reviewer          │ │
                          │  │  Critic = 测试门禁 │ Memory(Redis) │ Guardrail   │ │
                          │  └────────────────────────────────────────────────┘ │
                          └──────┬───────────────────────────────┬──────────────┘
                                 │ POST /v1/chat                 │ search/read/edit/run
                  ┌──────────────▼────────────┐     ┌────────────▼─────────────────┐
                  │      llm-gateway (FastAPI) │     │    sandbox-runner (FastAPI)   │
                  │  Claude Opus 4.8 (主)      │     │   代码工作区(workspace)        │
                  │  OpenAI (备) · 模型分级路由 │     │   search / read / edit         │
                  │  重试 · 熔断 · 故障转移      │     │   run_tests = pytest 沙箱执行  │
                  │  token & 成本计量 · 缓存     │     │   v1 子进程 → v2 Docker 隔离   │
                  └──────────────┬────────────┘     └───────────────────────────────┘
                                 │ HTTPS
                       ┌─────────▼──────────┐
                       │  Anthropic / OpenAI │
                       └─────────────────────┘

   基础设施：PostgreSQL 16 + pgvector · Redis 7 · (🔨 OTel Collector / Prometheus / Langfuse)
   rag-service (FastAPI + pgvector) ✅ 保留，用于"代码文档 / 历史 issue 的 RAG 增强"(🔨 接入)
```

### 2.2 多 Agent 修复流程（LangGraph 状态机）

```
 START
   │
   ▼
 guard_input ──检测到提示词注入──► [拦截] END
   │ 安全通过
   ▼
 supervise  ◄──────────────────────────────────┐  有界循环 (≤ max_supervisor_rounds=8)
   │  Supervisor 路由决策（用便宜模型 Haiku，成本分级）│
   │  看"问题 + 已有结果" → 决定下一步派谁           │
   ▼                                              │
 dispatch ──► 执行选中的 worker ──────────────────┘
   │     • Coder    : search_code 定位 → read_file → edit_code 修改
   │     • Tester   : run_tests 在沙箱跑 pytest（客观结果）
   │     • Fixer    : 测试失败时，结合报错做针对性再修
   │     • Reviewer : read_file 审查最终改动质量/副作用
   ▼  Supervisor 判断信息已足够
 synthesize  汇总修复过程 + 最终测试状态（用强模型 Opus 4.8）
   │
   ▼
 critic  ── 测试门禁：sandbox 里的测试真的通过了吗？
   │              ├─ ✅ 通过 ──────────────► END（产出通过的改动）
   │              └─ ❌ 未过 ──► 一次有界修订轮 ──► supervise
```

**两道安全护栏，杜绝失控**：① 每个 worker 内部 ReAct 步数上限（`max_tool_iterations`）② Supervisor 总轮数上限（`max_supervisor_rounds`）。任一超限即强制收尾，返回 best-effort 而非死循环。

### 2.3 分层能力架构（10 层）

```
┌──────────────────────────────────────────────────────────────────────┐
│ L10 全栈交付层    React+TS+Vite 前端 · Docker/Compose · 🔨K8s/HPA · 🔨CI/CD · 🔨Locust压测 │
├──────────────────────────────────────────────────────────────────────┤
│ L9  可观测层      structlog 结构化日志 · trace_id 全链路 · Prometheus 指标 · 🔨OTel/Langfuse │
├──────────────────────────────────────────────────────────────────────┤
│ L8  安全防护层    Prompt-Injection(规则✅/🔨语义) · JWT 鉴权 · RBAC · 多租户隔离 · 工具沙箱(AST) │
├──────────────────────────────────────────────────────────────────────┤
│ L7  评测层(Harness) Critic 测试门禁✅ · 🔨评测集(20-50 bug) · 🔨通过率/回归门禁 · 🔨轨迹回放 │
├──────────────────────────────────────────────────────────────────────┤
│ L6  沙箱执行层    sandbox-runner: 代码工作区 + pytest 执行 + 超时/资源限制(v1) · 🔨Docker隔离(v2) │
├──────────────────────────────────────────────────────────────────────┤
│ L5  上下文与记忆层 Context 隔离(worker 只拿子任务) · token 预算 · Redis 滑动窗口记忆 · 🔨摘要压缩 │
├──────────────────────────────────────────────────────────────────────┤
│ L4  代码检索层    search_code 关键词检索 · read_file 精读 · 🔨AST 语义索引 · 🔨向量化代码 RAG │
├──────────────────────────────────────────────────────────────────────┤
│ L3  Multi-Agent 编排层 Supervisor 调度 + Coder/Tester/Reviewer/Fixer · 任务路由 · 结果聚合 · 并行能力 │
├──────────────────────────────────────────────────────────────────────┤
│ L2  工具调用层    Function/Tool Calling · 工具注册表 · Pydantic 结构化输出 · 工具失败→观察(容错) │
├──────────────────────────────────────────────────────────────────────┤
│ L1  推理引擎层    ReAct 循环(Reason→Act→Observe) · 结构化 JSON 动作 · 对标 CoT/ToT/ReWOO/Plan-Execute │
└──────────────────────────────────────────────────────────────────────┘
   ↓ 贯穿所有层 ↓   LangGraph(状态机) · FastAPI(异步) · Claude Opus 4.8 · PostgreSQL+pgvector · Redis
```

### 2.4 一次修复的端到端数据流

```
1. 用户在前端输入："src/calc.py 的 divide 结果不对，让测试通过"
2. gateway：校验 JWT → 查 RBAC → Redis 限流 → 注入过滤 → 透传 tenant/user + trace_id 给 agent-core
3. agent-core/guard_input：再查一遍注入（纵深防御）→ 通过
4. Supervisor(Haiku 路由) → 派 Coder
5. Coder(ReAct)：search_code("divide") → read_file("src/calc.py") → 发现 a*b → edit_code 改成 a/b
6. Supervisor → 派 Tester
7. Tester：run_tests → sandbox-runner 在工作区跑 pytest → 返回 passed=true
8. Supervisor 判断完成 → synthesize(Opus) 汇总"改了什么、测试通过"
9. Critic 测试门禁：_last_test.passed == true → ✅ 批准
10. agent-core 返回 {答案, 协作步骤 steps, token/成本 usage}；前端渲染答案 + Agent 协作轨迹
   —— 全程每一步都带 trace_id，可在日志/轨迹视图中重放
```

### 2.5 Harness 评测体系（质量闭环 · 差异化核心）

Runtime 让 Agent "能跑"，**Harness 让 Agent "可信"**——它是给 Agent 做自动体检的一整套评测/回归/调试体系（对应 JD 的 "Harness Engineering"）。这是本项目最核心的差异化，也是"能演示的玩具"与"可上线的系统"的分界。

```
 评测集 EvalSet (N 个 bug 用例：仓库快照 + 失败测试 + 期望修复)
        │
        ▼
 批量执行 ──► 每个用例送入多 Agent 修复流程 (Supervisor→Coder→Tester→Fixer→Reviewer)
        │
        ▼
 沙箱验证 (run_tests) ──► 客观判定：测试通过 / 失败   ← 唯一裁判，无幻觉空间
        │
        ▼
 指标汇总 ┌─ pass@1 修复成功率（核心 KPI）
        ├─ 平均修复轮数 / 平均 token & 成本 / 平均耗时
        │
        ├─► 轨迹回放 (Trace Replay)：每个用例的完整 Agent 协作步骤可回看、逐步调试
        └─► 回归门禁 (Regression Gate)：CI 中通过率低于阈值即阻断合并 → 防止改 prompt 越改越差
```

| Harness 能力 | 作用 | 状态 |
|---|---|---|
| 测试门禁 Critic | 修复成功的唯一客观标准（run_tests 通过）| ✅ |
| 沙箱验证环境 | 隔离地跑仓库测试 | ✅ |
| 评测集 EvalSet | 20-50 个 bug 用例，衡量真实修复能力 | 🔨 |
| 通过率指标 pass@1 | 量化"到底能修好多少"（面试硬证据）| 🔨 |
| 轨迹回放 | 回看/调试每次修复的 Agent 全过程 | 🔨 |
| 回归门禁 | 通过率下降即拦截，保证不退化 | 🔨 |
| 成本/延迟指标 | 每次修复的 token/$/耗时 | 🔨 |

> **一句面试话术**：*"我用 Harness 在 N 个 bug 用例上跑评测，pass@1 = X%；加了 rerank 检索后提升到 Y%；每次修复平均 $Z、P99 W 秒。"* —— 有没有这组数字，就是 25K 和 50K 的分界。

---

## 3. 技术栈（详细）

### 3.1 后端 / Agent
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 语言 | Python 3.12 | 全部后端服务 | ✅ |
| Web 框架 | FastAPI + uvicorn | 异步 HTTP 服务（5 个微服务）| ✅ |
| 数据校验 | Pydantic v2 | 跨服务契约 / 结构化输出 / 配置 | ✅ |
| Agent 编排 | LangGraph | 多 Agent 状态机（Supervisor + 子图）| ✅ |
| 主模型 SDK | Anthropic SDK | Claude Opus 4.8 调用 | ✅ |
| 备选模型 SDK | OpenAI SDK | 故障转移 + Embedding | ✅ |
| 弹性 | tenacity | 指数退避重试 / 主备故障转移 | ✅ |
| 服务间通信 | httpx (async) | 内网调用 + trace 透传 | ✅ |
| 测试执行 | pytest | 沙箱内跑仓库测试（修复裁判）| ✅ |

### 3.2 数据 / 存储
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 关系库 | PostgreSQL 16 | 业务/元数据 | ✅ |
| 向量扩展 | pgvector (IVFFlat/HNSW) | 代码文档/issue 向量检索 | ✅(rag-service) |
| ORM | SQLAlchemy 2.0 async + asyncpg | 异步数据访问 | ✅ |
| 缓存/状态 | Redis 7 | 会话记忆 · 限流计数 · 缓存 | ✅ |

### 3.3 沙箱执行
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 工作区 | 文件系统 + 路径越界防护 | 持有代码、搜索/读取/编辑 | ✅ |
| 测试执行 | subprocess + 硬超时 | v1：受限子进程跑 pytest | ✅ |
| 真隔离 | Docker（`--network none`/资源限额）| v2：每任务独立容器 | 🔨 |

### 3.4 安全
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 认证 | PyJWT | JWT 签发/校验 | ✅ |
| 密码 | passlib[bcrypt] | 口令哈希 | ✅ |
| 权限 | 自研 RBAC 依赖 | 角色化路由保护 | ✅ |
| 注入防护 | 正则规则(✅) + 语义检测(🔨) | 边界 + 核心双重过滤 | ✅/🔨 |
| 工具沙箱 | AST 白名单 | 防工具参数注入代码 | ✅ |

### 3.5 前端
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 框架 | React 18 + TypeScript + Vite | 对话界面 | ✅ |
| API 客户端 | 类型化 fetch 封装 | 对接 gateway | ✅ |
| 轨迹可视化 | 自研组件 | Agent 协作步骤/Trace 展示 | ✅(雏形)/🔨升级 |
| 样式 | TailwindCSS | UI | 🔨 |

### 3.6 可观测 / 部署 / 运维
| 组件 | 技术 | 职责 | 状态 |
|---|---|---|---|
| 日志 | structlog | 结构化 JSON 日志 + trace_id | ✅ |
| 指标 | prometheus-client | `/metrics` 暴露 | ✅ |
| 健康检查 | FastAPI 探针 | `/healthz` | ✅ |
| 链路追踪 | OpenTelemetry | 全链路 trace | 🔨 |
| LLM 可观测 | Langfuse | token/成本/轨迹回放 | 🔨 |
| 容器 | Docker + docker-compose | 一键编排 | ✅ |
| 编排/弹性 | Kubernetes + HPA | 水平扩缩 | 🔨 |
| CI/CD | GitHub Actions | 测试/构建/部署 | 🔨 |
| 压测 | k6 / Locust | QPS/P99/成本数字 | 🔨 |

---

## 4. 核心设计亮点（面试可展开）

1. **测试门禁 Critic**：修复成功的唯一标准是 sandbox 测试通过 → 杜绝"声称修复"的幻觉。
2. **生成/审查分离**：Coder/Fixer 负责改，Tester/Reviewer/Critic 负责验，职责解耦提升可靠性。
3. **Supervisor 中央编排**：可预测、可追溯，而非 Agent 自由互调的"黑盒网络"。
4. **成本分级路由**：路由决策用便宜模型(Haiku)，最终合成用强模型(Opus 4.8)。
5. **双重有界循环**：worker 步数 + Supervisor 轮数双上限，永不失控。
6. **上下文隔离**：每个 worker 只拿子任务，不拿全历史 → 压制 token 爆炸。
7. **纵深安全**：网关边界过滤 + 核心二次校验 + 工具 AST 沙箱 + 多租户隔离。
8. **全链路 trace_id**：一次修复贯穿所有服务，可重放、可调试。

---

## 5. 快速开始

```bash
cp .env.example .env          # 填入 ANTHROPIC_API_KEY
docker compose up -d --build  # 一键拉起全部服务
# 前端  http://localhost:5173
# 网关  http://localhost:8080/docs
# sandbox-runner 自带一个有 bug 的种子项目，可直接演示"自动修复"闭环
```

## 6. 目录结构

```
.
├── frontend/                # React + TS 对话前端 + Agent 轨迹可视化
├── services/
│   ├── gateway/             # 入口网关：鉴权 / RBAC / 限流 / 防注入 / BFF
│   ├── agent-core/          # LangGraph 多 Agent 编排（Supervisor + 4 worker + Critic）
│   │   └── app/
│   │       ├── agents/      #   worker.py(ReAct基类) / roster.py(花名册) / supervisor.py
│   │       ├── tools/       #   code.py(search/read/edit/run) / base.py(注册表)
│   │       ├── multi_agent.py #  LangGraph 状态机
│   │       ├── memory.py    #   Redis 会话记忆
│   │       └── guardrails.py#   注入检测
│   ├── llm-gateway/         # 模型抽象：Claude Opus 4.8 主 / OpenAI 备 / 计费 / 熔断
│   ├── sandbox-runner/      # 代码工作区 + 沙箱测试执行（自带种子 bug 项目）
│   └── rag-service/         # pgvector 检索（保留，用于代码文档 RAG 增强）
├── packages/common/         # 共享：配置 / 结构化日志 / 可观测中间件 / Schema
├── docs/                    # 架构与 ADR 决策文档
└── docker-compose.yml
```

## 7. 路线图

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 跑通 | 多 Agent 修复闭环端到端可演示 | 🔨 进行中 |
| M2 深度 | 评测集+通过率、Harness 轨迹回放、Docker 沙箱、代码 RAG/AST、MCP、SSE 流式 | 🔨 |
| M3 落地证据 | 压测性能/成本数字、K8s、CI/CD、Langfuse | 🔨 |
| M4 放大 | 公开仓库打磨、技术博客、demo 视频 | 🔨 |

详见 [docs/](docs/) 下的架构与 ADR 决策文档。
