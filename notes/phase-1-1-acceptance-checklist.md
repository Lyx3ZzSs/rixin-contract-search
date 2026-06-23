# Phase 1.1 验收清单

验收日期：2026-06-23

## 范围

Phase 1.1 验收当前 qmd 合同集合筛选主链路：创建筛选任务、真实 qmd MCP 检索、Agent 分类、SSE 事件、结果 API 和证据展示数据。验收不包含合同上传、解析入库、合同库管理、导出、人工复核、登录或复杂 RBAC。

## 环境

- qmd CLI：`/Users/liyuanxin/.nvm/versions/node/v22.12.0/bin/qmd`
- qmd index：`/Users/liyuanxin/.cache/qmd/index.sqlite`
- qmd MCP：running，PID `88143`
- 验收集合：`contract_docs`
- 集合文档数：3
- 验收查询：`软件开发服务合同`
- 应用模式：单租户内网模式，`INTERNAL_OWNER_ID=internal-user`
- Agent 模式：必须配置 OpenAI-compatible LLM；测试环境可显式注入测试 LLM，但运行时不提供规则替身

## 验收项

- [x] qmd 可用：`qmd status` 返回 MCP running。
- [x] 集合存在：`qmd ls contract_docs` 返回 3 个 qmd 文档。
- [x] qmd 检索可用：`qmd search 合同 -c contract_docs` 返回合同文档片段。
- [x] LLM 配置必填：`AGENT_LLM_API_KEY` 为空或 `AGENT_LLM_MODEL=fake` 会被配置校验拒绝。
- [x] 任务可创建：`POST /api/screening-tasks` 返回 200，并返回 `events_url` 和 `results_url`。
- [x] worker 可完成：同步执行 `run_screening_task(task_id)` 后任务状态为 `completed`。
- [x] SSE 正常：`GET /api/screening-tasks/{task_id}/events` 返回 `snapshot`、`task_created`、`task_started`、`criteria_parsed`、`qmd_checking`、`qmd_searching`、`qmd_retrieved`、`document_classified`、`progress`、`task_completed`。
- [x] 结果证据可读：`GET /api/screening-tasks/{task_id}/results` 返回 3 个 included 文档，证据包含 `text`、`score`、`condition_id`、`artifact_ref`。
- [x] 失败可诊断：未授权访问本机 qmd MCP 时，任务进入 `failed`，`error_code=qmd_unavailable`，SSE 返回 `task_failed`，错误信息包含连接失败原因。
- [x] 文档口径清理：README 明确当前主流程不做上传、解析入库和复杂登录，旧表为历史保留/后续阶段兼容基础。

## 验收记录

真实 qmd 成功路径：

```text
CREATE 200
SUMMARY 200 status=completed progress_percent=100 documents=3 included=3 uncertain=0 excluded=0
RESULTS 200 included:
- qmd://contract_docs/software-development-contract.md
- qmd://contract_docs/data-processing-confidentiality-contract.md
- qmd://contract_docs/equipment-purchase-contract.md
SSE_STATUS 200
```

真实 LLM + qmd 成功路径（2026-06-23 11:13 CST）：

```text
task_id=89409fe8-36b6-4025-bda9-db87c9ee14fe
query=哪份合同采购了GPU服务器和存储服务器？
SUMMARY 200 status=completed progress_percent=100 documents=3 included=1 uncertain=2 excluded=0
included:
- qmd://contract_docs/equipment-purchase-contract.md
evidence_fields=text, score, condition_id, artifact_ref
SSE_STATUS 200
SSE_EVENTS snapshot, task_created, task_started, criteria_parsed, qmd_checking, qmd_searching, qmd_retrieved, document_classified, progress, task_completed
REGRESSION backend pytest: 55 passed, 2 warnings
REGRESSION frontend vitest: 6 passed
REGRESSION frontend build: passed
```

失败诊断路径：

```text
SUMMARY 200 status=failed current_stage=failed
error_code=qmd_unavailable
error_message=Unable to reach qmd MCP: [Errno 1] Operation not permitted
SSE_STATUS 200
terminal_event=task_failed
```

LLM 配置失败路径：

```text
status=failed
error_code=agent_llm_not_configured
stage=planning
```

## 后续不在 Phase 1.1 内

- 任务历史页。
- CSV/JSON/XLSX 导出。
- 人工复核、改判和备注。
- qmd 集合管理页。
- 合同上传、解析、artifact 写入和 qmd 入库主流程。
- 登录、SSO、多租户权限矩阵。
