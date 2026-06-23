import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TaskProgressPage } from '../src/pages/TaskProgressPage';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function streamResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      }
    }),
    { status: 200 }
  );
}

const runningSummary = {
  task_id: 'task-1',
  title: '合同总价',
  raw_query: '合同总价',
  status: 'retrieving',
  progress_percent: 72,
  current_stage: 'retrieving',
  error_code: null,
  error_message: null,
  created_at: '2026-06-22T00:00:00Z',
  updated_at: '2026-06-22T00:00:00Z',
  completed_at: null,
  counts: { documents: 1, included: 0, uncertain: 0, excluded: 0 }
};

const completedSummary = {
  ...runningSummary,
  status: 'completed',
  progress_percent: 100,
  current_stage: 'completed',
  completed_at: '2026-06-22T00:00:01Z',
  counts: { documents: 1, included: 1, uncertain: 0, excluded: 0 }
};

const results = {
  task_id: 'task-1',
  buckets: {
    included: [
      {
        document_uri: 'qmd://company_docs/contracts/purchase.md',
        document_path: 'contracts/purchase.md',
        document_title: '采购合同',
        collection: 'company_docs',
        decision: 'included',
        reason: 'keyword_evidence_matched',
        matched_conditions: ['general_match'],
        missing_conditions: [],
        evidence: [
          {
            page: 1,
            text: '合同总价为人民币120万元',
            source: 'qmd',
            score: 0.88,
            condition_id: 'general_match',
            artifact_ref: 'qmd://company_docs/contracts/purchase.md'
          }
        ],
        confidence: 0.65,
        created_at: '2026-06-22T00:00:01Z',
        updated_at: '2026-06-22T00:00:01Z'
      }
    ],
    uncertain: [],
    excluded: []
  }
};

describe('TaskProgressPage', () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('loads final results after the SSE stream completes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(runningSummary))
      .mockResolvedValueOnce(
        streamResponse([
          ': keepalive\n\n',
          'id: task-1:1\nevent: progress\ndata: {"event_id":"task-1:1","type":"progress","task_id":"task-1","timestamp":"2026-06-22T00:00:00Z","payload":{"progress_percent":90}}\n\n',
          'id: task-1:2\nevent: task_completed\ndata: {"event_id":"task-1:2","type":"task_completed","task_id":"task-1","timestamp":"2026-06-22T00:00:01Z","payload":{"included_count":1}}\n\n'
        ])
      )
      .mockResolvedValueOnce(jsonResponse(completedSummary))
      .mockResolvedValueOnce(jsonResponse(results));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={['/tasks/task-1']}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskProgressPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('采购合同')).toBeInTheDocument());
    expect(screen.getByText('company_docs · contracts/purchase.md')).toBeInTheDocument();
    expect(screen.getByTestId('event-progress')).toBeInTheDocument();
    expect(screen.getByText('入选 · keyword_evidence_matched')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/events', {
      signal: expect.any(AbortSignal)
    });
  });
});
