const REVIEWER_STORAGE_KEY = 'contract-agent-reviewer-name';

export function getReviewerName(): string {
  return localStorage.getItem(REVIEWER_STORAGE_KEY) || '';
}

export function setReviewerName(name: string): void {
  const trimmed = name.trim();
  if (trimmed) localStorage.setItem(REVIEWER_STORAGE_KEY, trimmed);
}
