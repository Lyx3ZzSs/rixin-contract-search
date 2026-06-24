# 合同智能筛选 Agent

Phase 2 提供一个可本地运行的合同智能筛选工作台：合同文档由外部部署的 MinerU-Document-Explorer/qmd 知识库统一管理，用户只输入自然语言筛选条件，后台通过 qmd MCP 检索企业合同集合并生成文档级筛选结果，并在前端完成历史追踪、人工复核和导出。

后台筛选主流程由 LangGraph Agent 编排：通过 OpenAI-compatible LLM 规划筛选条件、调用 qmd MCP 检索、必要时补充检索查询、聚合证据并输出文档级判断。运行时必须配置 LLM API key；测试环境通过显式注入测试 LLM 保持可重复，不提供运行时规则替身。

## 本地启动

依赖 Docker 和 Docker Compose。

```sh
cp .env.example .env
# 另起终端启动外部 MinerU-Document-Explorer/qmd MCP 服务
qmd mcp --http --daemon
# 确认 QMD_MCP_URL / QMD_COLLECTIONS 指向 qmd MCP 和已索引合同集合
docker compose up --build
```

打开 `http://localhost:5173`。系统面向内网单租户使用，不需要在页面输入 Token。

前端默认请求同源 `/api` 路径，本地由 Vite dev server 代理到后端，不需要配置本地 CORS 端口白名单。

当前主流程不在页面上传合同，也不执行合同入库。请先在外部 MinerU-Document-Explorer/qmd 服务中维护企业合同集合，例如 `qmd collection add <合同目录> --name company_docs`，并确保 `qmd status` 能看到对应集合。

## 本机调试后端

如果希望在宿主机直接调试后端，建议用 Docker 只启动依赖服务，API 和 worker 在本机进程中启动：

```sh
cp .env.example .env
qmd mcp --http --daemon
docker compose up postgres redis
cd backend
../.venv/bin/alembic upgrade head
CONTRACT_AGENT_HOST=127.0.0.1 CONTRACT_AGENT_PORT=8000 ../.venv/bin/python -m app.main
```

另起终端启动 worker：

```sh
cd ..
PYTHONPATH=backend .venv/bin/python -m app.worker
```

本机启动前端开发服务：

```sh
cd frontend
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

后端配置固定加载项目根目录 `.env`，因此从项目根目录、`backend/` 目录或 IDE 启动 API/worker 都使用同一份配置文件；不需要复制 `backend/.env`。

IDE API 配置：

- Script path: `backend/app/main.py`
- Python interpreter: `.venv/bin/python`
- Working directory: 项目根目录
- Environment variables: 可选 `CONTRACT_AGENT_HOST=127.0.0.1;CONTRACT_AGENT_PORT=8000`

IDE worker 配置：

- Module name: `app.worker`
- Python interpreter: `.venv/bin/python`
- Working directory: 项目根目录
- Environment variables: `PYTHONPATH=backend`

启动后访问 `http://127.0.0.1:8000/healthz` 检查 API，前端仍然是 `http://localhost:5173`。

## 接入 MinerU-Document-Explorer MCP

本项目不集成或 vendor MinerU-Document-Explorer 源码。MinerU-Document-Explorer/qmd 作为独立检索服务运行，本项目只通过 MCP HTTP 接口调用它，并在 `backend/app/services/retrieval/qmd_client.py` 中把检索结果归一化为内部 `QmdResult`。

推荐运行形态：

- 本机调试：在宿主机启动 `qmd mcp --http --daemon`，后端使用 `QMD_MCP_URL=http://localhost:8181/mcp`。
- Docker 后端访问宿主机 qmd：使用 `QMD_MCP_URL=http://host.docker.internal:8181/mcp`。
- 独立服务器 qmd：使用该服务器的内网 HTTP MCP 地址，并确保 API/worker 容器可访问。

默认配置：

```sh
QMD_BACKEND=mcp
QMD_MCP_URL=http://localhost:8181/mcp
QMD_COLLECTIONS=company_docs
QMD_TOP_K=50
```

本地直接运行后端时使用 `http://localhost:8181/mcp`。后端跑在 Docker 容器内时通常使用 `http://host.docker.internal:8181/mcp`。

常用 qmd 命令：

```sh
qmd collection list
qmd status
qmd mcp --http --daemon
qmd mcp --http --daemon --port 8080
qmd mcp stop
```

MinerU-Document-Explorer 是独立 Node/TypeScript 运行时服务，负责模型加载、索引、向量存储和检索。本项目的职责边界是：发起 MCP `status`/`query` 调用、处理不可用错误、持久化候选片段、聚合文档级证据并返回筛选结果。

