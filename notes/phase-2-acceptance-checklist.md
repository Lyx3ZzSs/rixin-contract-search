# Phase 2 验收清单

验收日期：2026-06-23

## 范围

Phase 2 验收当前 qmd-first 合同筛选工作台：任务历史、任务复制、动态进度活动流、结果级人工复核、CSV/XLSX/JSON 导出、qmd/runtime 健康摘要、失败诊断和 macOS 本地 worker 稳定性。当前主流程仍是筛选已索引 qmd 合同集合，不验收合同上传、解析入库、qmd 集合管理、登录、SSO 或多租户权限。

## 自动验证

- [ ] 后端测试通过：

```sh
cd backend
../.venv/bin/pytest
```

- [ ] 前端 Vitest 通过：

```sh
cd frontend
npm test -- --run
```

- [ ] 前端构建通过：

```sh
cd frontend
npm run build
```

- [ ] 文档和补丁无空白错误：

```sh
git diff --check
```

## 手工烟测

环境准备：

- [ ] qmd MCP 已启动，且目标集合已索引：

```sh
qmd mcp --http --daemon
qmd status
qmd collection list
```

- [ ] `.env` 使用真实可访问配置：`QMD_MCP_URL`、`QMD_COLLECTIONS`、`AGENT_LLM_API_KEY`、`AGENT_LLM_MODEL`、`REDIS_URL`、`DATABASE_URL`。
- [ ] macOS 本地 worker 使用默认 `RQ_WORKER_MODE=auto` 或显式 `RQ_WORKER_MODE=simple`。

启动应用：

- [ ] 后端依赖服务可用：

```sh
docker compose up postgres redis
```

- [ ] 数据库迁移完成并启动 API：

```sh
cd backend
../.venv/bin/alembic upgrade head
CONTRACT_AGENT_HOST=127.0.0.1 CONTRACT_AGENT_PORT=8000 ../.venv/bin/python -m app.main
```

- [ ] worker 启动并打印脱敏 runtime 摘要：

```sh
cd ..
PYTHONPATH=backend RQ_WORKER_MODE=simple .venv/bin/python -m app.worker
```

如使用 Docker Compose，`worker` 服务应通过 `python -m app.worker` 启动，以便同样应用 `RQ_WORKER_MODE` 和脱敏启动摘要。

- [ ] 前端启动：

```sh
cd frontend
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

API 烟测：

- [ ] runtime 健康摘要不暴露 secret：

```sh
curl -s http://127.0.0.1:8000/api/runtime/status
```

- [ ] qmd 健康摘要显示 configured collections，集合存在时 `exists=true`：

```sh
curl -s http://127.0.0.1:8000/api/qmd/status
```

- [ ] 可创建筛选任务：

```sh
curl -s -X POST http://127.0.0.1:8000/api/screening-tasks \
  -H 'content-type: application/json' \
  -d '{"query":"筛选采购GPU服务器或存储服务器的合同"}'
```

- [ ] worker 完成任务后，任务摘要、SSE 事件和结果 API 可读：

```sh
curl -s http://127.0.0.1:8000/api/screening-tasks/<task_id>
curl -s http://127.0.0.1:8000/api/screening-tasks/<task_id>/events
curl -s http://127.0.0.1:8000/api/screening-tasks/<task_id>/results
```

工作台验收：

- [ ] 首页展示 qmd/runtime 健康摘要、当前集合和最近任务入口，不要求用户登录或输入 Token。
- [ ] `/tasks` 可按状态、关键词和时间排序筛选任务；复制任务会创建新任务，不覆盖原任务结果或复核记录。
- [ ] 任务详情页展示六段进度和活动流，包含条件解析、qmd 检查、检索、文档判断和完成/失败信息。
- [ ] 结果列表可按 Agent 判断、复核状态和关键词过滤，证据详情可读。
- [ ] 对一条结果保存人工复核后，页面显示复核状态、人工判断、备注、复核人和复核时间；刷新后仍可读。
- [ ] 浏览器 `localStorage` 保存复核人姓名；后端 `screening_document_results` 保存复核字段，并写入 `audit_events.event_type=result_reviewed`。
- [ ] 完成任务可下载 CSV、XLSX、JSON；导出内容包含任务信息、文档信息、Agent 判断、证据摘要和复核字段。
- [ ] qmd 停止或集合缺失时，任务失败提示能指向 qmd 服务或集合配置问题。
- [ ] LLM key/model 配置错误时，失败提示能指向 LLM 配置问题。
- [ ] worker 异常时，失败提示包含检查 worker 日志和 macOS `SimpleWorker` 模式的建议。

## 完成标准

- [ ] 自动验证全部通过。
- [ ] 成功任务能完成筛选、进入历史、复制、复核一份文档并导出 CSV/XLSX/JSON。
- [ ] 失败任务能区分 qmd、LLM、队列/worker 等主要问题。
- [ ] README 和本清单准确说明 Phase 2 当前边界：qmd-first、内网单租户、无登录、不以上传/解析为主流程。
