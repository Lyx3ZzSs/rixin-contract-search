export type TaskStatus = 'uploaded' | 'parsing' | 'parsed' | 'indexing' | 'indexed' | 'retrieving' | 'classifying' | 'completed' | 'failed';

export type ResultDecision = 'included' | 'uncertain' | 'excluded';

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

export interface EvidenceItem {
  page: number | null;
  text: string;
  source: 'qmd';
  score: number | null;
  condition_id: string;
  artifact_ref: string | null;
}

export interface DocumentResultItem {
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
  created_at: string;
  updated_at: string;
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
