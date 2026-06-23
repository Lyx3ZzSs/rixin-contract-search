# PRD: 合同文件智能筛选 Agent MVP

## Executive Summary

建设一个面向企业内部合同库的 AI Agent，用于从大量合同文件中筛选出符合用户条件的合同文件。系统采用 **PaddleX/PaddleOCR 解析合同文件**、**qmd 作为检索层**、**Agent 负责编排与文件级判定**，前台通过 **SSE 事件流**展示筛选过程，最终输出合同文件名称、下载链接、命中原因和证据。

本项目当前是空 git 仓库，无现有代码、文档、测试或部署约束。因此 PRD 定义的是新建 MVP 的产品与技术基线。

## Problem Statement

公司内部合同库文件数量大、格式复杂，人工筛选耗时高且准确性不稳定。用户需要用自然语言描述筛选条件，例如“筛出 2024 年后签署、金额大于 100 万、包含自动续约的采购合同”，系统应快速返回符合条件的合同文件列表。

核心问题不是“回答合同条款问题”，而是 **文件级筛选**：哪些合同文件应被纳入结果，哪些需要复核，哪些可以排除。

## Target Users

- 法务：筛选存在特定风险或条件的合同文件
- 采购/供应链合规：筛选供应商、金额、续约、付款条件相关合同
- 财务/内控：筛选金额、付款、期限、责任条款相关合同
- 审计人员：按审计条件批量定位合同文件并导出结果

## Current State

当前仓库：

- 已初始化 git repo，分支为 `main`
- 无 commits
- 无源码、README、AGENTS.md、CLAUDE.md、package.json、pyproject.toml、docker-compose 等项目文件
- 无现成前端、后端、数据模型、API、权限、任务系统、PaddleX/qmd 集成

因此 MVP 需要从零建立技术栈、目录结构、任务模型和交互模式。

## Proposed Solution

构建一个 **Evidence Ledger Agent**：

```text
合同上传/导入
  -> PaddleX/PaddleOCR 解析
  -> 生成 Markdown + JSON + Evidence artifacts
  -> qmd 索引 Markdown
  -> 用户输入筛选条件
  -> Agent 生成 ScreeningPlan
  -> Agent 调用 qmd 多路检索
  -> 按 contract_id 聚合候选片段
  -> 文件级判定 included / uncertain / excluded
  -> SSE 推送过程事件
  -> 输出合同文件名 + 下载链接 + 原因 + 证据
```

产品前台采用三桶筛选台：

- 入选合同：证据充分，满足条件
- 待复核合同：证据不足、冲突、解析质量低或条件歧义
- 已排除合同：证据充分，不满足条件

## Scope

### In Scope

- 批量上传 PDF、扫描 PDF、图片合同
- PaddleX/PaddleOCR 解析合同，生成页面级和合同级 Markdown/JSON
- qmd 直接作为检索层使用
- 自然语言筛选条件解析为 `ScreeningPlan`
- qmd 检索候选片段
- 按合同文件聚合 qmd 结果
- Agent 文件级判定
- SSE 流式展示筛选过程
- 输出合同文件名称、下载链接、命中原因、证据片段
- 任务历史、结果导出、基础审计日志
- 下载链接鉴权和任务级访问控制

### Out of Scope

- 完整 CLM 合同生命周期管理
- 合同起草、审批、签署、归档流程
- 自研 qmd 替代品
- 条款级检索产品化
- 自动给出法律结论
- 复杂多租户 RBAC 和组织权限矩阵
- DOCX、Excel、邮件附件等全格式合同库接入，MVP 后置

## User Stories / Jobs To Be Done

1. 作为法务，我希望输入筛选条件，系统返回符合条件的合同文件名称和下载链接。
2. 作为审计人员，我希望看到筛选过程，包括解析、检索、候选数量、判定进度。
3. 作为复核人员，我希望每份入选合同都有命中原因和证据片段，而不是黑盒结果。
4. 作为业务用户，我希望结果分为入选、待复核、已排除，避免系统强行二分类。
5. 作为管理员，我希望所有下载、筛选和人工改判都有审计记录。

