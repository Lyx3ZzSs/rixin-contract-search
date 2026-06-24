import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
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
        result_id: 'result-1',
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
        review_status: 'unreviewed',
        review_decision: null,
        review_note: null,
        reviewer_name: null,
        reviewed_at: null,
        decision_basis: { general_match: 'satisfied' },
        uncertain_reasons: [],
        evidence_support_rate: 1,
        verification_status: 'deep_read_verified',
        created_at: '2026-06-22T00:00:01Z',
        updated_at: '2026-06-22T00:00:01Z'
      }
    ],
    uncertain: [],
    excluded: []
  }
};

const taskTwoRunningSummary = {
  task_id: 'task-2',
  title: '第二个任务',
  raw_query: '第二个任务',
  status: 'retrieving',
  progress_percent: 20,
  current_stage: 'retrieving',
  error_code: null,
  error_message: null,
  created_at: '2026-06-22T00:10:00Z',
  updated_at: '2026-06-22T00:10:00Z',
  completed_at: null,
  counts: { documents: 0, included: 0, uncertain: 0, excluded: 0 }
};

const failedLlmSummary = {
  ...runningSummary,
  status: 'failed',
  progress_percent: 100,
  current_stage: 'failed',
  error_code: 'agent_llm_not_configured',
  error_message: 'LLM not configured'
};

function RouteSwitchHarness() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate('/tasks/task-2')}>
        切换到任务 2
      </button>
      <TaskProgressPage />
    </>
  );
}

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

    expect(await screen.findByRole('heading', { name: '采购合同', level: 3 })).toBeInTheDocument();
    expect(await screen.findByText('条件矩阵')).toBeInTheDocument();
    expect(screen.getByText('证据账本')).toBeInTheDocument();
    expect(screen.getByText('company_docs · contracts/purchase.md')).toBeInTheDocument();
    expect(screen.getByTestId('event-progress')).toBeInTheDocument();
    expect(screen.getByText('理解筛选条件')).toBeInTheDocument();
    expect(screen.getByText('实时活动')).toBeInTheDocument();
    expect(screen.getByText('已分析 0 份文档')).toBeInTheDocument();
    expect(screen.getByText('入选 · keyword_evidence_matched')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '任务历史' })).toHaveAttribute('href', '/tasks');
    expect(screen.getByRole('link', { name: '导出 CSV' })).toHaveAttribute('href', '/api/screening-tasks/task-1/export.csv');
    expect(screen.getByRole('link', { name: '导出 XLSX' })).toHaveAttribute('href', '/api/screening-tasks/task-1/export.xlsx');
    expect(screen.getByRole('link', { name: '导出 JSON' })).toHaveAttribute('href', '/api/screening-tasks/task-1/export.json');
    expect(screen.getByRole('button', { name: '保存复核' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/events', {
      signal: expect.any(AbortSignal)
    });
  });

  it('saves a manual review and updates the selected result', async () => {
    const user = userEvent.setup();
    const reviewedResult = {
      ...results.buckets.included[0],
      review_status: 'reviewed',
      review_decision: 'excluded',
      review_note: '附件金额不匹配',
      reviewer_name: '王五',
      reviewed_at: '2026-06-22T00:05:00Z'
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(completedSummary))
      .mockResolvedValueOnce(streamResponse([]))
      .mockResolvedValueOnce(jsonResponse(completedSummary))
      .mockResolvedValueOnce(jsonResponse(results))
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }))
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }))
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/contracts/purchase.md', toc: [], can_open: false, can_download: false }))
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/contracts/purchase.md', text: '合同总价为人民币120万元', source_tool: 'doc_read' }))
      .mockResolvedValueOnce(jsonResponse({ result: reviewedResult }));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={['/tasks/task-1']}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskProgressPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { name: '采购合同', level: 3 })).toBeInTheDocument();

    await user.clear(screen.getByLabelText('复核人'));
    await user.type(screen.getByLabelText('复核人'), '  王五  ');
    await user.selectOptions(screen.getByLabelText('人工结论'), 'excluded');
    await user.type(screen.getByLabelText('复核备注'), '附件金额不匹配');
    await user.click(screen.getByRole('button', { name: '保存复核' }));

    await waitFor(() => expect(screen.getByText('已复核：王五')).toBeInTheDocument());
    expect(localStorage.getItem('contract-agent-reviewer-name')).toBe('王五');
    expect(screen.getByText('人工结论：不符合')).toBeInTheDocument();
    expect(screen.getAllByText('附件金额不匹配').length).toBeGreaterThanOrEqual(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/results/result-1/review', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        review_status: 'reviewed',
        review_decision: 'excluded',
        review_note: '附件金额不匹配',
        reviewer_name: '王五'
      })
    });
  });

  it('clears stale task detail state while switching task routes', async () => {
    const user = userEvent.setup();
    let resolveTaskTwoSummary!: (response: Response) => void;
    const taskTwoSummaryPromise = new Promise<Response>((resolve) => {
      resolveTaskTwoSummary = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/screening-tasks/task-1') return Promise.resolve(jsonResponse(completedSummary));
      if (url === '/api/screening-tasks/task-1/results') return Promise.resolve(jsonResponse(results));
      if (url === '/api/screening-tasks/task-1/events') return Promise.resolve(streamResponse([]));
      if (url === '/api/screening-tasks/task-2') return taskTwoSummaryPromise;
      if (url === '/api/screening-tasks/task-2/events') return Promise.resolve(streamResponse([]));
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={['/tasks/task-1']}>
        <Routes>
          <Route path="/tasks/:taskId" element={<RouteSwitchHarness />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { name: '采购合同', level: 3 })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '导出 CSV' })).toHaveAttribute('href', '/api/screening-tasks/task-1/export.csv');
    expect(screen.getByRole('button', { name: '保存复核' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '切换到任务 2' }));

    await waitFor(() => expect(screen.queryByText('采购合同')).not.toBeInTheDocument());
    expect(screen.queryByRole('link', { name: '导出 CSV' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存复核' })).not.toBeInTheDocument();
    expect(screen.getByText('Agent 正在检索合同库')).toBeInTheDocument();

    resolveTaskTwoSummary(jsonResponse(taskTwoRunningSummary));
    await waitFor(() => expect(screen.getAllByText('第二个任务').length).toBeGreaterThanOrEqual(1));
    expect(fetchMock).not.toHaveBeenCalledWith('/api/screening-tasks/task-2/results/result-1/review', expect.anything());
  });

  it('shows actionable guidance for mapped failed task summaries', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(failedLlmSummary))
      .mockResolvedValueOnce(streamResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={['/tasks/task-1']}>
        <Routes>
          <Route path="/tasks/:taskId" element={<TaskProgressPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText(/LLM 配置不可用/)).toBeInTheDocument());
    expect(screen.getByText(/AGENT_LLM_API_KEY/)).toBeInTheDocument();
    expect(screen.getByText(/AGENT_LLM_BASE_URL/)).toBeInTheDocument();
    expect(screen.getByText(/AGENT_LLM_MODEL/)).toBeInTheDocument();
    expect(screen.queryByText('LLM not configured')).not.toBeInTheDocument();
  });
});
