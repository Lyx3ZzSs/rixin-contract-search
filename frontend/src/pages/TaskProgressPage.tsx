import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  exportTaskUrl,
  getConditionVerdicts,
  getEvidenceLedger,
  getQmdEvidenceContext,
  getQmdDownloadUrl,
  getQmdPreview,
  getQmdOpenLinkUrl,
  getTaskResults,
  getTaskSummary,
  reviewDocumentResult
} from '../lib/api';
import { apiErrorMessage, failureMessage } from '../lib/errorMessages';
import { getReviewerName, setReviewerName } from '../lib/reviewer';
import { subscribeTaskEvents } from '../lib/sse';
import { buildTaskActivity } from '../lib/taskActivity';
import type {
  ConditionVerdictItem,
  ConditionVerdictValue,
  DocumentResultItem,
  LedgerEvidenceItem,
  QmdDocumentPreview,
  QmdEvidenceContext,
  ResultDecision,
  ReviewStatus,
  StreamEvent,
  TaskResults,
  TaskSummary
} from '../lib/types';

const decisionLabels = {
  included: '入选',
  uncertain: '需确认',
  excluded: '不符合'
};

const decisionClasses = {
  included: 'full',
  uncertain: 'review',
  excluded: 'none'
};

type DecisionFilter = 'all' | ResultDecision;
type ReviewFilter = 'all' | ReviewStatus;

type PreviewTarget = {
  documentUri: string;
  conditionId: string | null;
  page: number | null;
};

