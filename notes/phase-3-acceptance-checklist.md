# Phase 3 验收清单

日期：2026-06-24

Phase 3 验收可信证据筛选增强，不验收上传、OCR、解析、索引或 qmd 集合管理。

## 后端

- [ ] `ScreeningPlanPayload` 支持 v1 兼容和 v2 条件字段。
- [ ] `condition_verdicts` 可保存每个文档、每个条件的 verdict。
- [ ] `screening_document_results` 包含 `decision_basis`、`uncertain_reasons`、`evidence_support_rate`、`verification_status`。
- [ ] `QmdClient` 支持 `doc_toc`、`doc_grep`、`doc_read`、`doc_query`、`doc_elements`。
- [ ] qmd document URI 不允许路径逃逸。
- [ ] deep-read 失败时单文档降级为 `uncertain`，不强行入选。
- [ ] `/api/screening-tasks/{task_id}/condition-verdicts` 返回条件矩阵数据。
- [ ] `/api/screening-tasks/{task_id}/evidence-ledger` 返回证据账本。
- [ ] `/api/qmd-documents/preview` 可返回上下文摘要或明确错误。
- [ ] `/api/qmd-documents/download` 在无安全下载链接时返回 `qmd_download_unavailable`。
- [ ] `/api/agent-evals/run` 输出 precision、recall、uncertain rate、evidence support rate。

## 前端

- [ ] 任务详情页保留 Phase 2 三桶结果、复核和导出能力。
- [ ] 条件矩阵显示满足、不满足、未知、冲突。
- [ ] 证据账本显示证据角色和来源工具。
- [ ] 点击证据可加载原文上下文。
- [ ] 下载按钮只在后端声明可用时显示。
- [ ] `uncertain` 结果显示具体不确定原因。

## 回归

- [ ] `cd backend && ../.venv/bin/pytest`
- [ ] `cd frontend && npm test -- --run`
- [ ] `cd frontend && npm run build`
