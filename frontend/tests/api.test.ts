import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiBase, createScreeningTask, getTaskSummary } from '../src/lib/api';

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
});
