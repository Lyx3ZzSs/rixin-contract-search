# Phase 2 工作台闭环设计

日期：2026-06-23

## 背景与目标

Phase 1.1 已完成真实 qmd MCP、真实 qmd 集合、真实 OpenAI-compatible LLM 的端到端验收。当前系统能从自然语言筛选条件创建任务，通过 qmd 检索合同集合，使用 LangGraph Agent 输出文档级判断，并通过 SSE 和结果 API 展示证据。

Phase 2 的目标是把这条单次筛选链路产品化成可日常使用的合同筛选工作台。核心用户是内网业务/法务人员：输入筛选条件，等待 Agent 产出文档级判断，人工确认或改判，补充备注，并导出可交付结果。

Phase 2 不做合同上传入库、不做 qmd 集合管理、不做登录/SSO/多租户，也不改变后端固定 `QMD_COLLECTIONS` 的模型。旧上传、解析、artifact、下载相关能力继续作为历史保留和后续阶段基础，不属于本阶段主流程。

## 产品范围

Phase 2 采用“工作台闭环版”：

- 新建任务：首页保留自然语言筛选入口。
- 任务历史：新增可筛选任务列表，支持状态筛选、关键词搜索和时间排序。
- 任务复制：任意任务可复制查询创建新任务，不覆盖旧任务。
- 动态进度：将静态阶段条升级为细粒度阶段状态和实时任务活动流。
- 结果复核：按文档结果进行人工复核，保存复核状态、人工判断、备注、复核人和复核时间。
- 导出交付：提供 CSV/XLSX 业务汇总导出和单任务 JSON 归档导出。
- 集合摘要：只读展示当前 qmd 集合与健康状态，不允许用户选择或管理集合。
- 失败诊断：面向用户展示可理解的失败类型与建议动作。
- 本地稳定性：加固 macOS 本地 worker 运行模式，避免 RQ fork 导致的 ObjC 崩溃。

## 用户流程

1. 用户进入首页，看到当前 qmd 集合只读摘要，包括集合名、qmd 可用性和集合可访问状态。
2. 用户输入自然语言筛选条件创建任务，或从任务历史复制旧查询创建新任务。
3. 用户进入任务详情页，看到细粒度阶段进度和实时活动流。
4. Agent 解析条件后，页面显示条件摘要；qmd 检索阶段显示正在检索的 query、条件和候选数量；分类阶段显示已分析文档进度和文档判断事件。
5. 任务完成后，用户在结果列表中按 Agent 判断、复核状态、关键词筛选文档，并在证据侧栏查看判断依据。
6. 用户首次复核时输入复核人姓名，前端保存到 `localStorage`。
7. 用户对每份文档确认 Agent 判断或改判为 `included`、`uncertain`、`excluded`，并可填写备注。
8. 用户导出 CSV/XLSX 业务汇总，必要时导出 JSON 归档数据。
9. 如果任务失败，页面显示错误分类、失败阶段和建议动作。

## 数据模型与 API

Phase 2 复用现有 `screening_tasks`、`screening_document_results`、`stream_events`、`audit_events` 表。只为结果级复核扩展 `screening_document_results`。

新增字段：

- `review_status`: `unreviewed | reviewed`，默认 `unreviewed`。
- `review_decision`: `included | uncertain | excluded | null`。
- `review_note`: nullable text。
- `reviewer_name`: nullable string。
- `reviewed_at`: nullable datetime。

新增或扩展 API：

- `GET /api/screening-tasks`
  - 返回任务历史列表。
  - 支持 `status`、`q`、`sort`、`limit`、`offset`。
  - 关键词搜索覆盖 `title` 和 `raw_query`。
  - 返回任务摘要、结果计数、复核计数、创建时间、完成时间。

- `POST /api/screening-tasks/{task_id}/copy`
  - 复制原任务 `raw_query` 和 `title` 创建新任务并入队。
  - 不复制旧结果、旧事件和复核记录。

- `PATCH /api/screening-tasks/{task_id}/results/{result_id}/review`
  - 请求包含 `review_status=reviewed`、`review_decision`、`review_note`、`reviewer_name`。
  - 后端设置 `reviewed_at`，写入 `audit_events`。
  - 不修改 Agent 原始 `decision`、`reason`、`evidence`。

- `GET /api/screening-tasks/{task_id}/export.csv`
  - 导出业务汇总 CSV。

- `GET /api/screening-tasks/{task_id}/export.xlsx`
  - 导出业务汇总 Excel。

- `GET /api/screening-tasks/{task_id}/export.json`
  - 导出单任务完整归档 JSON，包括任务、plan、结果、证据、复核字段、事件和关键诊断信息。

- `GET /api/qmd/status`
  - 返回当前配置集合、qmd MCP 可用性、集合是否存在、可选文档数量。
  - 只读，不提供集合选择或管理。

- `GET /api/runtime/status`
  - 返回脱敏运行状态：LLM key 是否存在、模型名、qmd URL、集合名、Redis URL、worker 模式建议。
  - 不暴露任何 secret。

