import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createScreeningTask, getQmdStatus, getRuntimeStatus } from '../lib/api';
import type { QmdCollectionStatus, QmdStatus, RuntimeStatus } from '../lib/types';

export function UploadPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qmdStatus, setQmdStatus] = useState<QmdStatus | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const trimmedQuery = query.trim();

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const [nextQmdStatus, nextRuntimeStatus] = await Promise.all([getQmdStatus(), getRuntimeStatus()]);
        if (cancelled) return;
        setQmdStatus(nextQmdStatus);
        setRuntimeStatus(nextRuntimeStatus);
      } catch (err) {
        if (!cancelled) setHealthError(err instanceof Error ? err.message : '加载运行状态失败');
      }
    }

    void loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!trimmedQuery || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const task = await createScreeningTask({ query: trimmedQuery });
      navigate(`/tasks/${task.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建筛选任务失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="agent-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">CONTRACT FILE AGENT</p>
          <h1>合同筛选审查台</h1>
          <p className="topbar-subtitle">输入筛选条件，后端 Agent 会检索 qmd 合同集合并返回证据。</p>
        </div>
      </header>

      <section className="agent-status-strip" aria-label="Agent 状态">
        {['提交任务', '理解条件', '检索合同', '生成结果'].map((step, index) => (
          <div className={`agent-status-step ${index === 0 ? 'active' : 'pending'}`} key={step}>
            <span>{index + 1}</span>
            <strong>{step}</strong>
          </div>
        ))}
      </section>

      <section className="workspace single-workspace" aria-label="合同文件筛选工作区">
        <aside className="panel-left">
          <form className="side-card task-card" onSubmit={handleSubmit}>
            <div className="card-heading">
              <h2>筛选任务</h2>
              <p>描述你要找的合同类型、金额、主体、条款或风险条件。</p>
            </div>
            <label className="field-label" htmlFor="screening-query">
              筛选条件
            </label>
            <textarea
              id="screening-query"
              aria-label="筛选条件"
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="例如：筛选合同总价超过100万元且包含验收付款条款的采购合同"
            />
            <button className="primary-button full-width" type="submit" disabled={!trimmedQuery || submitting}>
              {submitting ? '正在创建任务...' : '开始筛选'}
            </button>
            <Link className="ghost-button full-width center-button" to="/tasks">
              查看任务历史
            </Link>
            {error ? <p className="error-text">{error}</p> : null}
            <p className="field-help">当前版本直接使用后端合同集合，不在页面上传文件。</p>
          </form>
        </aside>

        <section className="panel-center">
          <HealthSummary qmdStatus={qmdStatus} runtimeStatus={runtimeStatus} error={healthError} />
          <section className="summary-card">
            <div>
              <p className="eyebrow">WORKFLOW</p>
              <h2>真实任务流已接入</h2>
              <p>任务创建后会跳转到进度页，实时读取后端 SSE，并在完成后加载文档结果和证据。</p>
            </div>
            <div className="summary-stats">
              <span>
                <strong>1</strong>任务
              </span>
              <span>
                <strong>SSE</strong>进度
              </span>
              <span>
                <strong>qmd</strong>检索
              </span>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

function HealthSummary({ qmdStatus, runtimeStatus, error }: { qmdStatus: QmdStatus | null; runtimeStatus: RuntimeStatus | null; error: string | null }) {
  const configuredCollections = qmdStatus?.configured_collections?.length ? qmdStatus.configured_collections : qmdStatus?.collections || [];
  const currentCollections = runtimeStatus?.qmd.collections.length ? runtimeStatus.qmd.collections : configuredCollections.map((collection) => collection.name);
  const qmdError = qmdStatus && !qmdStatus.available && qmdStatus.error ? sanitizeStatusError(qmdStatus.error) : null;
  return (
    <section className="summary-card health-summary">
      <div>
        <p className="eyebrow">RUNTIME</p>
        <h2>当前合同集合</h2>
        <p>{currentCollections.length ? currentCollections.join('、') : '正在读取后端配置'}</p>
        {error ? <p className="error-text compact">{error}</p> : null}
        {qmdError ? <p className="error-text compact">{qmdError}</p> : null}
      </div>
      <div className="health-grid">
        <section className="health-block" aria-label="合同集合状态">
          <h3>配置集合</h3>
          <div className="health-rows">
            {configuredCollections.length ? (
              configuredCollections.map((collection) => <CollectionRow collection={collection} key={collection.name} />)
            ) : (
              <span className="muted-row">等待 qmd 状态</span>
            )}
          </div>
        </section>
        <section className="health-block" aria-label="LLM 状态">
          <h3>LLM</h3>
          <div className="health-rows">
            <span>
              <strong>{runtimeStatus?.llm.model || '读取中'}</strong>
              <em>{runtimeStatus?.llm.has_api_key ? '已配置' : '未配置'}</em>
            </span>
            <small>{runtimeStatus?.llm.base_url || '等待运行配置'}</small>
          </div>
        </section>
      </div>
    </section>
  );
}

function sanitizeStatusError(value: string): string {
  return value.trim();
}

function CollectionRow({ collection }: { collection: QmdCollectionStatus }) {
  return (
    <span>
      <strong>{collection.name}</strong>
      <em>{collection.document_count} 文档 · {collection.exists ? '可用' : '不可用'}</em>
    </span>
  );
}
