import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { IPStatusCode } from '@/types/enums';

const hoisted = vi.hoisted(() => ({ ipItems: [] as Record<string, unknown>[] }));

vi.mock('@/services/ip', () => ({
  useIPList: () => ({
    data: { items: hoisted.ipItems, total: hoisted.ipItems.length },
    isLoading: false,
    refetch: vi.fn()
  }),
  useIPDetail: () => ({ data: undefined, isLoading: false, isFetching: false }),
  useDetectIPStatus: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useUpdateIPCustomer: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useUpdateIPNotes: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  usePingIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useScanIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useBanIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({ data: {} }) }),
  useUnbanIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({ data: {} }) }),
  useBatchBanIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useBatchUnbanIP: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useIPStatistics: () => ({ data: undefined })
}));

vi.mock('@/services/network', () => ({
  useScanNetwork: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false })
}));

vi.mock('@/services/customer', () => ({
  useAllocatableCustomerOptions: () => ({ data: [] })
}));

vi.mock('@/services/room', () => ({
  useRoomOptions: () => ({ data: [] })
}));

vi.mock('@/hooks/useGlobalEvents', () => ({
  useGlobalEventListener: vi.fn()
}));

import IP from './index';

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

describe('IP 管理页 冒烟测试（重构回归护栏）', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    hoisted.ipItems = [];
  });

  it('渲染 IP 列表与工具栏不抛错', () => {
    render(<IP />, { wrapper: makeWrapper() });
    expect(screen.getAllByText('IP地址').length).toBeGreaterThan(0);
    expect(screen.getByText('导出CSV')).toBeInTheDocument();
    expect(screen.getByText('批量封禁')).toBeInTheDocument();
    expect(screen.getByText('统计')).toBeInTheDocument();
    expect(screen.getByText('扫描网段')).toBeInTheDocument();
    expect(screen.queryByText(/已选择/)).toBeNull();
  });

  it('点击"统计"打开 IP 状态统计弹窗', async () => {
    render(<IP />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByText('统计'));
    await waitFor(() => expect(screen.getByText('IP 状态统计')).toBeInTheDocument());
  });

  it('勾选行后浮出 BatchActionBar（批量封禁/解封），取消选择后收起', async () => {
    const user = userEvent.setup();
    hoisted.ipItems = [
      { ip_address: '10.0.0.1', status: IPStatusCode.UNUSED, switch_name: 'sw1', port: 'GE0/0/1' },
      { ip_address: '10.0.0.2', status: IPStatusCode.UNUSED, switch_name: 'sw2', port: 'GE0/0/2' }
    ];
    render(<IP />, { wrapper: makeWrapper() });

    expect(screen.queryByText(/已选择/)).toBeNull();

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    await user.click(checkboxes[1]);

    await waitFor(() => {
      const bar = screen.getByText(/已选择/);
      expect(bar.textContent).toContain('1');
      expect(bar.textContent).toContain('个IP');
    });
    expect(screen.getAllByText('批量封禁').length).toBeGreaterThan(0);
    expect(screen.getByText('批量解封')).toBeInTheDocument();

    await user.click(screen.getByText('取消选择'));
    await waitFor(() => expect(screen.queryByText(/已选择/)).toBeNull());
  });
});