## LangGraph Agent 配置

默认配置：

```sh
AGENT_BACKEND=langgraph
AGENT_LLM_BASE_URL=https://api.openai.com/v1
AGENT_LLM_API_KEY=replace-with-openai-compatible-key
AGENT_LLM_MODEL=gpt-4.1-mini
AGENT_LLM_TEMPERATURE=0
AGENT_MAX_RETRIEVAL_ROUNDS=2
```

`AGENT_LLM_BASE_URL` 使用 OpenAI-compatible 接口地址。`AGENT_LLM_API_KEY` 必须配置，`AGENT_LLM_MODEL` 必须是真实模型名；`fake` 不再是有效运行时模型。Planner、Query Refiner 和 Classifier 都通过 LangGraph 调用配置的 LLM。

## 开发阶段验证

当前开发阶段不使用 Docker/Compose 作为测试验证手段。提交前使用本机 Python/Node 环境运行：

```sh
cd backend
../.venv/bin/pytest

cd ../frontend
npm test -- --run
npm run build
```

## Phase 1.1 验收口径

Phase 1.1 以真实 qmd MCP 服务和真实 qmd 集合完成端到端验收，但不改变产品边界：本项目仍只负责创建筛选任务、调用 qmd MCP、编排 Agent、持久化文档级结果并通过 SSE/结果 API 展示证据。

验收前确认：

- `qmd mcp --http --daemon` 已启动，`qmd status` 能看到 MCP running。
- `QMD_COLLECTIONS` 指向真实存在且已索引的 qmd 集合。
- API/worker 能访问 `QMD_MCP_URL`，Docker 中运行时通常使用 `http://host.docker.internal:8181/mcp`。
- `AGENT_LLM_API_KEY` 和真实 `AGENT_LLM_MODEL` 已配置；未配置 LLM 不属于真实 Agent 验收通过状态。

验收清单见 `notes/phase-1-1-acceptance-checklist.md`。

## Phase 2 工作台能力

Phase 2 在 Phase 1.1 的 qmd-first 筛选主链路上补齐日常工作台能力，但仍不把合同上传、解析或入库作为当前主流程。用户从已索引的 qmd 合同集合创建筛选任务，进入任务历史、查看动态进度、复核结果并导出交付数据。

已实现能力：

- 任务历史页 `/tasks`：支持状态筛选、关键词搜索、时间排序、查看详情和复制旧任务查询创建新任务。
- 动态进度：任务详情页从 SSE 事件构建阶段进度和活动流，展示条件解析、qmd 检查、检索、分类和完成/失败事件。
- 结果级复核：每条文档结果可保存人工判断、备注、复核人和复核时间；前端把复核人姓名保存在浏览器 `localStorage`，后端把复核记录持久化为业务审计字段并写入 `result_reviewed` 审计事件。
- 导出：完成后的单任务结果支持 `CSV`、`XLSX` 和 `JSON` 导出，包含 Agent 判断、证据摘要和人工复核字段。
- 健康摘要：首页展示 qmd 集合状态和 LLM 配置状态；`/api/runtime/status` 提供 runtime 脱敏配置、Redis URL 和 worker 模式摘要。
- 失败提示：前端按 `qmd_unavailable`、`qmd_collection_missing`、`agent_llm_not_configured`、`enqueue_failed`、`worker_unexpected_error` 等错误码展示可执行排查建议。
- 本地 worker：`RQ_WORKER_MODE=auto|simple|fork`；macOS 本地 `auto` 默认使用无 fork 的 `SimpleWorker`，也可显式设置 `RQ_WORKER_MODE=simple`。
- 权限模型：继续保持内网单租户模型，通过 `INTERNAL_OWNER_ID` 注入固定 owner；不提供登录、SSO、多租户或页面 Token。

验收清单见 `notes/phase-2-acceptance-checklist.md`。

## Phase 1 限制

- 主流程只筛选 qmd 已索引的合同集合，不提供用户上传合同、合同入库和合同库管理。
- 旧上传、解析、artifact、下载相关代码和表是历史保留/后续入库阶段的兼容基础，不属于当前主流程；当前筛选结果以 qmd 文档 URI、集合名、文档路径和证据片段为准。
- 当前运行模式是内网单租户：后端使用 `INTERNAL_OWNER_ID` 注入固定 owner，不提供页面 Token、登录、SSO 或复杂 RBAC。
- Phase 2 已补齐任务历史、复制、导出和结果级复核；仍不提供 qmd 集合管理页。
