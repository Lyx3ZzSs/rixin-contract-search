# Phase 3 可信证据筛选增强设计

日期：2026-06-24

## 背景与目标

Phase 2 已把 qmd-first 合同筛选链路产品化为工作台：用户可以创建筛选任务、查看动态进度、复核文档级结果并导出 CSV/XLSX/JSON。当前系统的主要瓶颈不再是任务闭环，而是筛选判断的可信度：Agent 目前以 qmd `query` 片段召回为主要证据，按文档一次性分类，缺少条件级核验、证据质量分层、冲突证据识别和可回归的准确率评测。

Phase 3 的目标是把筛选 Agent 从“片段召回后判断”升级为“候选召回后逐条件核验”。检索层固定使用 OpenDataLab MinerU-Document-Explorer，通过其 qmd MCP 能力完成候选召回和文档内 deep-read 核验。Phase 3 不建设上传、OCR、解析、索引或集合管理闭环。

设计依据：

- MinerU-Document-Explorer 提供 qmd CLI/MCP、文档集合、检索、doc read/query/grep/elements 等能力，适合作为合同知识库与 deep-read 检索层。
- OpenAI evals 思路强调使用测试集和判定标准持续评估模型输出，而不是依赖单次人工观察。
- OpenAI structured outputs 思路强调用结构化 schema 约束模型输出，减少 JSON 可解析但业务字段漂移的问题。

参考资料：

- https://github.com/OpenDataLab/MinerU-Document-Explorer
- https://raw.githubusercontent.com/OpenDataLab/MinerU-Document-Explorer/main/docs/mcp.md
- https://raw.githubusercontent.com/OpenDataLab/MinerU-Document-Explorer/main/docs/architecture.md
- https://platform.openai.com/docs/guides/evals
- https://platform.openai.com/docs/guides/structured-outputs

## 产品范围

Phase 3 采用“可信证据增强版”：

- ScreeningPlan 2.0：把自然语言筛选条件拆成可核验的结构化条件。
- 多策略初筛：继续使用 qmd `query` 做候选文档召回，支持条件别名、金额/日期/主体改写和多查询策略。
- Deep Read 核验：对候选文档调用 MinerU deep-read 类工具做文档内搜索、章节定位和上下文读取。
- 条件级判定：每个候选文档对每个条件独立输出 `satisfied | not_satisfied | unknown | conflicting`。
- 文档级决策：由条件级判定汇总为 `included | uncertain | excluded`，并记录明确不确定原因。
- 证据账本：区分召回片段、支持证据、反驳证据和缺失证据，保留核验方法与来源。
- 证据驱动预览：用户可从证据跳转到原文上下文；下载仅在 MinerU/qmd 暴露安全源文件时作为可选能力。
- Agent 评测：建立小型 golden set，持续衡量 precision、recall、uncertain rate 和 evidence support rate。

Phase 3 不做：

- 页面上传合同。
- OCR、解析、artifact 写入或 qmd 索引任务管理。
- qmd 集合创建、删除、重建或集合权限管理。
- 多租户 RBAC、SSO 或复杂审批流。
- 自研向量库、替换 MinerU-Document-Explorer 或绕过 qmd 直读本地文件。

## 推荐架构

当前 Phase 2 链路是：

```text
plan -> qmd query -> aggregate snippets -> LLM classify
```

Phase 3 升级为：

```text
plan v2
  -> 多策略 qmd query 初筛
  -> 候选文档聚合
  -> MinerU deep-read 核验
  -> 条件级 verdict
  -> 文档级 decision
  -> 证据账本与评测指标
```

关键边界：

- qmd `query` 是候选召回，不直接等同最终证据。
- deep-read 核验用于确认候选片段上下文、补足缺失条件、发现反向证据或冲突证据。
- LLM 分类器必须输出结构化条件级 verdict；schema 校验失败时不能强行入选。
- `uncertain` 是一等结果，必须带原因码，而不是兜底文案。

## ScreeningPlan 2.0

`screening_plans.plan_json` 继续作为任务计划持久化载体，升级为兼容旧字段的 v2 结构。旧 Phase 2 plan 可以继续读取，新的 Phase 3 plan 增加：

- `plan_version`: 固定为 `2`。
- `condition_type`: `amount | date | party | clause_presence | clause_absence | semantic_risk | keyword`。
- `operator`: `gte | lte | eq | contains | not_contains | before | after | semantic_match`。
- `value`: 归一化目标值，例如金额数值、日期 ISO 字符串、主体名或条款描述。
- `normalization_hint`: 金额单位、日期格式、主体别名、关键词同义词。
- `qmd_queries`: 初筛查询列表。
- `verification_strategy`: `query_only | grep_then_read | doc_query | toc_guided_read`。
- `required_evidence_count`: 默认 `1`。
- `negative_evidence_allowed`: 布尔值，用于条款缺失、排除条件或冲突核验。

示例：

