import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';

const hoisted = vi.hoisted(() => ({ devices: [] as Record<string, unknown>[] }));

vi.mock('@/services/device', () => ({
  useDeletedDeviceList: () => ({
    data: {
      devices: hoisted.devices,
      total: hoisted.devices.length,
      page: 1,
      page_size: 10,
      total_pages: 1
    },
    isLoading: false,
    refetch: vi.fn()
  }),
  useRestoreDevice: () => ({ mutate: vi.fn(), isPending: false }),
  useBatchRestoreDevices: () => ({ mutate: vi.fn(), isPending: false }),
  usePermanentDeleteDevice: () => ({ mutate: vi.fn(), isPending: false }),
  useBatchPermanentDeleteDevices: () => ({ mutate: vi.fn(), isPending: false })
}));

vi.mock('@/services/room', () => ({
  useRoomOptions: () => ({ data: [] })
}));

vi.mock('@/services/cabinet', () => ({
  useCabinetOptions: () => ({ data: [], isLoading: false })
}));

import DeviceRecycleBin from './index';

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

describe('设备回收站 冒烟测试（BatchActionBar 接入回归护栏）', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    hoisted.devices = [];
  });

  it('渲染列表不抛错，无选中时批量操作栏不渲染', () => {
    hoisted.devices = [
      { id: 1, device_name: 'dev-1', device_type: 'server', management_ip: '10.0.0.1' },
      { id: 2, device_name: 'dev-2', device_type: 'server', management_ip: '10.0.0.2' }
    ];
    render(<DeviceRecycleBin />, { wrapper: makeWrapper() });
    expect(screen.getAllByText('设备名称').length).toBeGreaterThan(0);
    expect(screen.queryByText('批量恢复')).toBeNull();
  });

  it('勾选行后浮出批量操作栏（批量恢复/批量永久删除），取消勾选后收起', async () => {
    const user = userEvent.setup();
    hoisted.devices = [
      { id: 1, device_name: 'dev-1', device_type: 'server', management_ip: '10.0.0.1' },
      { id: 2, device_name: 'dev-2', device_type: 'server', management_ip: '10.0.0.2' }
    ];
    render(<DeviceRecycleBin />, { wrapper: makeWrapper() });

    expect(screen.queryByText('批量恢复')).toBeNull();

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    await user.click(checkboxes[1]);

    await waitFor(() => expect(screen.getByText('批量恢复')).toBeInTheDocument());
    expect(screen.getByText(/已选/)).toBeInTheDocument();
    expect(screen.getByText('批量永久删除')).toBeInTheDocument();

    await user.click(checkboxes[1]);
    await waitFor(() => expect(screen.queryByText('批量恢复')).toBeNull());
  });

  it('勾选后点「批量恢复」打开批量恢复弹窗', async () => {
    const user = userEvent.setup();
    hoisted.devices = [
      { id: 1, device_name: 'dev-1', device_type: 'server', management_ip: '10.0.0.1' },
      { id: 2, device_name: 'dev-2', device_type: 'server', management_ip: '10.0.0.2' }
    ];
    render(<DeviceRecycleBin />, { wrapper: makeWrapper() });

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    await user.click(checkboxes[1]);
    await waitFor(() => expect(screen.getByText('批量恢复')).toBeInTheDocument());

    await user.click(screen.getByText('批量恢复'));
    await waitFor(() => expect(screen.getByText(/将恢复选中/)).toBeInTheDocument());
  });
});