## Functional Requirements

### FR1. 合同上传与文件管理

- 支持批量上传 PDF、扫描 PDF、图片合同
- 每个文件生成 `contract_id`
- 保存原始文件、文件名、文件 hash、上传人、上传时间、文件大小
- 支持受保护的下载接口，不暴露原始文件路径
- MVP 默认限制：单批最多 100 份合同，单文件最多 200 页，单文件大小上限可配置

### FR2. PaddleX 解析

- 使用 PaddleX/PaddleOCR 解析合同文件
- 对每份合同生成：
  - `contract.md`：合同级合并 Markdown
  - `pages/*.md`：页面级 Markdown
  - `metadata.json`：文件、页数、解析状态、OCR/版面质量
  - `evidence.json`：页码、文本块、表格、坐标、解析置信度
- 解析状态包括：`pending`、`running`、`succeeded`、`failed`、`low_quality`
- 低 OCR 质量、空文本、页码异常、表格解析失败需进入待复核原因

### FR3. qmd 索引与检索

- qmd 索引 PaddleX 生成的合同 Markdown
- qmd 查询结果必须可映射到：
  - `contract_id`
  - `file_name`
  - `download_url`
  - `page`
  - `snippet_text`
  - `qmd_score`
  - `artifact_ref`
- 支持按任务范围、文件集合或批次限制检索
- Agent 需要限制 qmd candidate top-k，避免无限候选

### FR4. ScreeningPlan

Agent 将自然语言条件转成结构化计划：

```json
{
  "target": "contract_file",
  "conditions": [
    {
      "id": "amount",
      "operator": "gte",
      "value": 1000000,
      "qmd_queries": ["合同金额", "总价", "含税金额", "人民币"],
      "evidence_required": 1
    }
  ],
  "decision_policy": "all_conditions_must_pass_else_uncertain_if_missing_evidence"
}
```

ScreeningPlan 需保存，便于复跑、审计和调试。

### FR5. Agent 文件级判定

Agent 执行流程：

```text
parse_requirement
-> build_screening_plan
-> call_qmd
-> aggregate_by_contract
-> verify_conditions
-> classify_results
-> persist_results
-> stream_final
```

每份合同输出：

```json
{
  "contract_id": "c_001",
  "file_name": "2024-采购合同-A公司.pdf",
  "download_url": "/api/contracts/c_001/download",
  "decision": "included",
  "reason": "命中供应商、金额和签署日期条件",
  "matched_conditions": ["供应商=A公司", "金额>100万"],
  "missing_conditions": [],
  "evidence": [
    {
      "page": 3,
      "text": "合同总价为人民币120万元",
      "source": "qmd",
      "score": 0.82
    }
  ]
}
```

`uncertain` 必须是一等结果，触发原因包括：

- qmd 未召回必要证据
- 证据冲突
- PaddleX 解析质量低
- 用户条件歧义
- 权限不足
- 条件需要人工法律判断

### FR6. SSE 流式过程展示

前端通过 SSE 接收业务级事件，不做 token 级流式。

事件示例：

```json
{"type":"task_started","task_id":"t_001"}
{"type":"criteria_parsed","criteria":["供应商=A公司","金额>100万"]}
{"type":"file_parsed","contract_id":"c_001","status":"succeeded"}
{"type":"qmd_searching","query":"A公司 合同金额 100万"}
{"type":"qmd_retrieved","candidate_count":87}
{"type":"contract_classified","file_name":"A公司采购合同.pdf","decision":"included"}
{"type":"progress","reviewed":42,"included":9,"uncertain":3,"excluded":30}
{"type":"task_completed","included_count":12,"export_url":"/api/tasks/t_001/export"}
{"type":"task_failed","reason":"qmd index unavailable"}
```

SSE 需支持：

- keepalive
- event id
- reconnect 后恢复当前任务状态
- 前端 fallback polling

