import { afterEach, describe, expect, it, vi } from 'vitest';
import { getConditionVerdicts, getEvidenceLedger, getQmdEvidenceContext, getQmdPreview } from '../src/lib/api';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('phase 3 api client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('loads condition verdicts and evidence ledger', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }))
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await getConditionVerdicts('task-1');
    await getEvidenceLedger('task-1');

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/condition-verdicts');
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/evidence-ledger');
  });

  it('encodes qmd task and document parameters for preview and context', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/a.md', toc: [], can_open: false, can_download: false }))
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/a.md', text: '上下文', source_tool: 'doc_read' }));
    vi.stubGlobal('fetch', fetchMock);

    await getQmdPreview('task-1', 'qmd://company_docs/a.md');
    await getQmdEvidenceContext('task-1', { document_uri: 'qmd://company_docs/a.md', condition_id: 'amount', page: 3 });

    expect(String(fetchMock.mock.calls[0][0])).toContain('task_id=task-1');
    expect(String(fetchMock.mock.calls[0][0])).toContain('document_uri=qmd%3A%2F%2Fcompany_docs%2Fa.md');
    expect(String(fetchMock.mock.calls[1][0])).toContain('task_id=task-1');
    expect(String(fetchMock.mock.calls[1][0])).toContain('condition_id=amount');
    expect(String(fetchMock.mock.calls[1][0])).toContain('page=3');
  });
});
