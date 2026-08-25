import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import type { SwitchPort, SwitchPortDetail } from '@/types/models';

const mockDetail: SwitchPortDetail = {
  port: 'GE0/0/1',
  status: 'up',
  vlan: 1,
  ip_list: [
    {
      id: 1,
      switch_id: 1,
      port: 'GE0/0/1',
      ip_address: '10.0.0.1',
      subnet_mask: '255.255.255.0',
      prefix: 24,
      is_primary: true,
      updated_at: '2026-01-01T00:00:00Z'
    }
  ],
  updated_at: '2026-01-01T00:00:00Z',
  mac_address: null,
  port_mac: null
};

vi.mock('@/services/switch', () => ({
  useUpdatePortCustomer: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useSwitchPortDetail: () => ({ data: mockDetail, isLoading: false, isFetching: false }),
  useFetchPortConfig: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ data: {} }),
    isPending: false
  }),
  useRefreshPortConfig: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ data: {} }),
    isPending: false
  })
}));

vi.mock('@/services/customer', () => ({
  useAllocatableCustomerOptions: () => ({ data: [] })
}));

import PortActions from './PortActions';

const fakePort: SwitchPort = {
  port_name: 'GE0/0/1',
  link_status: 'up',
  customer_id: null,
  notes: '',
  vlan: 1,
  mac_address: 'aa:bb:cc:dd:ee:ff',
  speed: 1000,
  max_speed: 10000
} as unknown as SwitchPort;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <AntApp>{children}</AntApp>
    </QueryClientProvider>
  );
}

describe('PortActions 冒烟测试（重构回归护栏）', () => {
  beforeEach(() => vi.clearAllMocks());

  it('渲染按钮组不抛错', () => {
    render(<PortActions switchId={1} port={fakePort} submitAction={vi.fn()} />, {
      wrapper: makeWrapper()
    });
    expect(screen.getByText('详情')).toBeInTheDocument();
    expect(screen.getByText('分配')).toBeInTheDocument();
  });

  it('点击"详情"打开端口详情弹窗', async () => {
    render(<PortActions switchId={1} port={fakePort} submitAction={vi.fn()} />, {
      wrapper: makeWrapper()
    });
    fireEvent.click(screen.getByText('详情'));
    await waitFor(() => expect(screen.getByText(/端口详情 — GE0\/0\/1/)).toBeInTheDocument());
  });

  it('NULL0 端口不渲染任何操作按钮', () => {
    const nullPort = { ...fakePort, port_name: 'NULL0' } as unknown as SwitchPort;
    const { container } = render(
      <PortActions switchId={1} port={nullPort} submitAction={vi.fn()} />,
      { wrapper: makeWrapper() }
    );
    expect(container.querySelector('button')).toBeNull();
  });
});
