import type {
  CreateTaskRequest,
  CreateTaskResponse,
  ExportFormat,
  QmdStatus,
  ReviewResultRequest,
  ReviewResultResponse,
  RuntimeStatus,
  TaskListParams,
  TaskListResponse,
  TaskResults,
  TaskSummary
} from './types';

export const apiBase = '';

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = (typeof body?.error === 'string' ? body.error : body?.error?.message) || message;
    } catch {
      // Keep the generic message when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function pathSegment(value: string): string {
  return encodeURIComponent(value);
}

function buildQuery(params: TaskListParams): string {
  const search = new URLSearchParams();
  if (params.status !== undefined && params.status !== 'all') search.set('status', params.status);
  if (params.q !== undefined && params.q !== '') search.set('q', params.q);
  if (params.sort !== undefined) search.set('sort', params.sort);
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  const query = search.toString();
  return query ? `?${query}` : '';
}

export async function createScreeningTask(payload: CreateTaskRequest): Promise<CreateTaskResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readJson<CreateTaskResponse>(response);
}

export async function listScreeningTasks(params: TaskListParams = {}): Promise<TaskListResponse> {
  const query = buildQuery(params);
  const response = await fetch(`${apiBase}/api/screening-tasks${query}`);
  return readJson<TaskListResponse>(response);
}

export async function copyScreeningTask(taskId: string): Promise<CreateTaskResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}/copy`, { method: 'POST' });
  return readJson<CreateTaskResponse>(response);
}

export async function getTaskSummary(taskId: string): Promise<TaskSummary> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}`);
  return readJson<TaskSummary>(response);
}

export async function getTaskResults(taskId: string): Promise<TaskResults> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}/results`);
  return readJson<TaskResults>(response);
}

export async function reviewDocumentResult(taskId: string, resultId: string, payload: ReviewResultRequest): Promise<ReviewResultResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}/results/${pathSegment(resultId)}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readJson<ReviewResultResponse>(response);
}

export function exportTaskUrl(taskId: string, format: ExportFormat): string {
  return `${apiBase}/api/screening-tasks/${pathSegment(taskId)}/export.${format}`;
}

export async function getQmdStatus(): Promise<QmdStatus> {
  const response = await fetch(`${apiBase}/api/qmd/status`);
  return readJson<QmdStatus>(response);
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const response = await fetch(`${apiBase}/api/runtime/status`);
  return readJson<RuntimeStatus>(response);
}
