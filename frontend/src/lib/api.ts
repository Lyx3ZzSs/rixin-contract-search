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

export class ApiClientError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    let code: string | undefined;
    try {
      const body = await response.json();
      if (typeof body?.error === 'string') {
        message = body.error;
      } else if (body?.error && typeof body.error === 'object') {
        message = typeof body.error.message === 'string' ? body.error.message : message;
        code = typeof body.error.code === 'string' ? body.error.code : undefined;
      }
    } catch {
      // Keep the generic message when the server did not return JSON.
    }
    throw new ApiClientError(message, code);
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
