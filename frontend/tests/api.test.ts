import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  apiBase,
  copyScreeningTask,
  createScreeningTask,
  exportTaskUrl,
  getQmdStatus,
  getRuntimeStatus,
  getTaskSummary,
  listScreeningTasks,
  reviewDocumentResult
} from '../src/lib/api';

describe('api client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('uses same-origin API paths by default', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: 'task-1' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await getTaskSummary('task-1');

    expect(apiBase).toBe('');
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1');
  });

  it('creates screening tasks with a JSON query only', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: 'task-1' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await createScreeningTask({ query: '合同总价' });

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: '合同总价' })
    });
  });

  it('lists screening tasks with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await listScreeningTasks({ status: 'completed', q: 'GPU', sort: 'created_desc', limit: 20, offset: 0 });

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks?status=completed&q=GPU&sort=created_desc&limit=20&offset=0');
  });

  it('omits empty task list filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await listScreeningTasks({ status: 'all', q: '', sort: undefined, limit: undefined, offset: 0 });

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks?offset=0');
  });

  it('copies screening tasks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: 'task-2' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await copyScreeningTask('task-1');

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/copy', { method: 'POST' });
  });

  it('reviews document results', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ result: { result_id: 'result-1' } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await reviewDocumentResult('task-1', 'result-1', {
      review_status: 'reviewed',
      review_decision: 'included',
      review_note: '人工确认',
      reviewer_name: '张三'
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/results/result-1/review', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        review_status: 'reviewed',
        review_decision: 'included',
        review_note: '人工确认',
        reviewer_name: '张三'
      })
    });
  });

  it('builds export URLs and loads health statuses', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ available: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ env_file: '.env' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    expect(exportTaskUrl('task-1', 'csv')).toBe('/api/screening-tasks/task-1/export.csv');
    expect(exportTaskUrl('task-1', 'xlsx')).toBe('/api/screening-tasks/task-1/export.xlsx');
    expect(exportTaskUrl('task-1', 'json')).toBe('/api/screening-tasks/task-1/export.json');

    await getQmdStatus();
    await getRuntimeStatus();

    expect(fetchMock).toHaveBeenCalledWith('/api/qmd/status');
    expect(fetchMock).toHaveBeenCalledWith('/api/runtime/status');
  });

  it('throws server error messages from new clients', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: 'Invalid task status filter' } }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(listScreeningTasks({ status: 'completed' })).rejects.toThrow('Invalid task status filter');
  });
});