### FR7. 前台页面

MVP 页面：

- 上传/创建筛选任务页
- 任务进度页
- 三桶结果页
- 合同证据详情抽屉
- 下载/导出入口
- 任务历史页

结果页核心信息：

- 合同文件名
- 下载链接
- 判定：入选 / 待复核 / 排除
- 命中条件
- 缺失条件
- 关键证据
- 解析质量提示
- 人工复核操作：确认、改判、备注

### FR8. 导出

支持导出：

- Excel
- CSV
- JSON

导出字段：

- 文件名
- 下载链接
- 判定
- 命中条件
- 待复核原因
- 证据页码
- 证据片段
- 任务 ID
- 操作人
- 时间

### FR9. 权限与审计

MVP 至少支持：

- 用户登录
- 任务归属
- 任务结果访问控制
- 下载接口鉴权
- SSE 任务订阅鉴权
- 审计日志

审计事件包括：

- 文件上传
- 解析开始/完成/失败
- qmd 查询
- Agent 判定
- 人工改判
- 结果导出
- 文件下载
- 权限拒绝

## Non-Functional Requirements

### NFR1. 技术栈

推荐：

- 前端：React + Vite + TypeScript
- 后端：Python FastAPI
- Agent 编排：LangGraph 或自研轻量 workflow
- 解析：PaddleX/PaddleOCR
- 检索：qmd CLI / HTTP / MCP
- 数据库：PostgreSQL
- 队列：Redis + Celery/RQ/Dramatiq
- 文件存储：本地目录起步，后续 MinIO
- 流式：SSE
- 部署：Docker Compose 起步

### NFR2. 性能

MVP 初始目标：

- 单批 100 份以内合同
- 单文件 200 页以内
- qmd 单次检索候选上限可配置，默认 50-100
- SSE 事件按业务阶段推送，不超过每秒 5 条常规事件
- 大文件上传使用磁盘/流式处理，不将完整文件加载进内存

### NFR3. 可靠性

- 每个 pipeline 阶段可失败、可重试、可观察
- 任务状态必须持久化
- 解析失败的文件不阻塞整个批次
- qmd 不可用时任务进入失败或待重试状态
- Agent 判定失败时保留 qmd 候选和错误信息

### NFR4. 安全

- 上传文件类型 allowlist
- 文件大小和页数限制
- 下载链接走后端鉴权接口
- 禁止暴露本地文件路径
- qmd 检索需按任务/用户/项目范围隔离
- Agent 不执行合同文本中的任何指令
- 对 prompt injection、恶意 PDF、越权下载做测试

### NFR5. 可观测性

记录：

- parse duration
- qmd indexing duration
- qmd query latency
- Agent classification latency
- task p50/p95 duration
- OCR/parse failure rate
- uncertain rate
- download count
- qmd candidate count
- LLM token/cost，如果使用外部模型

## Success Metrics

### Product Metrics

- 人工筛选时间减少 30% 以上
- 入选合同结果人工接受率 >= 80%
- 待复核率可控，目标 <= 30%
- 用户能在结果中找到文件名、下载链接、理由、证据

### Retrieval / Classification Metrics

- qmd 候选召回率 >= 90%，基于人工 gold set
- 文件级误排率尽量低，MVP 目标 < 5%
- included 结果 evidence precision@3 >= 85%
- 证据引用正确率 >= 95%

### System Metrics

- SSE 断线可恢复
- 任务失败原因可解释
- 100% 下载请求可审计
- 100% 人工改判可追踪

## Risks & Mitigations

### R1. qmd 漏召回导致漏合同

Mitigation：

- 多查询扩展
- ScreeningPlan 保存所有 qmd queries
- 高风险条件默认扩大召回
- 召回不足进入 uncertain，而不是 excluded

### R2. PaddleX 解析质量影响判断

Mitigation：

- 保存 page-level JSON 和 OCR confidence
- low_quality 文件进入待复核
- 前端展示解析质量标记
- 允许人工查看原文件

