import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UploadPage } from '../src/pages/UploadPage';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

const qmdStatus = {
  available: true,
  backend: 'qmd',
  url: 'http://qmd.local',
  collections: [{ name: 'contracts_prod', exists: true, document_count: 128, files: 128 }],
  configured_collections: [
    { name: 'contracts_prod', exists: true, document_count: 128, files: 128 },
    { name: 'contracts_archive', exists: false, document_count: 0, files: 0 }
  ]
};

const runtimeStatus = {
  env_file: '.env',
  llm: {
    base_url: 'https://llm.example.com/v1',
    model: 'qwen-plus',
    has_api_key: true,
    api_key_length: 32
  },
  qmd: {
    backend: 'qmd',
    url: 'http://qmd.local',
    collections: ['contracts_prod', 'contracts_archive']
  },
  redis: {
    url: 'redis://localhost:6379/0'
  },
  worker: {
    mode: 'inline',
    configured_mode: 'inline'
  }
};

describe('UploadPage', () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders the qmd screening workspace, health summary, and history link', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(jsonResponse(qmdStatus)).mockResolvedValueOnce(jsonResponse(runtimeStatus)));
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );
    expect(screen.getByText('合同筛选审查台')).toBeInTheDocument();
    expect(await screen.findByText('当前合同集合')).toBeInTheDocument();
    expect(screen.getByText('contracts_prod')).toBeInTheDocument();
    expect(screen.getByText('128 文档 · 可用')).toBeInTheDocument();
    expect(screen.getByText('qwen-plus')).toBeInTheDocument();
    expect(screen.getByText('已配置')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '查看任务历史' })).toHaveAttribute('href', '/tasks');
    expect(screen.queryByText('合同库')).not.toBeInTheDocument();
    expect(screen.queryByText('导入合同')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('合同文件')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Token')).not.toBeInTheDocument();
    expect(screen.getByText('开始筛选')).toBeDisabled();
  });

  it('starts screening by submitting only the query JSON', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(qmdStatus))
      .mockResolvedValueOnce(jsonResponse(runtimeStatus))
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1' }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText('筛选条件'), '合同总价');
    await user.click(screen.getByRole('button', { name: '开始筛选' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: '合同总价' })
      });
    });
  });
});
