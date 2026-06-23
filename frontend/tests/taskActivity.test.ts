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

  it('marks the failed stage from task_failed payload stage', () => {
    const activity = buildTaskActivity(
      {
        ...baseSummary,
        status: 'failed',
        current_stage: 'failed',
        error_code: 'qmd_command_failed',
        error_message: 'qmd command failed'
      },
      [event('task_failed', { stage: 'retrieving', error_code: 'qmd_command_failed', message: 'qmd command failed' }, 1)]
    );

    expect(activity.stages.map((stage) => [stage.key, stage.state])).toEqual([
      ['submit', 'pending'],
      ['plan', 'pending'],
      ['check', 'pending'],
      ['retrieve', 'failed'],
      ['classify', 'pending'],
      ['complete', 'pending']
    ]);
  });

  it('falls back to reached event stage when failed summary has no payload stage', () => {
    const activity = buildTaskActivity(
      {
        ...baseSummary,
        status: 'failed',
        current_stage: 'failed',
        error_code: 'worker_unexpected_error',
        error_message: 'Unexpected worker error'
      },
      [
        event('document_classified', { document_path: 'equipment.md', decision: 'uncertain' }, 1),
        event('task_failed', { error_code: 'worker_unexpected_error', message: 'Unexpected worker error' }, 2)
      ]
    );

    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('failed');
    expect(activity.stages.find((stage) => stage.key === 'complete')?.state).toBe('pending');
  });

  it('keeps active stage monotonic for duplicate or out-of-order events', () => {
    const activity = buildTaskActivity(
      { ...baseSummary, status: 'retrieving', current_stage: 'retrieving' },
      [
        event('document_classified', { document_uri: 'qmd://contracts/equipment.md', decision: 'uncertain' }, 1),
        event('qmd_searching', { query_text: 'GPU服务器采购', condition_id: 'gpu' }, 2)
      ]
    );

    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('done');
    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('active');
  });

  it('uses summary stage as part of monotonic stage precedence', () => {
    const activity = buildTaskActivity(baseSummary, [event('qmd_searching', { query_text: 'GPU服务器采购', condition_id: 'gpu' }, 1)]);

    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('done');
    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('active');
    expect(activity.stages.find((stage) => stage.key === 'plan')?.state).toBe('pending');
    expect(activity.stages.find((stage) => stage.key === 'check')?.state).toBe('pending');
  });

  it('keeps unknown events as items without advancing stage progress', () => {
    const activity = buildTaskActivity({ ...baseSummary, status: 'uploaded', progress_percent: 5, current_stage: 'uploaded' }, [event('custom_event', { value: 1 }, 1)]);

    expect(activity.items).toEqual([
      {
        id: 'task-1:1',
        type: 'custom_event',
        text: 'custom_event',
        timestamp: '2026-06-23T00:00:01Z'
      }
    ]);
    expect(activity.stages.map((stage) => stage.state)).toEqual(['active', 'pending', 'pending', 'pending', 'pending', 'pending']);
  });

  it('does not mark missing intermediate stages done from summary alone when events exist', () => {
    const activity = buildTaskActivity({ ...baseSummary, status: 'retrieving', current_stage: 'retrieving', progress_percent: 35 }, [event('task_started', {}, 1)]);

    expect(activity.stages.map((stage) => [stage.key, stage.state])).toEqual([
      ['submit', 'done'],
      ['plan', 'pending'],
      ['check', 'pending'],
      ['retrieve', 'active'],
      ['classify', 'pending'],
      ['complete', 'pending']
    ]);
  });

  it('uses snapshot stage and friendly activity text when summary is unavailable', () => {
    const activity = buildTaskActivity(null, [event('snapshot', { current_stage: 'retrieving', status: 'retrieving', progress_percent: 35 }, 1)]);

    expect(activity.items[0]).toMatchObject({
      type: 'snapshot',
      text: '已同步任务状态：35%'
    });
    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('active');
  });

  it('does not let a snapshot regress later event evidence', () => {
    const activity = buildTaskActivity(null, [
      event('document_classified', { document_path: 'equipment.md', decision: 'included' }, 1),
      event('snapshot', { current_stage: 'retrieving', status: 'retrieving', progress_percent: 35 }, 2)
    ]);

    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('active');
    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).not.toBe('active');
  });

  it('marks all stages done for completed snapshots when summary is unavailable', () => {
    const activity = buildTaskActivity(null, [event('snapshot', { status: 'completed', current_stage: 'completed', progress_percent: 100 }, 1)]);

    expect(activity.stages.every((stage) => stage.state === 'done')).toBe(true);
  });

  it('marks failed stage from failed snapshots when summary is unavailable', () => {
    const activity = buildTaskActivity(null, [event('snapshot', { status: 'failed', current_stage: 'retrieving', progress_percent: 35 }, 1)]);

    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('failed');
    expect(activity.stages.find((stage) => stage.key === 'complete')?.state).toBe('pending');
  });

  it('falls back to complete stage for failed snapshots without a stage hint', () => {
    const activity = buildTaskActivity(null, [event('snapshot', { status: 'failed', progress_percent: 35 }, 1)]);

    expect(activity.stages.find((stage) => stage.key === 'complete')?.state).toBe('failed');
  });

  it('infers failed snapshot stage from latest event evidence when current stage is terminal failed', () => {
    const activity = buildTaskActivity(null, [
      event('qmd_retrieved', { query_text: 'GPU服务器采购', candidate_count: 3 }, 1),
      event('document_classified', { document_path: 'equipment.md', decision: 'uncertain' }, 2),
      event('snapshot', { status: 'failed', current_stage: 'failed', progress_percent: 90 }, 3)
    ]);

    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('failed');
    expect(activity.stages.find((stage) => stage.key === 'complete')?.state).toBe('pending');
  });

  it('prefers explicit non-terminal snapshot failed stage over event evidence', () => {
    const activity = buildTaskActivity(null, [
      event('document_classified', { document_path: 'equipment.md', decision: 'uncertain' }, 1),
      event('snapshot', { status: 'failed', stage: 'retrieving', current_stage: 'failed', progress_percent: 90 }, 2)
    ]);

    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('failed');
    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('pending');
  });
});
