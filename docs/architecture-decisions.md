# 架构决策记录（ADR）· 全栈选型理由

> 本文记录平台**每一个关键技术/工具选择**：选了什么、候选有哪些、为什么选它、达到什么效果、备选的缺点、以及它自身的代价与退路。
>
> **元原则**：不存在"最好的技术"，只有"在本项目的延迟 / 成本 / 质量 / 可控性约束下最优的技术"。每条决策都是一次权衡，不是标准答案。

决策卡格式：**选型 · 候选 · 为什么 · 效果 · 备选缺点 · 风险与退路**

---

## A. 语言与框架

### ADR-01：后端语言 — Python
- **候选**：Python / Node(TS) / Go / Java
- **为什么 Python**：AI/Agent 生态唯一成熟选择——LangGraph、向量库、Anthropic/OpenAI SDK、评测工具全是 Python 一等公民；招聘 JD 也都要 Python。
- **效果**：生态零摩擦，开发速度最快，团队招人最容易。
- **备选缺点**：Node 的 Agent 生态薄、Go/Java 几乎没有成熟 Agent 框架，要大量自研。
- **风险与退路**：Python 性能弱、GIL 限制并发 → 用 async I/O（FastAPI 全异步）规避（Agent 是 I/O 密集而非 CPU 密集，GIL 影响小）；真有 CPU 热点再用 Rust/Go 写微服务旁挂。

### ADR-02：Web 框架 — FastAPI
- **候选**：FastAPI / Flask / Django
- **为什么 FastAPI**：原生 async（Agent 大量等待 LLM/检索，异步是刚需）+ Pydantic 集成（结构化输出/类型校验）+ 自动 OpenAPI 文档。
- **效果**：高并发下连接不阻塞；接口契约即文档；类型安全减少线上错误。
- **备选缺点**：Flask 默认同步、扩展零散；Django 太重，ORM/admin 这些 Agent 用不上，反成负担。
- **风险与退路**：FastAPI 生态比 Django 小 → 用得到的中间件都成熟，够用。

### ADR-03：数据校验 — Pydantic v2
- **候选**：Pydantic v2 / dataclass / 手写校验
- **为什么**：v2 用 Rust 内核，校验快；是"结构化输出"的落地工具（LLM 返回 → Pydantic 校验 → 失败重试）。
- **效果**：跨微服务的数据契约统一、强类型、自带序列化。
- **备选缺点**：dataclass 不校验值；手写校验易漏、难维护。

---

## B. Agent 编排

### ADR-04：编排框架 — LangGraph
- **候选**：LangGraph / LangChain AgentExecutor / LlamaIndex / CrewAI / AutoGen / 自研
- **为什么 LangGraph**：显式状态图——循环/分支/回退/并行/断点全可控可视；子图可嵌套（多 Agent 的基础）；支持 checkpoint 回放。
- **效果**：Agent 执行路径**可追溯、可调试、可干预**，直接服务"结果可追溯"。
- **备选缺点**：LangChain AgentExecutor 是黑盒循环、出错难查；CrewAI/AutoGen 封装太死、可观测弱；自研要重写 checkpoint/回放。
- **风险与退路**：API 偏底层、状态要自己设计 → 用 `TypedDict` 显式建模 state，字段分明。

### ADR-05：多 Agent 拓扑 — Supervisor + 专职工人
- **候选**：Supervisor(中央调度) / Network(点对点) / Hierarchical / Sequential
- **为什么 Supervisor**：所有调度过中央节点 → 路径可预测、每次派发可记录；企业要的就是"可控、可复盘"。
- **效果**：协作过程能可视化成树、能重放、能插人工审核。
- **备选缺点**：Network 路径不可预测、易死循环、几乎无法调试（最危险）；Sequential 太僵硬，一环错全错；Hierarchical 在 Agent 少时是过度设计。
- **风险与退路**：Supervisor 是单点+瓶颈 → 设计成无状态可水平扩 + 只做轻量路由决策。

### ADR-06：推理范式 — 轻 Plan + ReAct
- **候选**：ReAct / Plan-and-Execute / ReWOO / Reflexion
- **为什么**：先出浅计划给方向（防瞎走），再 ReAct 循环执行（能根据中间结果动态调整）。
- **效果**：兼顾"有规划"和"能应变"，可解释性强。
- **备选缺点**：纯 Plan-Execute 计划僵硬、中途出错不改；ReWOO 不能动态调整；Reflexion 成本翻倍。
- **风险与退路**：ReAct 会绕圈烧 token → 步数硬上限 + 低 temperature。

### ADR-07：工具调用机制 — 结构化 JSON + Pydantic 校验
- **候选**：厂商原生 function calling / 结构化 JSON 动作 / 文本解析
- **为什么**：JSON 动作跨 Claude/OpenAI 完全通用；顺带命中"结构化输出"；结果可审计。
- **效果**：一套循环逻辑跑遍所有模型，切换零成本。
- **备选缺点**：原生 FC 各厂协议不同（Claude 的 tool_use/tool_result 配对严格），跨厂商切换成本高。
- **风险与退路**：模型偶发不守格式 → `_extract_json` 容错 + 解析失败降级。LLM 网关**同时保留原生 FC**，单轮场景可用。