### R3. Agent 误把片段证据当合同结论

Mitigation：

- 必须按 `contract_id` 聚合
- 条件级 evidence_required
- 缺证据进入 uncertain
- 不允许仅凭单一低分片段排除合同

### R4. 用户过度信任 AI 判定

Mitigation：

- 产品文案定位为“辅助筛选”
- 结果分三桶
- 显示证据与不确定原因
- 提供人工复核/改判

### R5. 合同数据泄露

Mitigation：

- 下载鉴权
- 任务级访问控制
- 审计日志
- 文件路径不外露
- qmd index 按任务/项目隔离

### R6. Agent prompt injection

Mitigation：

- 合同文本只作为 evidence，不作为系统指令
- Agent 工具权限最小化
- qmd 只读
- 输出 schema 校验

## Implementation Hints

### Suggested Repo Structure

```text
backend/
  app/
    api/
    application/
    services/
      parsing/
      retrieval/
      agent/
      screening/
      streaming/
      storage/
    models/
    schemas/
frontend/
  src/
    pages/
    components/
    lib/
docs/
  prds/
docker-compose.yml
README.md
```

### Core Backend APIs

```text
POST   /api/screening-tasks
GET    /api/screening-tasks/{task_id}
GET    /api/screening-tasks/{task_id}/events
GET    /api/screening-tasks/{task_id}/results
GET    /api/screening-tasks/{task_id}/export
GET    /api/contracts/{contract_id}/download
POST   /api/screening-tasks/{task_id}/review
```

### Core Data Models

- `ScreeningTask`
- `ContractFile`
- `ParsedArtifact`
- `QmdIndexJob`
- `ScreeningPlan`
- `QmdCandidateSnippet`
- `ContractScreeningResult`
- `EvidenceRef`
- `ReviewDecision`
- `AuditEvent`

### Pipeline States

```text
created
uploaded
parsing
parsed
indexing
indexed
retrieving
classifying
completed
failed
cancelled
```

### First Milestone

Build a vertical slice:

1. Upload 3-5 PDF contracts
2. PaddleX parse to Markdown/JSON
3. qmd indexes Markdown
4. User enters one筛选条件
5. Agent calls qmd
6. Results grouped by contract file
7. Frontend streams events
8. Final output file names + download links

## Open Questions

1. qmd 调用方式最终选 CLI、HTTP MCP 还是 SDK？
2. qmd 是否能稳定返回 snippet、score、docid、文件路径？
3. 合同下载链接由本系统生成，还是对接现有文件系统？
4. PaddleX 是本地进程、远程服务，还是容器化 worker？
5. 第一版是否需要真实登录，还是先使用简单 token？
6. 是否需要接入既有合同库，还是 MVP 只支持上传批次？
7. 外部 LLM 是否允许接触合同文本，还是必须私有化模型？
8. DOCX 是否必须进入 MVP？
9. 是否需要中文金额、日期、主体的规则解析器？
10. 结果中是否展示 excluded，还是仅展示 included + uncertain？

## Sources & References

- PaddleOCR / PaddleX / PP-StructureV3 documentation: https://github.com/PaddlePaddle/PaddleOCR
- PP-StructureV3 docs: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html
- qmd GitHub README: https://github.com/tobi/qmd
- FastAPI UploadFile: https://fastapi.tiangolo.com/tutorial/request-files/
- FastAPI file responses: https://fastapi.tiangolo.com/advanced/custom-response/
- MDN Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- OWASP LLM risks: https://genai.owasp.org/llmrisk/
- CUAD benchmark: https://arxiv.org/abs/2103.06268
- Explainable legal document review: https://arxiv.org/abs/1904.01721

## Out-of-Scope Follow-Ups

- 组织级 RBAC
- 多租户合同库接入
- DOCX/Excel/邮件附件完整解析
- qmd 替换为自研检索服务
- 合同风险评分体系
- 自动生成法律意见
- 与 OA、ERP、印章系统、CLM 系统集成
- 批量长期监控合同风险
