import { describe, expect, it } from 'vitest';
import { buildTaskActivity } from '../src/lib/taskActivity';
import type { StreamEvent, TaskSummary } from '../src/lib/types';

const baseSummary: TaskSummary = {
  task_id: 'task-1',
  title: 'GPU采购',
  raw_query: '采购GPU服务器',
  status: 'classifying',
  progress_percent: 85,
  current_stage: 'classifying',
  error_code: null,
  error_message: null,
  created_at: '2026-06-23T00:00:00Z',
  updated_at: '2026-06-23T00:00:00Z',
  completed_at: null,
  counts: { documents: 0, included: 0, uncertain: 0, excluded: 0 }
};

function event(type: string, payload: Record<string, unknown>, sequence = 1): StreamEvent {
  return {
    event_id: `task-1:${sequence}`,
    type,
    task_id: 'task-1',
    timestamp: `2026-06-23T00:00:0${sequence}Z`,
    payload
  };
}

describe('buildTaskActivity', () => {
  it('maps SSE events into six stages and activity text', () => {
    const activity = buildTaskActivity(baseSummary, [
      event('task_created', { title: 'GPU采购' }, 1),
      event('criteria_parsed', { conditions: [{ id: 'gpu', description: '采购GPU服务器' }] }, 2),
      event('qmd_checking', { collections: ['contract_docs'] }, 3),
      event('qmd_searching', { query_text: 'GPU服务器采购', condition_id: 'gpu' }, 4),
      event('qmd_retrieved', { query_text: 'GPU服务器采购', candidate_count: 3 }, 5),
      event('document_classified', { document_path: 'equipment.md', decision: 'included' }, 6)
    ]);

    expect(activity.stages.map((stage) => stage.label)).toEqual(['提交任务', '理解筛选条件', '检查合同集合', '检索证据', '分析文档', '生成结果']);
    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('done');
    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('active');
    expect(activity.items.map((item) => item.text)).toContain('已解析 1 个筛选条件');
    expect(activity.items.map((item) => item.text)).toContain('正在检索 GPU服务器采购');
    expect(activity.items.map((item) => item.text)).toContain('返回 3 条候选');
    expect(activity.items.map((item) => item.text)).toContain('equipment.md 判断为 included');
    expect(activity.items[0]).toMatchObject({
      id: 'task-1:1',
      type: 'task_created',
      timestamp: '2026-06-23T00:00:01Z'
    });
  });

  it('marks submit active and emits no items for empty events', () => {
    const activity = buildTaskActivity({ ...baseSummary, status: 'uploaded', progress_percent: 5, current_stage: 'uploaded' }, []);

    expect(activity.items).toEqual([]);
    expect(activity.stages.map((stage) => stage.state)).toEqual(['active', 'pending', 'pending', 'pending', 'pending', 'pending']);
  });

  it('marks every stage done for completed summaries', () => {
    const activity = buildTaskActivity(
      {
        ...baseSummary,
        status: 'completed',
        progress_percent: 100,
        current_stage: 'completed',
        completed_at: '2026-06-23T00:10:00Z'
      },
      [event('task_completed', { included_count: 1, uncertain_count: 0, excluded_count: 0 }, 1)]
    );

    expect(activity.stages.every((stage) => stage.state === 'done')).toBe(true);
    expect(activity.items.map((item) => item.text)).toContain('任务已生成结果');
  });

  it('marks the terminal stage failed for failed summaries', () => {
    const activity = buildTaskActivity(
      {
        ...baseSummary,
        status: 'failed',
        current_stage: 'failed',
        error_code: 'qmd_unavailable',
        error_message: 'Unable to reach qmd'
      },
      [event('task_failed', { error_code: 'qmd_unavailable', message: 'Unable to reach qmd' }, 1)]
    );

    expect(activity.stages.find((stage) => stage.key === 'complete')?.state).toBe('failed');
    expect(activity.items.map((item) => item.text)).toContain('任务失败：Unable to reach qmd');
  });
});