---

## C. RAG 与检索

> 详细的"为什么 A 不 B"对比见 [decision-cards-rag.md](decision-cards-rag.md)（决策卡 1-5）。此处只列结论。

### ADR-08：检索方式 — Hybrid（向量 + BM25，RRF 融合）
- **为什么**：向量管语义、BM25 管精确词（型号/编号/专名），互补提召回。
- **备选缺点**：纯向量漏精确匹配；纯 BM25 不懂同义改写。

### ADR-09：精排 — Cross-encoder Rerank（两阶段检索）
- **为什么**：bi-encoder 快召回 top-50，cross-encoder 准精排 top-5，降噪即降幻觉。
- **备选缺点**：不重排则 top-k 噪声多；MMR 只去重不提精度。

### ADR-10：分块 — Contextual Retrieval
- **为什么**：embed 前给每块加 LLM 生成的上下文摘要，解决"块脱离上下文"。
- **效果**：显著降低检索失败率（方向性，具体数以本项目评测集为准）。
- **代价与对策**：摄取要逐块调 LLM → 便宜模型 + prompt caching 摊薄。

### ADR-11：检索范式 — Agentic RAG
- **为什么**：Agent 自己决定是否检索/检索什么/检索几轮，避免无谓检索的噪声，支持多跳。
- **备选缺点**：静态管道闲聊也检索（浪费+噪声）；复杂问题一次检索不够。

### ADR-12：向量库 — pgvector（起步）
- **候选**：pgvector / Qdrant / Milvus / Pinecone
- **为什么**：复用 Postgres，一套库搞定业务+向量+多租户，少一个组件少一份故障面。
- **效果**：运维成本最低，中小数据量够用（IVFFlat/HNSW + cosine）。
- **备选缺点**：专用库（Qdrant/Milvus）多一个中间件要运维和同步；Pinecone 数据出境+贵，与私有化冲突。
- **风险与退路**：>千万向量性能不如专用库 → 检索已封装在 `rag-service`，量级上来换 Qdrant，上层无感。

### ADR-13：Embedding — 接口抽象（默认 OpenAI，可换 BGE-M3）
- **为什么**：抽象 `Embedder` 接口；多语言/私有化场景换 BGE-M3（中文强、可本地）。
- **风险与退路**：换模型=维度变=**全库重 embed** → 维度配置从一开始固定并记录。

---

## D. 模型与 LLM 网关

### ADR-14：主模型 — Claude Opus 4.8，OpenAI 备选
- **候选**：Opus 4.8 / OpenAI / 国内模型 / 开源自托管
- **为什么**：Opus 4.8 工具调用与 Agent 推理能力强；OpenAI 作冗余备份。（用户明确排除国内模型）
- **备选缺点**：单一厂商 = 供应商锁定 + 单点风险。
- **风险与退路**：闭源依赖外部 → 网关抽象层让换模型只改一处。

### ADR-15：模型接入 — LLM 网关抽象层（不直连 SDK）
- **候选**：网关抽象 / 各服务直连 SDK
- **为什么**：把"切换/限速/计费/熔断/缓存"收口到一处；上层与厂商解耦。
- **效果**：换模型零侵入；成本与限流统一治理。
- **备选缺点**：直连 = 上层和厂商耦合，换模型要改一堆地方，计费分散。
- **风险与退路**：网关是单点 → 无状态可水平扩，只做路由不做业务。

### ADR-16：成本控制 — 模型分级路由
- **为什么**：路由/改写等简单步骤用便宜模型（Haiku/4o-mini），最终合成/审查用 Opus。
- **效果**：在质量几乎不降的前提下大幅省 token——multi-agent 控成本的关键。
- **备选缺点**：全程用 Opus → 成本爆炸；全程用便宜模型 → 质量崩。

### ADR-17：重试与韧性 — tenacity + 主备故障转移
- **为什么**：指数退避重试瞬时错误；主模型连续失败自动切备用。
- **效果**：上游抖动不影响 Agent 可用性，命中"异常处理与运行监控"。

---

## E. 数据与存储

### ADR-18：关系库 — PostgreSQL
- **候选**：PostgreSQL / MySQL
- **为什么**：pgvector 扩展让它同时当向量库；JSON 支持好；生态强。
- **备选缺点**：MySQL 无原生向量，要再引入向量库。

### ADR-19：缓存/记忆/限流 — Redis
- **为什么**：一个组件复用三处——会话记忆（滑动窗口）、限流计数（共享原子计数）、消息队列（Streams）。
- **效果**：Agent pod 无状态化的支柱（状态外置到 Redis，任意副本接任意请求）。
- **备选缺点**：进程内存做记忆 → 多副本不共享、重启即丢。

