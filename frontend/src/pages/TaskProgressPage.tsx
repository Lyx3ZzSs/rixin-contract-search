import { useEffect, useMemo, useState } from 'react';
import type { MouseEvent } from 'react';
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
type InsightTab = 'conditions' | 'evidence' | 'source';

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
  const [insightDocumentUri, setInsightDocumentUri] = useState<string | null>(null);
  const [insightTab, setInsightTab] = useState<InsightTab>('conditions');
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
    setInsightDocumentUri(null);
    setInsightTab('conditions');
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
          .catch((err) => ({ items: [] as ConditionVerdictItem[], warning: apiErrorMessage(err, '条件核验加载失败') })),
        getEvidenceLedger(id)
          .then((items) => ({ items: items.items, warning: null }))
          .catch((err) => ({ items: [] as LedgerEvidenceItem[], warning: apiErrorMessage(err, '证据明细加载失败') }))
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
        setMatrixWarning(apiErrorMessage(verdictResult.reason, '条件核验加载失败'));
      }

      if (ledgerResult.status === 'fulfilled') {
        setLedger(ledgerResult.value.items);
        setLedgerWarning(ledgerResult.value.warning);
      } else {
        setLedger([]);
        setLedgerWarning(apiErrorMessage(ledgerResult.reason, '证据明细加载失败'));
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
  const insightDocument = useMemo(() => documents.find((item) => item.document_uri === insightDocumentUri) || null, [documents, insightDocumentUri]);
  const insightVerdicts = useMemo(
    () => (insightDocument ? verdicts.filter((item) => item.document_uri === insightDocument.document_uri) : []),
    [insightDocument, verdicts]
  );
  const insightLedger = useMemo(
    () => (insightDocument ? ledger.filter((item) => resolveEvidenceDocumentUri(item, insightDocument) === insightDocument.document_uri) : []),
    [insightDocument, ledger]
  );
  const isCompleted = visibleSummary?.status === 'completed';
  const taskFailureMessage = error || (visibleSummary?.status === 'failed' ? failureMessage(visibleSummary.error_code, visibleSummary.error_message) : null);

  useEffect(() => {
    if (!insightDocumentUri) return;
    if (documents.some((item) => item.document_uri === insightDocumentUri)) return;
    setInsightDocumentUri(null);
  }, [documents, insightDocumentUri]);

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
        setPreviewError((current) => current || apiErrorMessage(contextResult.reason, '原文依据加载失败'));
      }

      setPreviewLoading(false);
    }

    void loadPreview();

    return () => {
      cancelled = true;
    };
  }, [previewTarget, taskId]);

  function openInsight(document: DocumentResultItem, tab: InsightTab, target?: PreviewTarget) {
    setSelectedUri(document.document_uri);
    setInsightDocumentUri(document.document_uri);
    setInsightTab(tab);

    if (tab === 'source') {
      setPreviewTarget(target || { documentUri: document.document_uri, conditionId: null, page: null });
      return;
    }

    setPreviewTarget(null);
    setPreviewMeta(null);
    setPreviewContext(null);
    setPreviewError(null);
    setPreviewLoading(false);
  }

  function handleInsightTabChange(tab: InsightTab) {
    setInsightTab(tab);
    if (tab === 'source' && insightDocument) {
      if (previewTarget?.documentUri !== insightDocument.document_uri) {
        setPreviewTarget({ documentUri: insightDocument.document_uri, conditionId: null, page: null });
      }
    }
  }

  function handleInsightPick(target: PreviewTarget) {
    setSelectedUri(target.documentUri);
    setInsightDocumentUri(target.documentUri);
    setInsightTab('source');
    setPreviewTarget(target);
  }

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
                    onOpenInsight={(tab) => openInsight(document, tab)}
                    taskId={taskId}
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
      <DocumentInsightDrawer
        document={insightDocument}
        activeTab={insightTab}
        verdicts={insightVerdicts}
        ledgerItems={insightLedger}
        conditionWarning={matrixWarning}
        ledgerWarning={ledgerWarning}
        loading={phase3Loading}
        preview={previewMeta}
        context={previewContext}
        contextError={previewError}
        contextLoading={previewLoading}
        previewTarget={previewTarget}
        taskId={taskId}
        onClose={() => setInsightDocumentUri(null)}
        onPick={handleInsightPick}
        onPreview={(target) => {
          setSelectedUri(target.documentUri);
          setPreviewTarget(target);
        }}
        onTabChange={handleInsightTabChange}
      />
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

