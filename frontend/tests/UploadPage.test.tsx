import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UploadPage } from '../src/pages/UploadPage';

describe('UploadPage', () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders the qmd screening workspace without upload or library controls', () => {
    vi.stubGlobal('fetch', vi.fn());
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );
    expect(screen.getByText('合同筛选审查台')).toBeInTheDocument();
    expect(screen.queryByText('合同库')).not.toBeInTheDocument();
    expect(screen.queryByText('导入合同')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('合同文件')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Token')).not.toBeInTheDocument();
    expect(screen.getByText('开始筛选')).toBeDisabled();
  });

  it('starts screening by submitting only the query JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ task_id: 'task-1' }), { status: 200 }));
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
