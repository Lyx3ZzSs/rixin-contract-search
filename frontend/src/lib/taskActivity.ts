import type { StreamEvent, TaskSummary } from './types';

export type StageState = 'pending' | 'active' | 'done' | 'failed';
export type TaskStageKey = 'submit' | 'plan' | 'check' | 'retrieve' | 'classify' | 'complete';

export interface TaskStage {
  key: TaskStageKey;
  label: string;
  state: StageState;
}

export interface ActivityItem {
  id: string;
  type: string;
  text: string;
  timestamp: string;
}

export interface TaskActivity {
  stages: TaskStage[];
  items: ActivityItem[];
}

const STAGES: Array<Omit<TaskStage, 'state'>> = [
  { key: 'submit', label: '提交任务' },
  { key: 'plan', label: '理解筛选条件' },
  { key: 'check', label: '检查合同集合' },
  { key: 'retrieve', label: '检索证据' },
  { key: 'classify', label: '分析文档' },
  { key: 'complete', label: '生成结果' }
];

const EVENT_STAGE: Record<string, TaskStageKey> = {
  task_created: 'submit',
  task_started: 'submit',
  criteria_parsed: 'plan',
  qmd_checking: 'check',
  qmd_searching: 'retrieve',
  qmd_retrieved: 'retrieve',
  document_classified: 'classify',
  progress: 'classify',
  task_completed: 'complete',
  task_failed: 'complete'
};

const SUMMARY_STAGE: Partial<Record<string, TaskStageKey>> = {
  uploaded: 'submit',
  parsing: 'submit',
  parsed: 'plan',
  indexing: 'check',
  indexed: 'check',
  retrieving: 'retrieve',
  classifying: 'classify',
  completed: 'complete',
  failed: 'complete'
};

export function buildTaskActivity(summary: TaskSummary | null, events: StreamEvent[]): TaskActivity {
  const activeKey = activeStageKey(summary, events);
  const activeIndex = stageIndex(activeKey);

  return {
    stages: STAGES.map((stage, index): TaskStage => {
      if (summary?.status === 'completed') return { ...stage, state: 'done' };
      if (summary?.status === 'failed' && index === activeIndex) return { ...stage, state: 'failed' };
      if (index < activeIndex) return { ...stage, state: 'done' };
      if (index === activeIndex) return { ...stage, state: 'active' };
      return { ...stage, state: 'pending' };
    }),
    items: events.map((event) => ({
      id: event.event_id,
      type: event.type,
      text: activityText(event),
      timestamp: event.timestamp
    }))
  };
}

function activeStageKey(summary: TaskSummary | null, events: StreamEvent[]): TaskStageKey {
  if (summary?.status === 'completed' || summary?.status === 'failed') return 'complete';

  for (let index = events.length - 1; index >= 0; index -= 1) {
    const key = EVENT_STAGE[events[index].type];
    if (key) return key;
  }

  return SUMMARY_STAGE[summary?.current_stage || summary?.status || ''] || 'submit';
}

function activityText(event: StreamEvent): string {
  if (event.type === 'task_created') return '任务已创建';
  if (event.type === 'task_started') return '任务已开始';
  if (event.type === 'criteria_parsed') return `已解析 ${criteriaCount(event.payload)} 个筛选条件`;
  if (event.type === 'qmd_checking') return qmdCheckingText(event.payload);
  if (event.type === 'qmd_searching') return `正在检索 ${payloadString(event.payload, 'query_text') || payloadString(event.payload, 'query')}`.trim();
  if (event.type === 'qmd_retrieved') return `返回 ${payloadNumber(event.payload, 'candidate_count')} 条候选`;
  if (event.type === 'document_classified') return `${documentLabel(event.payload)} 判断为 ${payloadString(event.payload, 'decision')}`.trim();
  if (event.type === 'progress') return `已分析 ${payloadNumber(event.payload, 'reviewed')} 份文档`;
  if (event.type === 'task_completed') return '任务已生成结果';
  if (event.type === 'task_failed') return `任务失败：${payloadString(event.payload, 'message') || payloadString(event.payload, 'error_code') || 'unknown'}`;
  return event.type;
}

function criteriaCount(payload: Record<string, unknown>): number {
  if (Array.isArray(payload.conditions)) return payload.conditions.length;
  if (Array.isArray(payload.criteria)) return payload.criteria.length;
  return 0;
}

function qmdCheckingText(payload: Record<string, unknown>): string {
  const collections = Array.isArray(payload.collections) ? payload.collections.filter((item): item is string => typeof item === 'string') : [];
  return `正在检查合同集合 ${collections.join(', ')}`.trim();
}

function documentLabel(payload: Record<string, unknown>): string {
  return payloadString(payload, 'document_path') || payloadString(payload, 'document_uri') || '文档';
}

function payloadString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

function payloadNumber(payload: Record<string, unknown>, key: string): number {
  const value = payload[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function stageIndex(key: TaskStageKey): number {
  return STAGES.findIndex((stage) => stage.key === key);
}
