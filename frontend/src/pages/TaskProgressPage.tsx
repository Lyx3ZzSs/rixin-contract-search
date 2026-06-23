import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getTaskResults, getTaskSummary } from '../lib/api';
import { subscribeTaskEvents } from '../lib/sse';
import type { DocumentResultItem, StreamEvent, TaskResults, TaskSummary } from '../lib/types';

const statusSteps = [
  { key: 'uploaded', label: '提交任务' },
  { key: 'retrieving', label: '检索合同' },
  { key: 'classifying', label: '判断命中' },
  { key: 'completed', label: '生成结果' }
];

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

export function TaskProgressPage() {
  const { taskId } = useParams();
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [results, setResults] = useState<TaskResults | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
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

  const documents = useMemo(() => (results ? flattenResults(results) : []), [results]);
  const selectedDocument = documents.find((item) => item.document_uri === selectedUri) || documents[0] || null;

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
        <Link className="ghost-button" to="/">
          新建筛选
        </Link>
      </header>

      <section className="agent-status-strip" aria-label="Agent 状态">
        {statusSteps.map((step, index) => (
          <div className={`agent-status-step ${stepStatusClass(step.key, summary?.current_stage, summary?.status)}`} key={step.key}>
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
              <h2>事件流</h2>
            </div>
            <div className="event-list">
              {events.length ? events.map((event) => <span key={event.event_id}>{event.type}</span>) : <span>等待后端事件...</span>}
            </div>
          </section>
        </aside>

        <section className="panel-center">
          <ResultSummary summary={summary} results={results} />
          <section className="results-card">
            <div className="section-title-row">
              <h2>文件结果</h2>
              <span>{documents.length} 个文档</span>
            </div>
            <div className="result-list">
              {documents.length === 0 ? (
                <div className="empty-state">
                  <strong>{summary?.status === 'completed' ? '未找到符合条件的合同文件' : 'Agent 正在检索合同库'}</strong>
                  <span>完成后会在这里显示真实后端结果。</span>
                </div>
              ) : (
                documents.map((document) => (
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
          <EvidencePanel document={selectedDocument} />
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
      </div>
    </article>
  );
}

function EvidencePanel({ document }: { document: DocumentResultItem | null }) {
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

function stepStatusClass(step: string, currentStage?: string, taskStatus?: string): 'done' | 'active' | 'pending' {
  if (taskStatus === 'completed') return 'done';
  if (step === currentStage) return 'active';
  const order = ['uploaded', 'retrieving', 'classifying', 'completed'];
  const currentIndex = order.indexOf(currentStage || 'uploaded');
  const stepIndex = order.indexOf(step);
  return stepIndex >= 0 && stepIndex < currentIndex ? 'done' : 'pending';
}
