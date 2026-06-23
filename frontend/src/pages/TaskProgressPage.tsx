import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { exportTaskUrl, getTaskResults, getTaskSummary, reviewDocumentResult } from '../lib/api';
import { getReviewerName, setReviewerName } from '../lib/reviewer';
import { subscribeTaskEvents } from '../lib/sse';
import { buildTaskActivity } from '../lib/taskActivity';
import type { DocumentResultItem, ResultDecision, ReviewStatus, StreamEvent, TaskResults, TaskSummary } from '../lib/types';

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

export function TaskProgressPage() {
  const { taskId } = useParams();
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [results, setResults] = useState<TaskResults | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>('all');
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('all');
  const [keywordFilter, setKeywordFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const activeTaskId = taskId;
    let cancelled = false;

    async function loadInitial() {
      try {
        const nextSummary = await getTaskSummary(activeTaskId);
        if (cancelled) return;
        setSummary(nextSummary);
        if (nextSummary.status === 'completed') await loadFinal(activeTaskId, cancelled);
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
        void loadFinal(activeTaskId, cancelled);
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [taskId]);

  async function loadFinal(id: string, cancelled: boolean) {
    const [nextSummary, nextResults] = await Promise.all([getTaskSummary(id), getTaskResults(id)]);
    if (cancelled) return;
    setSummary(nextSummary);
    setResults(nextResults);
    const first = flattenResults(nextResults)[0];
    setSelectedUri((current) => current || first?.document_uri || null);
  }

  function handleReviewed(result: DocumentResultItem) {
    setResults((current) => (current ? updateResultInBuckets(current, result) : current));
    setSelectedUri(result.document_uri);
  }

  const activity = useMemo(() => buildTaskActivity(summary, events), [summary, events]);
  const documents = useMemo(() => (results ? flattenResults(results) : []), [results]);
  const filteredDocuments = useMemo(
    () => documents.filter((document) => matchesFilters(document, decisionFilter, reviewFilter, keywordFilter)),
    [documents, decisionFilter, keywordFilter, reviewFilter]
  );
  const selectedDocument = filteredDocuments.find((item) => item.document_uri === selectedUri) || filteredDocuments[0] || null;
  const isCompleted = summary?.status === 'completed';

  if (!taskId) {
    return <div className="agent-shell">缺少任务 ID</div>;
  }

  return (
    <main className="agent-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TASK {taskId}</p>
          <h1>{summary?.title || '合同筛选任务'}</h1>
          <p className="topbar-subtitle">{summary?.raw_query || '正在加载任务信息'}</p>
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
              <p>{summary?.current_stage || 'loading'}</p>
            </div>
            <div className="progress-meter" data-testid="event-progress">
              <span style={{ width: `${summary?.progress_percent ?? 0}%` }} />
            </div>
            <strong>{summary?.progress_percent ?? 0}%</strong>
            {error || summary?.status === 'failed' ? <p className="error-text">{error || summary?.error_message || '任务执行失败'}</p> : null}
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
          <ResultSummary summary={summary} results={results} />
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
                  <strong>{documents.length ? '没有符合筛选条件的文档' : summary?.status === 'completed' ? '未找到符合条件的合同文件' : 'Agent 正在检索合同库'}</strong>
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
    <article className={`contract-card ${selected ? 'is-selected' : ''}`} onClick={onSelect} role="button" tabIndex={0}>
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

function EvidencePanel({ document, taskId, onReviewed }: { document: DocumentResultItem | null; taskId: string; onReviewed: (result: DocumentResultItem) => void }) {
  const [reviewerName, setReviewerNameState] = useState(() => getReviewerName());
  const [reviewDecision, setReviewDecision] = useState<ResultDecision>('included');
  const [reviewNote, setReviewNote] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!document) return;
    setReviewDecision(document.review_decision || document.decision);
    setReviewNote(document.review_note || '');
    setSaveError(null);
  }, [document?.result_id]);

  async function handleSaveReview() {
    if (!document) return;
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
      const response = await reviewDocumentResult(taskId, document.result_id, {
        review_status: 'reviewed',
        review_decision: reviewDecision,
        review_note: reviewNote.trim() || undefined,
        reviewer_name: trimmedReviewer
      });
      onReviewed(response.result);
      setReviewDecision(response.result.review_decision || response.result.decision);
      setReviewNote(response.result.review_note || '');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存复核失败');
    } finally {
      setSaving(false);
    }
  }

  if (!document) {
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
            <p>当前文档：{document.document_title || document.document_path}</p>
          </div>
        </div>
        <section className="detail-block">
          <h3>判断结果</h3>
          <p>
            判断：{decisionLabels[document.decision]} · {document.reason}
          </p>
          {document.review_status === 'reviewed' ? (
            <div className="review-status-box">
              <strong>已复核：{document.reviewer_name || '未记录复核人'}</strong>
              <span>人工结论：{document.review_decision ? decisionLabels[document.review_decision] : '未记录'}</span>
              {document.reviewed_at ? <span>复核时间：{formatDateTime(document.reviewed_at)}</span> : null}
              {document.review_note ? <p>{document.review_note}</p> : null}
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
          {document.evidence.length ? (
            document.evidence.map((item, index) => (
              <article className="snippet-item" key={`${item.condition_id}-${index}`}>
                <div className="snippet-head">
                  <strong>{item.condition_id}</strong>
                  <span>{item.page ? `第 ${item.page} 页` : '页码未知'}</span>
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
