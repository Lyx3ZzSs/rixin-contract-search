export type TaskStatus = 'uploaded' | 'parsing' | 'parsed' | 'indexing' | 'indexed' | 'retrieving' | 'classifying' | 'completed' | 'failed';

export type ResultDecision = 'included' | 'uncertain' | 'excluded';

export type ReviewStatus = 'unreviewed' | 'reviewed';

export type TaskListStatusFilter = 'all' | 'active' | TaskStatus;

export type TaskSort = 'created_desc' | 'created_asc';

export type ExportFormat = 'csv' | 'xlsx' | 'json';

export interface CreateTaskRequest {
  query: string;
  title?: string;
}

export interface CreateTaskResponse {
  task_id: string;
  title: string;
  raw_query: string;
  status: TaskStatus;
  progress_percent: number;
  events_url: string;
  results_url: string;
}

export interface TaskCounts {
  documents: number;
  included: number;
  uncertain: number;
  excluded: number;
}

export interface TaskSummary {
  task_id: string;
  title: string;
  raw_query: string;
  status: TaskStatus;
  progress_percent: number;
  current_stage: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  counts: TaskCounts;
}

export interface ReviewCounts {
  unreviewed: number;
  reviewed: number;
}

export interface TaskListItem extends TaskSummary {
  review_counts: ReviewCounts;
}

export interface TaskListResponse {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskListParams {
  status?: TaskListStatusFilter;
  q?: string;
  sort?: TaskSort;
  limit?: number;
  offset?: number;
}

export interface EvidenceItem {
  page: number | null;
  text: string;
  source: 'qmd';
  score: number | null;
  condition_id: string;
  artifact_ref: string | null;
}

export interface DocumentResultItem {
  result_id: string;
  document_uri: string;
  document_path: string;
  document_title: string | null;
  collection: string;
  decision: ResultDecision;
  reason: string;
  matched_conditions: string[];
  missing_conditions: string[];
  evidence: EvidenceItem[];
  confidence: number;
  review_status: ReviewStatus;
  review_decision: ResultDecision | null;
  review_note: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewResultRequest {
  review_status: 'reviewed';
  review_decision: ResultDecision;
  review_note?: string;
  reviewer_name: string;
}

export interface ReviewResultResponse {
  result: DocumentResultItem;
}

export interface ResultBuckets {
  included: DocumentResultItem[];
  uncertain: DocumentResultItem[];
  excluded: DocumentResultItem[];
}

export interface TaskResults {
  task_id: string;
  buckets: ResultBuckets;
}

export interface StreamEvent {
  event_id: string;
  type: string;
  task_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface QmdCollectionStatus {
  name: string;
  exists: boolean;
  document_count: number;
  files: number;
}

export interface QmdStatus {
  available: boolean;
  error?: string;
  error_type?: string;
  backend?: string;
  url?: string;
  collections: QmdCollectionStatus[];
  configured_collections?: QmdCollectionStatus[];
  upstream_status?: unknown;
}

export interface RuntimeStatus {
  env_file: string;
  llm: {
    base_url: string;
    model: string;
    has_api_key: boolean;
    api_key_length: number;
  };
  qmd: {
    backend: string;
    url: string;
    collections: string[];
  };
  redis: {
    url: string;
  };
  worker: {
    mode: string;
    configured_mode?: string;
  };
}