function DocumentCard({
  document,
  selected,
  onSelect,
  onOpenInsight,
  taskId
}: {
  document: DocumentResultItem;
  selected: boolean;
  onSelect: () => void;
  onOpenInsight: (tab: InsightTab) => void;
  taskId: string;
}) {
  const title = document.document_title || document.document_path;
  const matchedCount = document.matched_conditions.length;
  const missingCount = document.missing_conditions.length;
  const uncertainCount = document.uncertain_reasons.length;
  const supportPercent = Math.round(document.evidence_support_rate * 100);
  const stopAction = (event: MouseEvent<HTMLElement>) => {
    event.stopPropagation();
  };

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
        <div className="score-block" aria-label={`${title}匹配率`}>
          <span className={`match-pill ${decisionClasses[document.decision]}`}>{decisionLabels[document.decision]}</span>
          <strong>{supportPercent}%</strong>
          <small>匹配率</small>
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
      <div className="card-insight-summary" aria-label={`${title}核验摘要`}>
        <span>命中 {matchedCount} 个条件</span>
        <span>缺失 {missingCount} 个条件</span>
        <span>{uncertainCount ? `${uncertainCount} 条需确认` : '暂无不确定项'}</span>
      </div>
      <div className="card-insight-actions" aria-label={`${title}操作`}>
        <button
          className="mini-button"
          type="button"
          aria-label={`查看${title}条件核验`}
          onClick={(event) => {
            stopAction(event);
            onOpenInsight('conditions');
          }}
        >
          条件核验
        </button>
        <button
          className="mini-button"
          type="button"
          aria-label={`查看${title}证据明细`}
          onClick={(event) => {
            stopAction(event);
            onOpenInsight('evidence');
          }}
        >
          证据明细
        </button>
        <button
          className="mini-button"
          type="button"
          aria-label={`查看${title}原文依据`}
          onClick={(event) => {
            stopAction(event);
            onOpenInsight('source');
          }}
        >
          原文依据
        </button>
        <a className="mini-button" href={getQmdOpenLinkUrl(taskId, document.document_uri)} aria-label={`预览${title}`} onClick={stopAction}>
          预览
        </a>
        <a className="mini-button" href={getQmdDownloadUrl(taskId, document.document_uri)} aria-label={`下载${title}`} onClick={stopAction}>
          下载
        </a>
      </div>
    </article>
  );
}

function DocumentInsightDrawer({
  document,
  activeTab,
  verdicts,
  ledgerItems,
  conditionWarning,
  ledgerWarning,
  loading,
  preview,
  context,
  contextError,
  contextLoading,
  previewTarget,
  taskId,
  onClose,
  onPick,
  onPreview,
  onTabChange
}: {
  document: DocumentResultItem | null;
  activeTab: InsightTab;
  verdicts: ConditionVerdictItem[];
  ledgerItems: LedgerEvidenceItem[];
  conditionWarning: string | null;
  ledgerWarning: string | null;
  loading: boolean;
  preview: QmdDocumentPreview | null;
  context: QmdEvidenceContext | null;
  contextError: string | null;
  contextLoading: boolean;
  previewTarget: PreviewTarget | null;
  taskId: string;
  onClose: () => void;
  onPick: (target: PreviewTarget) => void;
  onPreview: (target: PreviewTarget) => void;
  onTabChange: (tab: InsightTab) => void;
}) {
  if (!document) return null;

  const title = document.document_title || document.document_path;

  return (
    <div className="insight-drawer-backdrop" role="presentation">
      <section className="insight-drawer" role="dialog" aria-modal="true" aria-label={`${title}详情`}>
        <div className="insight-drawer-head">
          <div>
            <span className="contract-id">{document.collection}</span>
            <h2>{title}详情</h2>
            <p>{document.document_path}</p>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="insight-tabs" role="tablist" aria-label="文件详情">
          <InsightTabButton active={activeTab === 'conditions'} label="条件核验" onClick={() => onTabChange('conditions')} />
          <InsightTabButton active={activeTab === 'evidence'} label="证据明细" onClick={() => onTabChange('evidence')} />
          <InsightTabButton active={activeTab === 'source'} label="原文依据" onClick={() => onTabChange('source')} />
        </div>
        <div className="insight-drawer-body">
          {activeTab === 'conditions' ? (
            <ConditionVerificationDetails document={document} verdicts={verdicts} warning={conditionWarning} onPick={onPick} />
          ) : null}
          {activeTab === 'evidence' ? (
            <EvidenceLedgerDetails document={document} items={ledgerItems} loading={loading} warning={ledgerWarning} onPick={onPick} />
          ) : null}
          {activeTab === 'source' ? (
            <QmdContextPanel
              document={document}
              loading={contextLoading}
              preview={preview}
              context={context}
              error={contextError}
              previewTarget={previewTarget}
              onPreview={onPreview}
              taskId={taskId}
            />
          ) : null}
        </div>
      </section>
    </div>
  );
}

function InsightTabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={`insight-tab ${active ? 'active' : ''}`} type="button" role="tab" aria-selected={active} onClick={onClick}>
      {label}
    </button>
  );
}

function ConditionVerificationDetails({
  document,
  verdicts,
  warning,
  onPick
}: {
  document: DocumentResultItem;
  verdicts: ConditionVerdictItem[];
  warning: string | null;
  onPick: (target: PreviewTarget) => void;
}) {
  return (
    <section className="drawer-tab-panel">
      <div className="section-title-row">
        <div>
          <h2>条件核验</h2>
          <span>逐项查看这份文件是否满足筛选条件</span>
        </div>
        <span>{verdicts.length} 项</span>
      </div>
      {warning ? (
        <div className="phase3-warning" role="status">
          <strong>条件核验数据加载失败</strong>
          <span>{warning}</span>
        </div>
      ) : null}
      {verdicts.length === 0 ? (
        <div className="empty-state compact">
          <strong>暂无条件核验</strong>
          <span>后端返回逐项判定后，会在这里按条件展示。</span>
        </div>
      ) : (
        <div className="condition-verdict-list">
          {verdicts.map((item) => {
            const supportingPage = item.supporting_evidence.find((evidence) => evidence.page != null)?.page ?? null;
            return (
              <button
                className="condition-verdict-row"
                key={item.verdict_id || `${item.document_uri}-${item.condition_id}`}
                type="button"
                onClick={() =>
                  onPick({
                    documentUri: document.document_uri,
                    conditionId: item.condition_id,
                    page: supportingPage
                  })
                }
              >
                <div>
                  <strong>{item.condition_id}</strong>
                  <span>{item.missing_reason || `${item.supporting_evidence.length} 条支持证据 · ${item.contradicting_evidence.length} 条反向证据`}</span>
                </div>
                <span className={`verdict-pill verdict-${item.verdict}`}>{verdictLabel(item.verdict)}</span>
                <span>{Math.round(item.confidence * 100)}%</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function EvidenceLedgerDetails({
  document,
  items,
  loading,
  warning,
  onPick
}: {
  document: DocumentResultItem;
  items: LedgerEvidenceItem[];
  loading: boolean;
  warning: string | null;
  onPick: (target: PreviewTarget) => void;
}) {
  return (
    <section className="drawer-tab-panel">
      <div className="section-title-row">
        <div>
          <h2>证据明细</h2>
          <span>仅展示当前文件参与判断的证据记录</span>
        </div>
        <span>{items.length} 条</span>
      </div>
      {warning ? (
        <div className="phase3-warning" role="status">
          <strong>证据明细数据加载失败</strong>
          <span>{warning}</span>
        </div>
      ) : null}
      {loading ? (
        <div className="empty-state compact">
          <strong>正在加载证据明细</strong>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">
          <strong>暂无证据明细</strong>
          <span>后端返回的证据条目会在这里按条件聚合。</span>
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
                {item.text ? <span>{item.text}</span> : null}
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
  const displayTitle = preview?.document_title || document?.document_title || document?.document_path || documentUri || '原文依据';
  const displaySummary = preview?.summary || document?.collection || documentUri || '点击条件核验或证据明细查看原文依据';

  return (
    <section className="phase3-panel">
      <div className="section-title-row">
        <div>
          <h2>原文依据</h2>
          <span>{document ? document.document_title || document.document_path : documentUri || '点击条件核验或证据明细查看原文依据'}</span>
        </div>
        <span>{loading ? '加载中' : context?.source_tool || '待选中'}</span>
      </div>
      {!hasContext ? (
        <div className="empty-state compact">
          <strong>请选择一份合同</strong>
          <span>点击条件核验或证据明细查看原文依据。</span>
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
              <strong>点击条件核验或证据明细查看原文依据</strong>
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
              <strong>匹配率</strong>
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
    evidence_support_rate:
      typeof document.evidence_support_rate === 'number' && Number.isFinite(document.evidence_support_rate)
        ? document.evidence_support_rate
        : typeof document.confidence === 'number' && Number.isFinite(document.confidence)
          ? document.confidence
          : 0,
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
