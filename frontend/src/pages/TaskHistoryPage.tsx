import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { copyScreeningTask, listScreeningTasks } from '../lib/api';
import type { TaskListItem, TaskListStatusFilter, TaskSort } from '../lib/types';

const statusOptions: Array<{ value: TaskListStatusFilter; label: string }> = [
  { value: 'all', label: '全部任务' },
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' }
];

const sortOptions: Array<{ value: TaskSort; label: string }> = [
  { value: 'created_desc', label: '最新创建' },
  { value: 'created_asc', label: '最早创建' }
];

export function TaskHistoryPage() {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<TaskListStatusFilter>('all');
  const [sort, setSort] = useState<TaskSort>('created_desc');
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyingTaskId, setCopyingTaskId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function loadTasks() {
      try {
        const response = await listScreeningTasks({
          status,
          q: keyword.trim(),
          sort,
          limit: 50,
          offset: 0
        });
        if (cancelled) return;
        setTasks(response.items);
        setTotal(response.total);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载任务历史失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadTasks();

    return () => {
      cancelled = true;
    };
  }, [keyword, status, sort]);

  async function handleCopyTask(taskId: string) {
    if (copyingTaskId) return;
    setCopyingTaskId(taskId);
    setError(null);
    try {
      const copied = await copyScreeningTask(taskId);
      navigate(taskDetailPath(copied.task_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : '复制任务失败');
    } finally {
      setCopyingTaskId(null);
    }
  }

  return (
    <main className="agent-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TASK HISTORY</p>
          <h1>任务历史</h1>
          <p className="topbar-subtitle">检索已提交的合同筛选任务，查看结果或复制条件再次执行。</p>
        </div>
        <Link className="ghost-button" to="/">
          新建筛选
        </Link>
      </header>

      <section className="history-workbench" aria-label="任务历史工作区">
        <section className="history-toolbar" aria-label="任务筛选">
          <label className="history-filter">
            <span>关键词</span>
            <input aria-label="关键词" value={keyword} onChange={(event) => setKeyword(event.currentTarget.value)} placeholder="标题或筛选条件" />
          </label>
          <label className="history-filter">
            <span>任务状态</span>
            <select aria-label="任务状态" value={status} onChange={(event) => setStatus(event.currentTarget.value as TaskListStatusFilter)}>
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="history-filter">
            <span>排序</span>
            <select aria-label="排序" value={sort} onChange={(event) => setSort(event.currentTarget.value as TaskSort)}>
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <div className="history-total" aria-label="任务总数">
            {total} 个任务
          </div>
        </section>

        {error ? <p className="error-text">{error}</p> : null}

        <section className="results-card history-results">
          <div className="section-title-row">
            <h2>筛选任务</h2>
            <span>{loading ? '加载中' : `${tasks.length} / ${total}`}</span>
          </div>

          {loading ? (
            <div className="empty-state">
              <strong>正在加载任务历史...</strong>
            </div>
          ) : tasks.length === 0 ? (
            <div className="empty-state">
              <strong>暂无筛选任务</strong>
              <span>创建任务后会在这里显示历史记录。</span>
            </div>
          ) : (
            <div className="task-history-list">
              {tasks.map((task) => (
                <TaskHistoryRow key={task.task_id} task={task} copying={copyingTaskId === task.task_id} onCopy={() => void handleCopyTask(task.task_id)} />
              ))}
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function TaskHistoryRow({ task, copying, onCopy }: { task: TaskListItem; copying: boolean; onCopy: () => void }) {
  const reviewed = task.review_counts.reviewed;
  const reviewTotal = task.review_counts.reviewed + task.review_counts.unreviewed;
  return (
    <article className="task-history-row">
      <div className="task-history-main">
        <span className={`status-pill ${task.status}`}>{task.status}</span>
        <h3>{task.title}</h3>
        <p>{task.raw_query}</p>
        <p className="task-history-countline">
          {task.counts.documents} 文档 · {task.counts.included} 入选 · {task.counts.uncertain} 待确认 · {task.counts.excluded} 不符合
        </p>
        <time dateTime={task.created_at}>{formatDateTime(task.created_at)}</time>
      </div>
      <div className="task-history-metrics" aria-label={`${task.title} 统计`}>
        <span>{task.counts.documents} 文档</span>
        <span>{task.counts.included} 入选</span>
        <span>{task.counts.uncertain} 待确认</span>
        <span>{task.counts.excluded} 不符合</span>
        <strong>{reviewed} / {reviewTotal} 已复核</strong>
      </div>
      <div className="task-history-actions">
        <Link className="ghost-button" to={taskDetailPath(task.task_id)}>
          查看详情
        </Link>
        <button className="mini-button" type="button" disabled={copying} onClick={onCopy}>
          {copying ? '复制中...' : '复制任务'}
        </button>
      </div>
    </article>
  );
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function taskDetailPath(taskId: string): string {
  return `/tasks/${encodeURIComponent(taskId)}`;
}