```json
{
  "target": "qmd_document",
  "plan_version": 2,
  "conditions": [
    {
      "id": "amount_threshold",
      "description": "合同总价大于等于100万元",
      "condition_type": "amount",
      "operator": "gte",
      "value": 1000000,
      "normalization_hint": {"currency": "CNY", "unit_aliases": ["万元", "人民币"]},
      "qmd_queries": ["合同总价 人民币 金额", "含税总价 100万元"],
      "verification_strategy": "grep_then_read",
      "required_evidence_count": 1,
      "negative_evidence_allowed": false,
      "structured": true
    }
  ],
  "decision_policy": "all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict"
}
```

## MinerU/qmd 集成

现有 `QmdClient` 已支持 MCP 初始化、`status` 和 `query`。Phase 3 在同一客户端边界内扩展 deep-read 方法，而不是引入新的检索抽象。

建议扩展能力：

- `list_tools()`：启动或健康检查时确认 qmd MCP 是否暴露 deep-read 工具。
- `doc_toc(document_uri)`：读取文档目录或章节结构，用于长合同定位。
- `doc_grep(document_uri, pattern)`：按金额、日期、主体名、条款关键词做文档内搜索。
- `doc_read(document_uri, page_or_anchor, window)`：读取证据附近上下文。
- `doc_query(document_uri, question)`：对单文档做限定范围问答式核验。
- `doc_elements(document_uri, page_or_anchor)`：在 MinerU 可用时读取表格、标题、段落等结构元素。

Phase 3 只消费 MinerU 返回的安全文档引用、页码、章节锚点、片段和上下文。不得把 qmd 文档路径当作本地文件路径直读。

## 条件级判定与证据账本

新增 `condition_verdicts` 表，保存每个文档对每个条件的独立核验结果：

- `id`
- `task_id`
- `document_uri`
- `condition_id`
- `verdict`: `satisfied | not_satisfied | unknown | conflicting`
- `confidence`
- `supporting_evidence`
- `contradicting_evidence`
- `missing_reason`
- `verification_method`
- `created_at`

扩展 `screening_document_results`：

- `decision_basis`: 条件级汇总摘要。
- `uncertain_reasons`: `missing_evidence | conflicting_evidence | low_retrieval_confidence | ambiguous_requirement | model_validation_failed | verification_failed`。
- `evidence_support_rate`: 已满足条件中有 deep-read 支持证据的比例。
- `verification_status`: `query_only | deep_read_verified | partially_verified | verification_failed`。

证据账本按 evidence item 记录：

- 证据角色：`retrieval_candidate | supporting | contradicting | missing_context`。
- 来源工具：`query | doc_grep | doc_read | doc_query | doc_elements`。
- 文档引用：`document_uri`、`document_path`、`collection`。
- 定位信息：页码、章节锚点、行号或 MinerU 返回的元素 ID。
- 文本片段与上下文摘要。
- qmd score、核验置信度、条件 ID。
- 是否参与最终判定。

## 文档预览与可选下载

Phase 3 加入证据驱动的文档预览，但不建设独立文件管理。

前端能力：

- 在结果详情和证据账本中提供“预览原文/定位证据”入口。
- 点击证据后打开文档上下文侧栏，显示页码、章节、命中片段和前后文。
- 条件矩阵单元格可跳到该条件在该文档中的支持或反驳证据。
- 如果 MinerU/qmd 返回安全源文件 URL 或 open link，则显示“打开源文件”或“下载”按钮。

后端 API：

- `GET /api/qmd-documents/preview?document_uri=...`
  - 返回文档标题、collection、可展示的 TOC/摘要和可用操作。

- `GET /api/qmd-documents/evidence-context?document_uri=...&condition_id=...&page=...`
  - 返回证据上下文，优先来自 `doc_read` 或 `doc_elements`。

- `GET /api/qmd-documents/open-link?document_uri=...`
  - 仅当 qmd/MinerU 返回安全可打开链接时返回。

- `GET /api/qmd-documents/download?document_uri=...`
  - 可选接口。只有 qmd/MinerU 提供安全下载能力时启用；否则返回明确的 `qmd_download_unavailable`。

审计：

- 预览上下文写入 `document_previewed`。
- 打开源文件或下载写入 `document_opened` / `document_downloaded`。
- 审计 payload 只记录 document URI、task ID、condition ID、工具名和时间，不记录整段合同正文或本地路径。

当前旧接口 `/api/contracts/{contract_id}/download` 只服务本地 `contract_files` 记录，不作为 qmd 文档下载接口复用。

## API 设计

新增或扩展接口：

- `GET /api/screening-tasks/{task_id}/condition-verdicts`
  - 返回任务下所有文档的条件级判断矩阵。

- `GET /api/screening-tasks/{task_id}/evidence-ledger`
  - 返回证据账本，面向任务详情页、排查和审计。

- `POST /api/agent-evals/run`
  - 开发/内网调试接口，运行指定评测集。