动态进度继续基于 `stream_events`。如现有事件 payload 不够，优先扩充 payload，不新增进度表。

## 前端信息架构

Phase 2 前端包含三类页面：

- 首页 `/`
  - 新建任务输入框。
  - 当前 qmd 集合只读摘要。
  - 轻量运行健康摘要。
  - 最近任务入口。

- 任务历史 `/tasks`
  - 列表展示任务标题、查询摘要、状态、创建时间、完成时间、结果计数、复核进度。
  - 支持关键词搜索、状态筛选和时间排序。
  - 每行提供查看详情和复制为新任务。

- 任务详情 `/tasks/:taskId`
  - 顶部展示任务标题、状态、集合名、复制任务、导出按钮。
  - 左侧展示细粒度阶段进度和实时活动流。
  - 中间展示结果列表，支持按 Agent 判断、复核状态和关键词过滤。
  - 右侧展示证据详情和结果级复核面板。

任务详情的阶段进度包括：

1. 提交任务。
2. 理解筛选条件。
3. 检查合同集合。
4. 检索证据。
5. 分析文档。
6. 生成结果。

活动流从 SSE 事件构建，例如：

- 已解析 2 个筛选条件。
- 正在检索：GPU服务器采购。
- 返回 3 条候选。
- 设备采购合同判断为入选。

这个活动流用于解决 Phase 1.1 中“用户只看到提交后等待，最后跳到结果”的体验问题。

## 复核与导出

复核粒度为文档结果级。默认结果为 `unreviewed`。用户保存人工确认或改判后，结果变为 `reviewed`，并记录：

- 人工判断 `review_decision`。
- 备注 `review_note`。
- 复核人 `reviewer_name`。
- 复核时间 `reviewed_at`。

前端首次复核时要求输入复核人姓名，并保存到浏览器 `localStorage`。Phase 2 不引入登录，因此该姓名是业务留痕字段，不是认证身份。

CSV/XLSX 导出用于业务交付，包含：

- 任务标题、原始查询、创建时间、完成时间。
- 文档 URI、路径、标题、集合。
- Agent 判断、原因、置信度、命中条件、缺失条件。
- 人工复核状态、人工判断、备注、复核人、复核时间。
- 证据摘要，包括证据文本、分数、条件 ID、artifact ref。

JSON 导出用于归档和排查，保留完整结构，不做复杂模板。

## 错误处理与运行稳定性

前端按任务 `error_code` 显示用户可读失败提示：

- `agent_llm_not_configured`：LLM API key 未配置或模型不可用。
- `qmd_unavailable`：qmd MCP 不可访问。
- `qmd_collection_missing`：配置集合不存在或无文档。
- `worker_unexpected_error`：worker 执行异常，提示检查 worker 日志。
- `enqueue_failed`：Redis/RQ 队列不可用。

本地运行加固：

- macOS 本地 worker 默认使用无 fork 的 `SimpleWorker`，或通过配置选择 worker class。
- API/worker 启动时输出脱敏诊断，包括 env 文件路径、LLM key 是否存在、模型名、qmd URL、集合名、Redis URL、worker 模式。
- 日志和接口不得输出真实 LLM key。

健康摘要只服务内网调试，不替代登录或权限系统。

## 测试与验收

后端测试覆盖：

- 任务历史列表、状态筛选、关键词搜索、时间排序、分页。
- 复制任务创建新任务且不复制旧结果/复核记录。
- 结果复核保存、审计事件写入、Agent 原始判断不被覆盖。
- CSV、XLSX、JSON 导出字段完整。
- qmd/status 和 runtime/status 脱敏。
- 本地 worker 模式选择。

前端测试覆盖：

- 历史页筛选、排序和复制任务交互。
- 任务详情动态阶段和活动流渲染。
- 结果列表按 Agent 判断、复核状态和关键词过滤。
- 复核人输入、本地保存、复核提交。
- 导出按钮在完成/失败/处理中状态下的可用性。
- 失败任务错误文案。

回归测试保留 Phase 1.1 主链路：

- 创建真实筛选任务。
- SSE 返回 snapshot、task_created、task_started、criteria_parsed、qmd_checking、qmd_searching、qmd_retrieved、document_classified、progress、task_completed。
- 结果证据包含 `text`、`score`、`condition_id`、`artifact_ref`。
- LLM 配置缺失和 qmd 不可用可诊断。

手工验收至少覆盖：

1. 成功任务：完成筛选、复核一份文档、导出 CSV/XLSX/JSON。
2. qmd 故障任务：页面显示 qmd 不可用和建议动作。
3. LLM 配置故障：页面显示 LLM 配置问题，不误导用户。
4. 本地 macOS worker：不再因 RQ fork 触发 ObjC 崩溃。

Phase 2 完成标准：业务用户可以从历史任务进入结果，理解任务进度，复核并导出可交付清单；开发/运维人员能快速判断失败卡在 LLM、qmd、队列还是 worker。