export function TaskProgressPage() {
  const { taskId } = useParams();
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [results, setResults] = useState<TaskResults | null>(null);
  const [verdicts, setVerdicts] = useState<ConditionVerdictItem[]>([]);
  const [ledger, setLedger] = useState<LedgerEvidenceItem[]>([]);
  const [matrixWarning, setMatrixWarning] = useState<string | null>(null);
  const [ledgerWarning, setLedgerWarning] = useState<string | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null);
  const [previewMeta, setPreviewMeta] = useState<QmdDocumentPreview | null>(null);
  const [previewContext, setPreviewContext] = useState<QmdEvidenceContext | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [phase3Loading, setPhase3Loading] = useState(false);
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>('all');
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('all');
  const [keywordFilter, setKeywordFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const activeTaskId = taskId;
    let cancelled = false;
    setSummary(null);
    setResults(null);
    setVerdicts([]);
    setLedger([]);
    setMatrixWarning(null);
    setLedgerWarning(null);
    setEvents([]);
    setSelectedUri(null);
    setPreviewTarget(null);
    setPreviewMeta(null);
    setPreviewContext(null);
    setPreviewError(null);
    setPreviewLoading(false);
    setPhase3Loading(false);
    setDecisionFilter('all');
    setReviewFilter('all');
    setKeywordFilter('');
    setError(null);

    async function loadInitial() {
      try {
        const nextSummary = await getTaskSummary(activeTaskId);
        if (cancelled) return;
        setSummary(nextSummary);
        if (nextSummary.status === 'completed') await loadFinal(activeTaskId, () => cancelled);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载任务失败');
      }
    }

    void loadInitial();

    const unsubscribe = subscribeTaskEvents({
      taskId: activeTaskId,
      onEvent(event) {
        setEvents((current) => [...current, event]);
        if (typeof event.payload.progress_percent === 'number') {
          setSummary((current) => (current ? { ...current, progress_percent: event.payload.progress_percent as number } : current));
        }
      },
      onError(err) {
        setError(err.message);
      },
      onComplete() {
        void loadFinal(activeTaskId, () => cancelled);
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [taskId]);

  async function loadFinal(id: string, isCancelled: () => boolean) {
    setPhase3Loading(true);
    try {
      const [summaryResult, resultsResult, verdictResult, ledgerResult] = await Promise.allSettled([
        getTaskSummary(id),
        getTaskResults(id),
        getConditionVerdicts(id)
          .then((items) => ({ items: items.items, warning: null }))
          .catch((err) => ({ items: [] as ConditionVerdictItem[], warning: apiErrorMessage(err, '条件矩阵加载失败') })),
        getEvidenceLedger(id)
          .then((items) => ({ items: items.items, warning: null }))
          .catch((err) => ({ items: [] as LedgerEvidenceItem[], warning: apiErrorMessage(err, '证据账本加载失败') }))
      ]);
      if (isCancelled()) return;

      if (summaryResult.status === 'fulfilled') {
        setSummary(summaryResult.value);
      }
      if (resultsResult.status === 'fulfilled') {
        const nextResults = resultsResult.value;
        setResults(normalizeTaskResults(nextResults));
        const first = flattenResults(nextResults)[0];
        setSelectedUri((current) => current || first?.document_uri || null);
      }

      if (verdictResult.status === 'fulfilled') {
        setVerdicts(verdictResult.value.items);
        setMatrixWarning(verdictResult.value.warning);
      } else {
        setVerdicts([]);
        setMatrixWarning(apiErrorMessage(verdictResult.reason, '条件矩阵加载失败'));
      }

      if (ledgerResult.status === 'fulfilled') {
        setLedger(ledgerResult.value.items);
        setLedgerWarning(ledgerResult.value.warning);
      } else {
        setLedger([]);
        setLedgerWarning(apiErrorMessage(ledgerResult.reason, '证据账本加载失败'));
      }

      const coreFailure =
        summaryResult.status === 'rejected'
          ? summaryResult.reason
          : resultsResult.status === 'rejected'
            ? resultsResult.reason
            : null;
      if (coreFailure) {
        setError(apiErrorMessage(coreFailure, '加载任务结果失败'));
      } else {
        setError(null);
      }
    } finally {
      if (!isCancelled()) setPhase3Loading(false);
    }
  }

  function handleReviewed(result: DocumentResultItem) {
    const normalizedResult = normalizeDocumentResultItem(result);
    setResults((current) => (current ? updateResultInBuckets(current, normalizedResult) : current));
    setSelectedUri(normalizedResult.document_uri);
  }

  const visibleSummary = summary?.task_id === taskId ? summary : null;
  const visibleResults = results?.task_id === taskId ? results : null;
  const visibleEvents = useMemo(() => events.filter((event) => event.task_id === taskId), [events, taskId]);
  const activity = useMemo(() => buildTaskActivity(visibleSummary, visibleEvents), [visibleSummary, visibleEvents]);
  const documents = useMemo(() => (visibleResults ? flattenResults(visibleResults) : []), [visibleResults]);
  const filteredDocuments = useMemo(
    () => documents.filter((document) => matchesFilters(document, decisionFilter, reviewFilter, keywordFilter)),
    [documents, decisionFilter, keywordFilter, reviewFilter]
  );
  const selectedDocument = filteredDocuments.find((item) => item.document_uri === selectedUri) || null;
  const visibleLedger = useMemo(() => {
    if (!ledger.length) return [];
    if (!selectedDocument) return ledger;
    return ledger.filter((item) => resolveEvidenceDocumentUri(item, selectedDocument) === selectedDocument.document_uri);
  }, [ledger, selectedDocument]);
  const selectedDocumentUri = selectedDocument?.document_uri || null;
  const isCompleted = visibleSummary?.status === 'completed';
  const taskFailureMessage = error || (visibleSummary?.status === 'failed' ? failureMessage(visibleSummary.error_code, visibleSummary.error_message) : null);

  useEffect(() => {
    if (!selectedDocumentUri) {
      if (!previewTarget) {
        setPreviewTarget(null);
        setPreviewMeta(null);
        setPreviewContext(null);
        setPreviewError(null);
        setPreviewLoading(false);
      }
      return;
    }

    if (previewTarget?.documentUri === selectedDocumentUri) return;

    setPreviewTarget(null);
    setPreviewMeta(null);
    setPreviewContext(null);
    setPreviewError(null);
    setPreviewLoading(false);
  }, [previewTarget?.documentUri, selectedDocumentUri]);

  useEffect(() => {
    if (!taskId || !previewTarget) return;
    const currentTaskId = taskId;
    const target = previewTarget;
    if (!target.documentUri.trim()) {
      setPreviewError('原文预览需要有效的 document_uri 或 artifact_ref。');
      setPreviewMeta(null);
      setPreviewContext(null);
      return;
    }

    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);

    async function loadPreview() {
      const [metaResult, contextResult] = await Promise.allSettled([
        getQmdPreview(currentTaskId, target.documentUri),
        getQmdEvidenceContext(currentTaskId, {
          document_uri: target.documentUri,
          condition_id: target.conditionId || undefined,
          page: target.page
        })
      ]);

      if (cancelled) return;

      if (metaResult.status === 'fulfilled') {
        setPreviewMeta(metaResult.value);
      } else {
        setPreviewMeta(null);
        setPreviewError(apiErrorMessage(metaResult.reason, '原文预览加载失败'));
      }

      if (contextResult.status === 'fulfilled') {
        setPreviewContext(contextResult.value);
      } else {
        setPreviewContext(null);
        setPreviewError((current) => current || apiErrorMessage(contextResult.reason, '原文上下文加载失败'));
      }

      setPreviewLoading(false);
    }

    void loadPreview();

    return () => {
      cancelled = true;
    };
  }, [previewTarget, taskId]);

  if (!taskId) {
    return <div className="agent-shell">缺少任务 ID</div>;
  }

  return (
    <main className="agent-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TASK {taskId}</p>
          <h1>{visibleSummary?.title || '合同筛选任务'}</h1>
          <p className="topbar-subtitle">{visibleSummary?.raw_query || '正在加载任务信息'}</p>
        </div>
        <div className="topbar-actions">
          <Link className="ghost-button" to="/tasks">
            任务历史
          </Link>
          {isCompleted ? (
            <div className="export-actions" aria-label="导出任务结果">
              <a className="mini-button" href={exportTaskUrl(taskId, 'csv')}>
                导出 CSV
              </a>
              <a className="mini-button" href={exportTaskUrl(taskId, 'xlsx')}>
                导出 XLSX
              </a>
              <a className="mini-button" href={exportTaskUrl(taskId, 'json')}>
                导出 JSON
              </a>
            </div>
          ) : null}
          <Link className="ghost-button" to="/">
            新建筛选
          </Link>
        </div>
      </header>

      <section className="agent-status-strip" aria-label="Agent 状态">
        {activity.stages.map((step, index) => (
          <div className={`agent-status-step ${step.state}`} key={step.key}>
            <span>{index + 1}</span>
            <strong>{step.label}</strong>
          </div>
        ))}
      </section>

      <section className="workspace" aria-label="合同文件筛选工作区">
        <aside className="panel-left">
          <section className="side-card">
            <div className="card-heading">
              <h2>任务进度</h2>
              <p>{visibleSummary?.current_stage || 'loading'}</p>
            </div>
            <div className="progress-meter" data-testid="event-progress">
              <span style={{ width: `${visibleSummary?.progress_percent ?? 0}%` }} />
            </div>
            <strong>{visibleSummary?.progress_percent ?? 0}%</strong>
            {taskFailureMessage ? <p className="error-text">{taskFailureMessage}</p> : null}
          </section>

          <section className="side-card">
            <div className="card-heading">
              <h2>实时活动</h2>
            </div>
            <div className="event-list">
              {activity.items.length ? activity.items.map((item) => <span key={item.id}>{item.text}</span>) : <span>等待后端事件...</span>}
            </div>
          </section>
        </aside>

        <section className="panel-center">
          <ResultSummary summary={visibleSummary} results={visibleResults} />
          <ConditionMatrixPanel
            documents={filteredDocuments}
            selectedDocumentUri={selectedDocumentUri}
            verdicts={verdicts}
            warning={matrixWarning}
            onSelectDocument={(documentUri) => {
              setSelectedUri(documentUri);
            }}
            onPick={(target) => {
              setSelectedUri(target.documentUri);
              setPreviewTarget(target);
            }}
          />
          <EvidenceLedgerPanel
            document={selectedDocument}
            items={visibleLedger}
            loading={phase3Loading}
            warning={ledgerWarning}
            onPick={(target) => {
              setSelectedUri(target.documentUri);
              setPreviewTarget(target);
            }}
          />
          <QmdContextPanel
            document={selectedDocument}
            loading={previewLoading}
            preview={previewMeta}
            context={previewContext}
            error={previewError}
            previewTarget={previewTarget}
            onPreview={(target) => {
              setSelectedUri(target.documentUri);
              setPreviewTarget(target);
            }}
            taskId={taskId}
          />
          <section className="results-card">
            <div className="section-title-row">
              <h2>文件结果</h2>
              <span>
                {filteredDocuments.length} / {documents.length} 个文档
              </span>
            </div>
            <div className="result-filters" aria-label="结果筛选">
              <label>
                <span>Agent 判断</span>
                <select value={decisionFilter} onChange={(event) => setDecisionFilter(event.target.value as DecisionFilter)}>
                  <option value="all">全部</option>
                  <option value="included">入选</option>
                  <option value="uncertain">需确认</option>
                  <option value="excluded">不符合</option>
                </select>
              </label>
              <label>
                <span>复核状态</span>
                <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as ReviewFilter)}>
                  <option value="all">全部</option>
                  <option value="unreviewed">未复核</option>
                  <option value="reviewed">已复核</option>
                </select>
              </label>
              <label>
                <span>关键词</span>
                <input value={keywordFilter} onChange={(event) => setKeywordFilter(event.target.value)} placeholder="标题、路径、依据" />
              </label>
            </div>
            <div className="result-list">
              {filteredDocuments.length === 0 ? (
                <div className="empty-state">
                  <strong>{documents.length ? '没有符合筛选条件的文档' : visibleSummary?.status === 'completed' ? '未找到符合条件的合同文件' : 'Agent 正在检索合同库'}</strong>
                  <span>{documents.length ? '调整判断、复核状态或关键词后再查看。' : '完成后会在这里显示真实后端结果。'}</span>
                </div>
              ) : (
                filteredDocuments.map((document) => (
                  <DocumentCard
                    document={document}
                    key={document.document_uri}
                    selected={document.document_uri === selectedDocument?.document_uri}
                    onSelect={() => setSelectedUri(document.document_uri)}
                  />
                ))
              )}
            </div>
          </section>
        </section>

        <aside className="panel-right">
          <EvidencePanel document={selectedDocument} taskId={taskId} onReviewed={handleReviewed} />
        </aside>
      </section>
    </main>
  );
}

