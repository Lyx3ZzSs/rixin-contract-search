import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createScreeningTask } from '../lib/api';

export function UploadPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmedQuery = query.trim();

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
            {error ? <p className="error-text">{error}</p> : null}
            <p className="field-help">当前版本直接使用后端合同集合，不在页面上传文件。</p>
          </form>
        </aside>

        <section className="panel-center">
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
