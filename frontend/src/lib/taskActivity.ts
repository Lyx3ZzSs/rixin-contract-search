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
  submit: 'submit',
  submitted: 'submit',
  parsed: 'plan',
  plan: 'plan',
  planning: 'plan',
  criteria_parsed: 'plan',
  indexing: 'check',
  indexed: 'check',
  check: 'check',
  checking: 'check',
  qmd_checking: 'check',
  qmd_indexing: 'check',
  qmd_indexed: 'check',
  retrieving: 'retrieve',
  retrieve: 'retrieve',
  retrieval: 'retrieve',
  qmd_searching: 'retrieve',
  qmd_retrieved: 'retrieve',
  classifying: 'classify',
  classify: 'classify',
  classification: 'classify',
  document_classified: 'classify',
  progress: 'classify',
  completed: 'complete',
  complete: 'complete',
  failed: 'complete'
};

export function buildTaskActivity(summary: TaskSummary | null, events: StreamEvent[]): TaskActivity {
  const completed = summary?.status === 'completed' || events.some((event) => event.type === 'task_completed' || snapshotStatus(event) === 'completed');
  const evidenceKeys = eventEvidenceKeys(events);
  const evidenceSet = new Set(evidenceKeys);
  const failedKey = completed ? null : failedStageKey(summary, events);
  const activeKey = failedKey || activeStageKey(summary, events);

  return {
    stages: STAGES.map((stage): TaskStage => {
      if (completed) return { ...stage, state: 'done' };
      if (failedKey) {
        if (stage.key === failedKey) return { ...stage, state: 'failed' };
        if (stageIndex(stage.key) < stageIndex(failedKey) && evidenceSet.has(stage.key)) return { ...stage, state: 'done' };
        return { ...stage, state: 'pending' };
      }
      if (stage.key === activeKey) return { ...stage, state: 'active' };
      if (stageIndex(stage.key) < stageIndex(activeKey) && evidenceSet.has(stage.key)) return { ...stage, state: 'done' };
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
  return maxStageKey([...eventEvidenceKeys(events), ...stageHintKeys(summary, events, true)]);
}

function failedStageKey(summary: TaskSummary | null, events: StreamEvent[]): TaskStageKey | null {
  const failureKeys = events
    .filter((event) => event.type === 'task_failed')
    .map((event) => nonTerminalStageKey(event.payload.stage))
    .filter((key): key is TaskStageKey => Boolean(key));
  const failedSnapshotKeys = events
    .filter((event) => snapshotStatus(event) === 'failed')
    .map((event) => nonTerminalStageKey(event.payload.stage) || nonTerminalStageKey(event.payload.current_stage))
    .filter((key): key is TaskStageKey => Boolean(key));

  if (failureKeys.length > 0) return maxStageKey(failureKeys);
  if (failedSnapshotKeys.length > 0) return maxStageKey(failedSnapshotKeys);
  if (summary?.status !== 'failed' && !events.some((event) => event.type === 'task_failed' || snapshotStatus(event) === 'failed')) return null;
  const progressKeys = [...eventEvidenceKeys(events), ...stageHintKeys(summary, events, false)];
  if (progressKeys.length > 0) return maxStageKey(progressKeys);
  return 'complete';
}

function eventEvidenceKeys(events: StreamEvent[]): TaskStageKey[] {
  return events
    .filter((event) => event.type !== 'task_failed' && event.type !== 'snapshot')
    .map((event) => EVENT_STAGE[event.type])
    .filter((key): key is TaskStageKey => Boolean(key));
}

function stageHintKeys(summary: TaskSummary | null, events: StreamEvent[], includeTerminalHints: boolean): TaskStageKey[] {
  const keys: TaskStageKey[] = [];
  const summaryStageKey = backendStageKey(summary?.current_stage);
  const summaryStatusKey = backendStageKey(summary?.status);

  if (summaryStageKey && (includeTerminalHints || summaryStageKey !== 'complete')) keys.push(summaryStageKey);
  if (summaryStatusKey && (includeTerminalHints || summaryStatusKey !== 'complete')) keys.push(summaryStatusKey);

  for (const event of events) {
    if (event.type !== 'snapshot') continue;
    const snapshotStageKey = backendStageKey(event.payload.current_stage);
    const snapshotStatusKey = backendStageKey(event.payload.status);
    if (snapshotStageKey && (includeTerminalHints || snapshotStageKey !== 'complete')) keys.push(snapshotStageKey);
    if (snapshotStatusKey && (includeTerminalHints || snapshotStatusKey !== 'complete')) keys.push(snapshotStatusKey);
  }

  return includeTerminalHints && keys.length === 0 ? ['submit'] : keys;
}

function maxStageKey(keys: TaskStageKey[]): TaskStageKey {
  return keys.reduce((current, key) => (stageIndex(key) > stageIndex(current) ? key : current), 'submit');
}

function backendStageKey(stage: unknown): TaskStageKey | null {
  return typeof stage === 'string' ? SUMMARY_STAGE[stage.toLowerCase()] || null : null;
}

function nonTerminalStageKey(stage: unknown): TaskStageKey | null {
  const key = backendStageKey(stage);
  return key && key !== 'complete' ? key : null;
}

function snapshotStatus(event: StreamEvent): string {
  return event.type === 'snapshot' ? payloadString(event.payload, 'status').toLowerCase() : '';
}

function activityText(event: StreamEvent): string {
  if (event.type === 'snapshot') return snapshotText(event.payload);
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

function snapshotText(payload: Record<string, unknown>): string {
  const progress = payloadNumber(payload, 'progress_percent');
  return progress > 0 ? `已同步任务状态：${progress}%` : '已同步任务状态';
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