function ResultSummary({ summary, results }: { summary: TaskSummary | null; results: TaskResults | null }) {
  const counts = summary?.counts || { documents: 0, included: 0, uncertain: 0, excluded: 0 };
  return (
    <section className="summary-card">
      <div>
        <p className="eyebrow">RESULTS</p>
        <h2>{summary?.status === 'completed' ? `找到 ${counts.documents} 个合同文件` : 'Agent 正在处理任务'}</h2>
        <p>{results ? '结果来自后端任务 API，不再使用前端 mock 数据。' : '正在监听后端 SSE 事件并等待任务完成。'}</p>
      </div>
      <div className="summary-stats">
        <span>
          <strong>{counts.included}</strong>入选
        </span>
        <span>
          <strong>{counts.uncertain}</strong>需确认
        </span>
        <span>
          <strong>{counts.excluded}</strong>不符合
        </span>
      </div>
    </section>
  );
}

function DocumentCard({ document, selected, onSelect }: { document: DocumentResultItem; selected: boolean; onSelect: () => void }) {
  const title = document.document_title || document.document_path;
  return (
    <article
      className={`contract-card ${selected ? 'is-selected' : ''}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect();
        }
      }}
      role="button"
      tabIndex={0}
    >
      <div className="contract-card-top">
        <div className="file-title-block">
          <span className="contract-id">{document.collection}</span>
          <h3>{title}</h3>
          <p>
            {document.collection} · {document.document_path}
          </p>
        </div>
        <div className="score-block">
          <span className={`match-pill ${decisionClasses[document.decision]}`}>{decisionLabels[document.decision]}</span>
          <strong>{Math.round(document.confidence * 100)}%</strong>
        </div>
      </div>
      <div className="condition-columns">
        <section>
          <h4>命中条件</h4>
          <ul>{document.matched_conditions.length ? document.matched_conditions.map((item) => <li key={item}>{item}</li>) : <li className="muted">无</li>}</ul>
        </section>
        <section>
          <h4>缺失条件</h4>
          <ul>{document.missing_conditions.length ? document.missing_conditions.map((item) => <li key={item}>{item}</li>) : <li className="muted">无</li>}</ul>
        </section>
      </div>
      <div className="card-actions">
        <span className="mini-button readonly">
          {decisionLabels[document.decision]} · {document.reason}
        </span>
        <span className={`review-chip ${document.review_status === 'reviewed' ? 'reviewed' : ''}`}>
          {document.review_status === 'reviewed' ? `已复核${document.reviewer_name ? ` · ${document.reviewer_name}` : ''}` : '未复核'}
        </span>
      </div>
    </article>
  );
}

function ConditionMatrixPanel({
  documents,
  selectedDocumentUri,
  verdicts,
  warning,
  onSelectDocument,
  onPick
}: {
  documents: DocumentResultItem[];
  selectedDocumentUri: string | null;
  verdicts: ConditionVerdictItem[];
  warning: string | null;
  onSelectDocument: (documentUri: string) => void;
  onPick: (target: PreviewTarget) => void;
}) {
  const matrix = buildVerdictMatrix(documents, verdicts);
  const columns = matrix.columns;
  const gridTemplateColumns = [`minmax(220px, 1.2fr)`, ...columns.map(() => 'minmax(96px, 1fr)')].join(' ');
  const matrixStyle = { ['--matrix-columns' as const]: gridTemplateColumns } as CSSProperties;

  return (
    <section className="phase3-panel">
      <div className="section-title-row">
        <div>
          <h2>条件矩阵</h2>
          <span>{documents.length ? `当前筛选 ${documents.length} 份文档的条件判定` : '按任务汇总所有文档的条件判定'}</span>
        </div>
        <span>{matrix.rows.length} 行</span>
      </div>
      {warning ? (
        <div className="phase3-warning" role="status">
          <strong>条件矩阵数据加载失败</strong>
          <span>{warning}</span>
        </div>
      ) : null}
      {columns.length === 0 || matrix.rows.length === 0 ? (
        <div className="empty-state compact">
          <strong>暂无条件矩阵</strong>
          <span>任务完成后会显示文档与条件的逐项判定。</span>
        </div>
      ) : (
        <div className="matrix-table-scroll">
          <div className="matrix-table" role="table" aria-label="条件矩阵" style={matrixStyle}>
            <div className="matrix-row matrix-head" role="row">
              <span role="columnheader">文档</span>
              {columns.map((conditionId) => (
                <span role="columnheader" key={conditionId}>
                  {conditionId}
                </span>
              ))}
            </div>
            {matrix.rows.map((row) => (
              <div className={`matrix-row ${row.documentUri === selectedDocumentUri ? 'is-selected' : ''}`} key={row.documentUri} role="row">
                <button
                  aria-current={row.documentUri === selectedDocumentUri ? 'true' : undefined}
                  className="matrix-document-button"
                  type="button"
                  onClick={() => onSelectDocument(row.documentUri)}
                >
                  {row.documentTitle || row.documentPath}
                </button>
                {columns.map((conditionId) => {
                  const item = row.items.get(conditionId);
                  return (
                    <button
                      className={`verdict-pill verdict-${item?.verdict || 'missing'}`}
                      key={`${row.documentUri}-${conditionId}`}
                      type="button"
                      onClick={() => {
                        if (!item) return;
                        const supportingPage = item.supporting_evidence.find((evidence) => evidence.page != null)?.page ?? null;
                        onPick({
                          documentUri: row.documentUri,
                          conditionId,
                          page: supportingPage
                        });
                      }}
                      disabled={!item}
                    >
                      {item ? verdictLabel(item.verdict) : '—'}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function EvidenceLedgerPanel({
  document,
  items,
  loading,
  warning,
  onPick
}: {
  document: DocumentResultItem | null;
  items: LedgerEvidenceItem[];
  loading: boolean;
  warning: string | null;
  onPick: (target: PreviewTarget) => void;
}) {
  return (
    <section className="phase3-panel">
      <div className="section-title-row">
        <div>
          <h2>证据账本</h2>
          <span>{document ? `已过滤到：${document.document_title || document.document_path}` : '显示任务下全部证据记录'}</span>
        </div>
        <span>{items.length} 条</span>
      </div>
      {warning ? (
        <div className="phase3-warning" role="status">
          <strong>证据账本数据加载失败</strong>
          <span>{warning}</span>
        </div>
      ) : null}
      {loading ? (
        <div className="empty-state compact">
          <strong>正在加载证据账本</strong>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">
          <strong>暂无证据账本</strong>
          <span>后端返回的证据条目会按文档和条件聚合在这里。</span>
        </div>
      ) : (
        <div className="ledger-list">
          {items.map((item, index) => (
            <button
              className="ledger-row"
              key={`${item.condition_id}-${item.page ?? 'na'}-${index}`}
              type="button"
              onClick={() => {
                const resolvedUri = resolveEvidenceDocumentUri(item, document);
                if (!resolvedUri) return;
                onPick({
                  documentUri: resolvedUri,
                  conditionId: item.condition_id,
                  page: item.page
                });
              }}
            >
              <div>
                <strong>{item.condition_id}</strong>
                <span>{item.document_path || item.document_uri || '未命中文档'}</span>
              </div>
              <div>
                <strong>{ledgerRoleLabel(item.role)}</strong>
                <span>{ledgerToolLabel(item.source_tool)}</span>
              </div>
              <div>
                <strong>{item.page != null ? `第 ${item.page} 页` : '页码未知'}</strong>
                <span>{item.used_for_decision ? '参与判定' : '仅检索'}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function QmdContextPanel({
  document,
  loading,
  preview,
  context,
  error,
  previewTarget,
  onPreview,
  taskId
}: {
  document: DocumentResultItem | null;
  loading: boolean;
  preview: QmdDocumentPreview | null;
  context: QmdEvidenceContext | null;
  error: string | null;
  previewTarget: PreviewTarget | null;
  onPreview: (target: PreviewTarget) => void;
  taskId: string;
}) {
  const documentUri = document?.document_uri || previewTarget?.documentUri || preview?.document_uri || context?.document_uri || null;
  const canOpen = Boolean(preview?.can_open && documentUri);
  const canDownload = Boolean(preview?.can_download && documentUri);
  const conditionLabel = context?.condition_id ? `条件：${context.condition_id}` : '条件：-';
  const pageLabel = context && context.page != null ? `页码：${context.page}` : '页码：-';
  const anchorLabel = context?.anchor || '锚点：-';
  const reloadTarget = previewTarget || { documentUri: documentUri || '', conditionId: null, page: null };
  const hasContext = Boolean(document || previewTarget || preview || context);
  const displayTitle = preview?.document_title || document?.document_title || document?.document_path || documentUri || '原文上下文';
  const displaySummary = preview?.summary || document?.collection || documentUri || '点击条件矩阵或证据账本查看原文上下文';

  return (
    <section className="phase3-panel">
      <div className="section-title-row">
        <div>
          <h2>原文上下文</h2>
          <span>{document ? document.document_title || document.document_path : documentUri || '点击条件矩阵或证据账本查看原文上下文'}</span>
        </div>
        <span>{loading ? '加载中' : context?.source_tool || '待选中'}</span>
      </div>
      {!hasContext ? (
        <div className="empty-state compact">
          <strong>请选择一份合同</strong>
          <span>点击条件矩阵或证据账本查看原文上下文。</span>
        </div>
      ) : (
        <div className="context-box">
          {error ? (
            <div className="context-error">
              <strong>{error}</strong>
              <span>确认该文档与任务关联后重试。</span>
            </div>
          ) : null}
          <div className="context-toolbar">
            <div>
              <strong>{displayTitle}</strong>
              <span>{displaySummary}</span>
            </div>
            <div className="context-actions">
              <button
                className="ghost-button"
                type="button"
                onClick={() => onPreview(previewTarget ? { ...previewTarget } : reloadTarget)}
                disabled={!documentUri}
              >
                {preview || context ? '重新加载' : '加载上下文'}
              </button>
              {canOpen ? (
                <a className="mini-button" href={getQmdOpenLinkUrl(taskId, documentUri || '')}>
                  打开原文
                </a>
              ) : null}
              {canDownload ? (
                <a className="mini-button" href={getQmdDownloadUrl(taskId, documentUri || '')}>
                  下载原文
                </a>
              ) : null}
            </div>
          </div>
          {!preview && !context && !loading && !error ? (
            <div className="empty-state compact context-idle">
              <strong>点击条件矩阵或证据账本查看原文上下文</strong>
              <span>选择一个条件后，这里会加载对应的原文预览与上下文。</span>
            </div>
          ) : (
            <div className="context-body">
              <div className="context-text">{context?.text || '正在等待上下文内容'}</div>
              <div className="context-meta">
                <span>{conditionLabel}</span>
                <span>{pageLabel}</span>
                <span>{anchorLabel}</span>
                <span>{preview?.collection || document?.collection || 'collection：-'}</span>
              </div>
            </div>
          )}
          {preview?.toc?.length ? (
            <div className="context-toc">
              <strong>目录</strong>
              <ul>
                {preview.toc.slice(0, 5).map((item, index) => (
                  <li key={index}>{tocEntryLabel(item)}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function EvidencePanel({ document, taskId, onReviewed }: { document: DocumentResultItem | null; taskId: string; onReviewed: (result: DocumentResultItem) => void }) {
  const [reviewerName, setReviewerNameState] = useState(() => getReviewerName());
  const [reviewDecision, setReviewDecision] = useState<ResultDecision>('included');
  const [reviewNote, setReviewNote] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const normalizedDocument = useMemo(() => (document ? normalizeDocumentResultItem(document) : null), [document]);

  useEffect(() => {
    if (!normalizedDocument) return;
    setReviewDecision(normalizedDocument.review_decision || normalizedDocument.decision);
    setReviewNote(normalizedDocument.review_note || '');
    setSaveError(null);
  }, [normalizedDocument?.result_id]);

  async function handleSaveReview() {
    if (!normalizedDocument) return;
    const trimmedReviewer = reviewerName.trim();
    if (!trimmedReviewer) {
      setSaveError('请输入复核人');
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      setReviewerName(trimmedReviewer);
      setReviewerNameState(trimmedReviewer);
      const response = await reviewDocumentResult(taskId, normalizedDocument.result_id, {
        review_status: 'reviewed',
        review_decision: reviewDecision,
        review_note: reviewNote.trim() || undefined,
        reviewer_name: trimmedReviewer
      });
      const normalizedResult = normalizeDocumentResultItem(response.result);
      onReviewed(normalizedResult);
      setReviewDecision(normalizedResult.review_decision || normalizedResult.decision);
      setReviewNote(normalizedResult.review_note || '');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存复核失败');
    } finally {
      setSaving(false);
    }
  }

  if (!normalizedDocument) {
    return (
      <div className="evidence-panel empty">
        <div className="empty-state">
          <strong>请选择一份合同，查看 Agent 的判断依据。</strong>
          <span>命中条件、依据页码和关键原文会展示在这里。</span>
        </div>
      </div>
    );
  }
  return (
    <div className="evidence-panel">
      <div className="evidence-scroll">
        <div className="panel-heading">
          <div>
            <h2>命中依据</h2>
            <p>当前文档：{normalizedDocument.document_title || normalizedDocument.document_path}</p>
          </div>
        </div>
        <section className="detail-block">
          <h3>判断结果</h3>
          <p>
            判断：{decisionLabels[normalizedDocument.decision]} · {normalizedDocument.reason}
          </p>
          <div className="summary-grid phase3-summary-grid">
            <span>
              <strong>核验状态</strong>
              {normalizedDocument.verification_status}
            </span>
            <span>
              <strong>证据支持率</strong>
              {Math.round(normalizedDocument.evidence_support_rate * 100)}%
            </span>
            <span>
              <strong>不确定原因</strong>
              {normalizedDocument.uncertain_reasons.length ? normalizedDocument.uncertain_reasons.join('、') : '无'}
            </span>
            <span>
              <strong>判定摘要</strong>
              {Object.keys(normalizedDocument.decision_basis).length ? Object.keys(normalizedDocument.decision_basis).join('、') : '无'}
            </span>
          </div>
          {normalizedDocument.review_status === 'reviewed' ? (
            <div className="review-status-box">
              <strong>已复核：{normalizedDocument.reviewer_name || '未记录复核人'}</strong>
              <span>人工结论：{normalizedDocument.review_decision ? decisionLabels[normalizedDocument.review_decision] : '未记录'}</span>
              {normalizedDocument.reviewed_at ? <span>复核时间：{formatDateTime(normalizedDocument.reviewed_at)}</span> : null}
              {normalizedDocument.review_note ? <p>{normalizedDocument.review_note}</p> : null}
            </div>
          ) : null}
        </section>
        <section className="detail-block review-form">
          <h3>人工复核</h3>
          <label>
            <span>复核人</span>
            <input value={reviewerName} onChange={(event) => setReviewerNameState(event.target.value)} placeholder="输入姓名" />
          </label>
          <label>
            <span>人工结论</span>
            <select value={reviewDecision} onChange={(event) => setReviewDecision(event.target.value as ResultDecision)}>
              <option value="included">入选</option>
              <option value="uncertain">需确认</option>
              <option value="excluded">不符合</option>
            </select>
          </label>
          <label>
            <span>复核备注</span>
            <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="记录人工判断依据" />
          </label>
          {saveError ? <p className="error-text compact">{saveError}</p> : null}
          <button className="primary-button full-width" type="button" disabled={saving} onClick={handleSaveReview}>
            保存复核
          </button>
        </section>
        <section className="detail-block snippets-block">
          <h3>关键原文摘录</h3>
          {normalizedDocument.evidence.length ? (
            normalizedDocument.evidence.map((item, index) => (
              <article className="snippet-item" key={`${item.condition_id}-${index}`}>
                <div className="snippet-head">
                  <strong>{item.condition_id}</strong>
                  <span>{item.page != null ? `第 ${item.page} 页` : '页码未知'}</span>
                </div>
                <p>{item.text}</p>
                {item.artifact_ref ? <small>{item.artifact_ref}</small> : null}
              </article>
            ))
          ) : (
            <div className="empty-state">
              <strong>暂无可展示证据</strong>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function buildVerdictMatrix(
  documents: DocumentResultItem[] = [],
  verdicts: ConditionVerdictItem[] = []
): {
  columns: string[];
  rows: Array<{
    documentUri: string;
    documentTitle: string | null;
    documentPath: string;
    items: Map<string, ConditionVerdictItem>;
  }>;
} {
  const allowedDocuments = new Map(documents.map((document) => [document.document_uri, document] as const));
  const columns = Array.from(new Set(verdicts.filter((item) => allowedDocuments.has(item.document_uri)).map((item) => item.condition_id))).sort((a, b) => a.localeCompare(b));
  const grouped = new Map<
    string,
    {
      documentUri: string;
      documentTitle: string | null;
      documentPath: string;
      items: Map<string, ConditionVerdictItem>;
    }
  >();

  for (const document of documents) {
    grouped.set(document.document_uri, {
      documentUri: document.document_uri,
      documentTitle: document.document_title,
      documentPath: document.document_path,
      items: new Map()
    });
  }

  for (const item of verdicts) {
    if (!allowedDocuments.has(item.document_uri)) continue;
    if (!grouped.has(item.document_uri)) continue;
    const row = grouped.get(item.document_uri)!;
    row.items.set(item.condition_id, item);
  }

  return {
    columns,
    rows: Array.from(grouped.values()).sort((left, right) => left.documentPath.localeCompare(right.documentPath))
  };
}

function verdictLabel(value: ConditionVerdictValue): string {
  switch (value) {
    case 'satisfied':
      return '满足';
    case 'not_satisfied':
      return '不满足';
    case 'conflicting':
      return '冲突';
    default:
      return '未知';
  }
}

function ledgerRoleLabel(role: LedgerEvidenceItem['role']): string {
  switch (role) {
    case 'supporting':
      return '支持';
    case 'contradicting':
      return '反驳';
    case 'missing_context':
      return '缺失上下文';
    default:
      return '候选';
  }
}

function ledgerToolLabel(tool: LedgerEvidenceItem['source_tool']): string {
  switch (tool) {
    case 'doc_grep':
      return 'doc_grep';
    case 'doc_read':
      return 'doc_read';
    case 'doc_query':
      return 'doc_query';
    case 'doc_elements':
      return 'doc_elements';
    default:
      return 'query';
  }
}

function resolveEvidenceDocumentUri(item: LedgerEvidenceItem, selectedDocument: DocumentResultItem | null): string | null {
  return item.document_uri || item.artifact_ref || selectedDocument?.document_uri || null;
}

function tocEntryLabel(entry: Record<string, unknown>): string {
  const label = entry.title || entry.name || entry.label || entry.text;
  return typeof label === 'string' && label.trim() ? label : JSON.stringify(entry);
}

function normalizeTaskResults(results: TaskResults): TaskResults {
  return {
    ...results,
    buckets: {
      included: results.buckets.included.map(normalizeDocumentResultItem),
      uncertain: results.buckets.uncertain.map(normalizeDocumentResultItem),
      excluded: results.buckets.excluded.map(normalizeDocumentResultItem)
    }
  };
}

function normalizeDocumentResultItem(document: DocumentResultItem): DocumentResultItem {
  return {
    ...document,
    matched_conditions: Array.isArray(document.matched_conditions)
      ? document.matched_conditions.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      : [],
    missing_conditions: Array.isArray(document.missing_conditions)
      ? document.missing_conditions.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      : [],
    evidence: Array.isArray(document.evidence) ? document.evidence : [],
    confidence: typeof document.confidence === 'number' && Number.isFinite(document.confidence) ? document.confidence : 0,
    review_status: document.review_status === 'reviewed' ? 'reviewed' : 'unreviewed',
    review_decision: document.review_decision ?? null,
    review_note: document.review_note ?? null,
    reviewer_name: document.reviewer_name ?? null,
    reviewed_at: document.reviewed_at ?? null,
    decision_basis: isPlainObject(document.decision_basis) ? document.decision_basis : {},
    uncertain_reasons: Array.isArray(document.uncertain_reasons)
      ? document.uncertain_reasons.filter((reason): reason is string => typeof reason === 'string' && reason.trim().length > 0)
      : [],
    evidence_support_rate: typeof document.evidence_support_rate === 'number' && Number.isFinite(document.evidence_support_rate) ? document.evidence_support_rate : 0,
    verification_status: document.verification_status || 'query_only'
  };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function flattenResults(results: TaskResults): DocumentResultItem[] {
  return [...results.buckets.included, ...results.buckets.uncertain, ...results.buckets.excluded];
}

function updateResultInBuckets(results: TaskResults, result: DocumentResultItem): TaskResults {
  return {
    ...results,
    buckets: {
      included: results.buckets.included.map((item) => (item.result_id === result.result_id ? result : item)),
      uncertain: results.buckets.uncertain.map((item) => (item.result_id === result.result_id ? result : item)),
      excluded: results.buckets.excluded.map((item) => (item.result_id === result.result_id ? result : item))
    }
  };
}

function matchesFilters(document: DocumentResultItem, decisionFilter: DecisionFilter, reviewFilter: ReviewFilter, keywordFilter: string): boolean {
  if (decisionFilter !== 'all' && document.decision !== decisionFilter) return false;
  if (reviewFilter !== 'all' && document.review_status !== reviewFilter) return false;

  const keyword = keywordFilter.trim().toLowerCase();
  if (!keyword) return true;

  return searchableText(document).includes(keyword);
}

function searchableText(document: DocumentResultItem): string {
  return [
    document.document_title,
    document.document_path,
    document.collection,
    document.reason,
    ...document.matched_conditions,
    ...document.missing_conditions,
    ...document.evidence.map((item) => item.text)
  ]
    .filter((value): value is string => Boolean(value))
    .join(' ')
    .toLowerCase();
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}