### ADR-20：记忆策略 — 滑动窗口（起步）
- **候选**：滑动窗口 / 摘要记忆 / 向量记忆
- **为什么**：80% 场景够用、最简单；状态放 Redis 支持水平扩。
- **备选缺点**：超长对话丢早期信息 → 退路是叠加摘要记忆。

---

## F. 实时与异步

### ADR-21：实时推送 — SSE（非 WebSocket）
- **候选**：SSE / WebSocket / 轮询
- **为什么**：Agent 输出是**单向**流（服务器→客户端），SSE 足够且更轻、自动重连、走标准 HTTP。
- **效果**：实时推送 Agent 思考过程，体验远好于"转圈等 30 秒"。
- **备选缺点**：WebSocket 双向但更重、要额外维护连接状态，单向场景过度；轮询延迟高、浪费请求。

### ADR-22：异步任务 — 消息队列 + Worker
- **候选**：Redis Streams / Kafka / RabbitMQ / Celery
- **为什么**：长任务（批量文档摄取、长 Agent 任务）不能阻塞请求线程，丢进队列异步处理。
- **效果**：请求快速返回，重任务后台跑、可重试。
- **备选缺点**：同步处理长任务 → 连接池耗尽、请求超时。
- **风险与退路**：起步用 Redis Streams（已有 Redis，零新增组件），量级大再上 Kafka。

---

## G. 可观测与运维

### ADR-23：可观测 — OTel + Prometheus/Grafana + Langfuse
- **候选**：OTel 自建栈 / LangSmith / 纯日志
- **为什么**：OTel 统一采集（不锁厂商）；Prometheus 指标告警；Langfuse 专做 LLM Trace + token 成本 + 在线评测（且可私有化）。
- **效果**：一个 trace_id 贯穿全链路，每次调用的步骤/成本/延迟全可查。
- **备选缺点**：LangSmith 闭源 SaaS、数据出境；纯日志无法追踪分布式调用链。

### ADR-24：日志 — structlog（结构化 JSON）
- **为什么**：机器可解析、带 trace_id/request_id，分布式下能重建单次请求全貌。
- **备选缺点**：标准 logging 输出纯文本，跨服务排查困难。

### ADR-25：容器编排 — Kubernetes + HPA
- **候选**：K8s / Serverless / 裸 VM
- **为什么**：无状态服务多副本 + HPA 按负载自动扩缩 + 自愈 + 滚动发布；命中 JD"容器化/微服务"。
- **备选缺点**：Serverless 冷启动对长 Agent 任务不友好、有时长限制；裸 VM 无弹性、运维重。
- **风险与退路**：K8s 复杂度高 → 本地用 docker-compose 开发，K8s 清单只在 `deploy/k8s` 维护。

---

## H. 前端

### ADR-26：框架 — React + TypeScript + Vite
- **候选**：React / Vue / Svelte；Vite / Next.js / CRA
- **为什么 React**：生态最大、招聘最广；TS 类型安全（与后端 Pydantic 契约呼应）。
- **为什么 Vite**：开发服务器秒启、HMR 快；本项目是纯前端 SPA，不需要 Next.js 的 SSR。
- **备选缺点**：Next.js 带 SSR/路由全家桶，本场景用不上反增复杂度；CRA 已停更、慢。

---

## I. 安全与可控

### ADR-27：鉴权 — JWT（无状态）
- **候选**：JWT / Session(服务端存)
- **为什么**：无状态，网关多副本不需共享 session 存储；tenant_id/role 进 claim，天然支持多租户。
- **效果**：水平扩无障碍；租户隔离从 token 强制（不信客户端传参）。
- **备选缺点**：Session 要服务端集中存储，多副本下成瓶颈。
- **风险与退路**：JWT 不能即时吊销 → 短过期 + Redis 黑名单兜底。

### ADR-28：防注入 — 纵深防御 + 工具沙箱
- **为什么**：网关边界预过滤 + agent-core 核心再查（defence in depth）；工具用 AST 白名单而非 eval。
- **备选缺点**：只在一处过滤易被绕过；eval 执行工具参数 = 代码注入漏洞。
- **风险与退路**：正则会被绕过 → 生产叠加语义检测模型，正则只是第一道。

### ADR-29：幻觉治理 — 引用强制 + groundedness + Critic
- **为什么**：三道闸——强制引用溯源、确定性 groundedness 检查、独立 Critic 审查（生成/审查分离）。
- **备选缺点**：只靠 prompt 要求"别编"无强制力；同模型自审是既当运动员又当裁判。

---

## 如何使用本文档（面试场景）

1. 面试官指任一组件问"为什么用它" → 翻到对应 ADR，按"为什么 + 备选缺点 + 退路"三段式作答。
2. 被追问"有什么问题/瓶颈" → 答"风险与退路"那栏，**主动暴露代价 + 给迁移路径**，这比假装没缺点更显成熟。
3. 被问"如果数据涨 100 倍" → 串起各 ADR 的"退路"栏，讲演进路线。
