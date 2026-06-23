import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TaskHistoryPage } from '../src/pages/TaskHistoryPage';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

const taskList = {
  items: [
    {
      task_id: 'task-1/with?query#hash',
      title: '采购合同筛选',
      raw_query: '合同总价超过100万元',
      status: 'completed',
      progress_percent: 100,
      current_stage: 'completed',
      error_code: null,
      error_message: null,
      created_at: '2026-06-22T08:00:00Z',
      updated_at: '2026-06-22T08:04:00Z',
      completed_at: '2026-06-22T08:04:00Z',
      counts: { documents: 3, included: 1, uncertain: 1, excluded: 1 },
      review_counts: { reviewed: 1, unreviewed: 2 }
    },
    {
      task_id: 'task-2',
      title: '服务合同筛选',
      raw_query: '包含验收付款条款',
      status: 'retrieving',
      progress_percent: 42,
      current_stage: 'retrieving',
      error_code: null,
      error_message: null,
      created_at: '2026-06-21T10:00:00Z',
      updated_at: '2026-06-21T10:01:00Z',
      completed_at: null,
      counts: { documents: 0, included: 0, uncertain: 0, excluded: 0 },
      review_counts: { reviewed: 0, unreviewed: 0 }
    }
  ],
  total: 2,
  limit: 50,
  offset: 0
};

describe('TaskHistoryPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders task list rows with counts, review progress, and detail links', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(taskList)));

    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <TaskHistoryPage />
      </MemoryRouter>
    );

    expect(screen.getByText('正在加载任务历史...')).toBeInTheDocument();
    expect(await screen.findByText('采购合同筛选')).toBeInTheDocument();
    expect(screen.getByText('合同总价超过100万元')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('3 文档 · 1 入选 · 1 待确认 · 1 不符合')).toBeInTheDocument();
    expect(screen.getByText('1 / 3 已复核')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: '查看详情' })[0]).toHaveAttribute('href', '/tasks/task-1%2Fwith%3Fquery%23hash');
  });

  it('passes filters to the list API and navigates to copied task detail', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/copy') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({ task_id: 'task-copy/with?query#hash', title: '复制任务', raw_query: '合同总价', status: 'uploaded', progress_percent: 0, events_url: '', results_url: '' }));
      }
      return Promise.resolve(jsonResponse({ ...taskList, total: 1, items: [taskList.items[0]] }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <Routes>
          <Route path="/tasks" element={<TaskHistoryPage />} />
          <Route path="/tasks/:taskId" element={<LocationEcho />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByText('采购合同筛选');
    await user.type(screen.getByLabelText('关键词'), '采购');
    await user.selectOptions(screen.getByLabelText('任务状态'), 'completed');
    await user.selectOptions(screen.getByLabelText('排序'), 'created_asc');

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks?status=completed&q=%E9%87%87%E8%B4%AD&sort=created_asc&limit=50&offset=0');
    });

    await user.click(screen.getByRole('button', { name: '复制任务' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1%2Fwith%3Fquery%23hash/copy', { method: 'POST' });
    });
    expect(await screen.findByText('/tasks/task-copy%2Fwith%3Fquery%23hash')).toBeInTheDocument();
  });

  it('clears stale rows and shows only an error state when reload fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(taskList))
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: 'history backend unavailable' }), { status: 503, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <TaskHistoryPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('采购合同筛选')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('任务状态'), 'completed');

    expect(await screen.findByText('history backend unavailable')).toBeInTheDocument();
    expect(screen.queryByText('采购合同筛选')).not.toBeInTheDocument();
    expect(screen.queryByText('暂无筛选任务')).not.toBeInTheDocument();
  });

  it('shows Redis and RQ guidance when copied task enqueue fails', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/copy') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'enqueue_failed', message: 'Unable to enqueue screening task' } }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          })
        );
      }
      return Promise.resolve(jsonResponse(taskList));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <TaskHistoryPage />
      </MemoryRouter>
    );

    await screen.findByText('采购合同筛选');
    await user.click(screen.getAllByRole('button', { name: '复制任务' })[0]);

    expect(await screen.findByText(/Redis\/RQ/)).toBeInTheDocument();
    expect(screen.queryByText('Unable to enqueue screening task')).not.toBeInTheDocument();
  });
});

function LocationEcho() {
  const location = useLocation();
  return <div>{location.pathname}</div>;
}
