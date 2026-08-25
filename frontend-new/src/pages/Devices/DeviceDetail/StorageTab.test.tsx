import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';

const hoisted = vi.hoisted(() => ({
  storage: [] as Record<string, unknown>[],
  batchDeleteStub: vi
    .fn()
    .mockResolvedValue({ success: true, data: { deleted: [1], not_found: [] }, message: 'ok' })
}));

vi.mock('@/services/device-storage', () => ({
  useDeviceStorageDetail: () => ({ data: hoisted.storage, isLoading: false }),
  useCreateStorage: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useUpdateStorage: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useDeleteStorage: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useBatchDeleteStorage: () => ({ mutateAsync: hoisted.batchDeleteStub })
}));

import StorageTab from './StorageTab';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AntApp>{children}</AntApp>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StorageTab 冒烟测试（BatchActionBar 接入回归护栏）', () => {
  it('渲染工具栏不抛错，无选中时浮条不出现', () => {
    render(<StorageTab deviceId={1} />, { wrapper: makeWrapper() });
    expect(screen.getByText('模板配置')).toBeInTheDocument();
    expect(screen.queryByText(/已选择/)).toBeNull();
  });

  it('勾选存储后浮条出现，确认批量删除走后端批量接口', async () => {
    const user = userEvent.setup();
    hoisted.storage = [
      { id: 1, storage_type: 'SSD', capacity: '2TB', status: 'normal' },
      { id: 2, storage_type: 'NVMe', capacity: '1TB', status: 'normal' }
    ];
    render(<StorageTab deviceId={1} />, { wrapper: makeWrapper() });

    expect(screen.queryByText(/已选择/)).toBeNull();

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    await user.click(checkboxes[1]);

    await waitFor(() => {
      const bar = screen.getByText(/已选择/);
      expect(bar.textContent).toContain('1');
      expect(bar.textContent).toContain('条存储');
    });

    await user.click(screen.getByText('批量删除'));
    const okBtn = await screen.findByRole('button', { name: /确定|OK/i });
    await user.click(okBtn);

    await waitFor(() => expect(hoisted.batchDeleteStub).toHaveBeenCalledWith({ storage_ids: [1] }));
  });
});