- `GET /api/agent-evals/{run_id}`
  - 查看评测指标、失败样本和结构化输出失败原因。

现有接口保持兼容：

- `GET /api/screening-tasks/{task_id}/results` 继续返回三桶结果。
- `GET /api/screening-tasks/{task_id}/events` 继续作为 SSE 事件来源。
- CSV/XLSX/JSON 导出保留 Phase 2 字段，并在 Phase 3 追加条件 verdict、uncertain reasons、verification status 和 evidence support rate。

## 前端体验

Phase 3 不重做工作台，只增强任务详情页。

新增区域：

- 条件矩阵：行是文档，列是筛选条件，单元格显示 `满足 | 不满足 | 未知 | 冲突`。
- 证据账本侧栏：展示支持证据、反驳证据、缺失原因和核验工具。
- 不确定原因：`uncertain` 文档必须显示具体原因码和建议动作。
- 文档上下文预览：从证据跳转到 MinerU deep-read 返回的原文上下文。
- 评测面板：开发/调试入口展示最近评测指标和失败样本。

交互原则：

- 文档级结果仍按 Phase 2 的入选、待复核、排除三桶展示。
- 条件矩阵服务快速定位问题，不替代结果列表。
- 证据预览是复核辅助，不暴露本地文件路径。
- 下载按钮不是稳定必有能力；只有后端确认 qmd/MinerU 支持安全下载时才显示。

## 错误处理

新增错误码：

- `qmd_deep_read_unavailable`：MCP 可用，但 deep-read 工具不可用或返回异常。
- `evidence_verification_failed`：候选召回成功，但文档内核验失败。
- `condition_verdict_invalid`：LLM 输出的条件级判断不符合 schema。
- `qmd_preview_unavailable`：无法获取文档预览上下文。
- `qmd_download_unavailable`：qmd/MinerU 未提供安全下载能力。
- `eval_dataset_invalid`：评测集格式不合法。
- `eval_run_failed`：评测运行失败。

处理原则：

- 单文档 deep-read 失败时，该文档进入 `uncertain`，`verification_status=verification_failed`。
- 如果所有候选文档都无法核验，任务可以失败为 `evidence_verification_failed`。
- schema 校验失败先做一次修复；仍失败则对应条件 verdict 记为 `unknown`，不得强行入选。
- qmd `query` 故障和 deep-read 故障分开显示，因为排查路径不同。
- 预览或下载失败不改变筛选结果，只影响复核辅助功能。

## Agent 评测

新增小型 golden set 能力，用于持续衡量 Phase 3 改动效果。

评测样本包含：

- 原始筛选查询。
- 期望入选、排除、不确定文档 URI。
- 关键条件的人工 verdict。
- 可选人工证据片段或页码。

评测指标：

- `precision`: Agent 入选文档中人工也应入选的比例。
- `recall`: 人工应入选文档被 Agent 找到的比例。
- `uncertain_rate`: 不确定结果比例。
- `evidence_support_rate`: 入选文档中关键条件具备支持证据的比例。
- `schema_failure_rate`: 结构化输出校验失败比例。
- `verification_failure_rate`: deep-read 核验失败比例。

评测不要求替代人工法务判断，只用于开发回归和 prompt/model/检索策略比较。

## 测试与验收

后端测试覆盖：

- ScreeningPlan v2 schema 校验与旧 plan 兼容。
- qmd client deep-read 工具调用、错误转换和安全 document URI 处理。
- 条件级 verdict 持久化与文档级汇总。
- evidence ledger 输出字段完整，不暴露本地路径或密钥。
- preview/open-link/download 的可用与不可用分支。
- schema 修复失败时 verdict 降级为 `unknown`。
- golden set 评测指标计算。

前端测试覆盖：

- 条件矩阵渲染和单元格筛选。
- 证据账本支持/反驳/缺失证据展示。
- `uncertain` 原因码展示。
- 文档上下文预览成功和失败状态。
- 下载按钮只在后端声明可用时显示。
- Phase 2 历史、复核、导出、SSE 主流程不回退。

手工验收至少覆盖：

1. 成功筛选：入选文档的关键条件全部有 `satisfied` verdict，且能打开对应证据上下文。
2. 缺失证据：文档进入 `uncertain`，显示 `missing_evidence`。
3. 冲突证据：同一条件存在支持和反驳证据时，显示 `conflicting`。
4. deep-read 故障：单文档降级为 `uncertain`，任务整体不中断。
5. 预览不可用：筛选结果仍可查看，预览区域显示可执行错误提示。
6. golden set：能运行一次评测并输出 precision、recall、uncertain rate、evidence support rate。

Phase 3 完成标准：用户不仅能看到哪些合同被入选，还能逐条件追溯为什么入选、为什么不确定、证据来自哪里、是否经过文档内核验；开发人员能用评测集比较 Agent 版本变化对准确率和证据可信度的影响。
