import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp } from 'antd';

const hoisted = vi.hoisted(() => ({
  sshPorts: [] as Record<string, unknown>[],
  networkPorts: [] as Record<string, unknown>[],
  refetch: vi.fn(),
  syncStub: vi.fn().mockResolvedValue({}),
  sseCallback: null as null | ((event: Record<string, unknown>) => void)
}));

vi.mock('@/services/network-port', () => ({
  useNetworkPorts: () => ({
    data: hoisted.networkPorts,
    isLoading: false,
    refetch: hoisted.refetch
  }),
  useCreateNetworkPort: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useUpdateNetworkPort: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useDeleteNetworkPort: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useUpdatePortUsageStatus: () => ({ mutateAsync: vi.fn().mockResolvedValue({}) }),
  useBatchCreateNetworkPorts: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ data: { created_count: 1 } })
  }),
  useDevicePortSyncEnabled: () => ({
    data: { port_sync_enabled: null, global_enabled: true, effective_enabled: true }
  }),
  useSetDevicePortSyncEnabled: () => ({ mutate: vi.fn(), isPending: false })
}));
vi.mock('@/services/switch', () => ({
  useSwitchWithPorts: () => ({
    data: { ports: hoisted.sshPorts },
    isLoading: false,
    refetch: hoisted.refetch
  }),
  useSyncSwitchInfo: () => ({ mutateAsync: hoisted.syncStub, isPending: false }),
  useSyncSwitchPorts: () => ({ mutateAsync: hoisted.syncStub, isPending: false })
}));
vi.mock('@/services/device', () => ({
  useDeviceList: () => ({ data: { items: [] } })
}));
vi.mock('@/services/customer', () => ({
  useAllocatableCustomerOptions: () => ({ data: [] })
}));
vi.mock('@/services/monitor', () => ({
  useDeviceMonitorStatus: () => ({
    data: { configured_protocols: ['snmp'] }
  })
}));
vi.mock('@/hooks/useDeviceEvents', () => ({
  useDeviceEvents: (
    _deviceId: number,
    _type: string,
    cb: (event: Record<string, unknown>) => void
  ) => {
    hoisted.sseCallback = cb;
    return undefined;
  }
}));
vi.mock('@/hooks/usePortAction', () => ({
  usePortAction: () => ({ submitAction: vi.fn(), onEvent: vi.fn() })
}));
vi.mock('@/utils/confirm', () => ({
  confirm: (opts: { onOk?: () => void }) => {
    opts.onOk?.();
    return { destroy: vi.fn() };
  }
}));
vi.mock('@/components/SwitchPortPanel', () => ({
  default: ({ ports }: { ports: unknown[] }) => (
    <div data-testid="switch-port-panel">panel:{ports?.length ?? 0}</div>
  )
}));

import UnifiedPortTab from './UnifiedPortTab';

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

beforeEach(() => {
  hoisted.sshPorts = [];
  hoisted.networkPorts = [];
  vi.clearAllMocks();
});

describe('UnifiedPortTab 冒烟测试（拆分回归护栏）', () => {
  it('SSH 模式渲染：同步按钮 + 可视化面板 + 批量栏 + 表格', () => {
    hoisted.sshPorts = [
      {
        port_name: 'GE0/0/1',
        usage_status: 'free',
        link_status: 'up',
        customer_name: null,
        notes: null
      },
      {
        port_name: 'GE0/0/2',
        usage_status: 'occupied',
        link_status: 'down',
        customer_name: null,
        notes: null
      }
    ];
    render(
      <UnifiedPortTab
        deviceId={1}
        hasSsh
        renderPortActions={() => <span>PA</span>}
        renderBatchActions={() => <div data-testid="batch-port-actions">BatchPortActions</div>}
      />,
      { wrapper: makeWrapper() }
    );
    expect(screen.getByText('同步数据')).toBeInTheDocument();
    expect(screen.getByTestId('switch-port-panel')).toBeInTheDocument();
    expect(screen.getByTestId('batch-port-actions')).toBeInTheDocument();
    expect(screen.getByText('GE0/0/1')).toBeInTheDocument();
    expect(screen.getByText('GE0/0/2')).toBeInTheDocument();
    expect(screen.getByText('空闲: 1')).toBeInTheDocument();
  });

  it('非 SSH 模式渲染：新增端口按钮 + 批量栏 + 表格', () => {
    hoisted.networkPorts = [
      {
        id: 1,
        port_name: 'GE0/0/1',
        usage_status: 'free',
        customer_name: null,
        notes: null,
        port_info: null
      },
      {
        id: 2,
        port_name: 'GE0/0/2',
        usage_status: 'disabled',
        customer_name: null,
        notes: null,
        port_info: null
      }
    ];
    render(
      <UnifiedPortTab
        deviceId={1}
        hasSsh={false}
        renderPortActions={() => <span>PA</span>}
        renderBatchActions={() => <div data-testid="batch-port-actions">BatchPortActions</div>}
      />,
      { wrapper: makeWrapper() }
    );
    expect(screen.getByText('新增端口')).toBeInTheDocument();
    expect(screen.getByTestId('batch-port-actions')).toBeInTheDocument();
    expect(screen.getByText('GE0/0/1')).toBeInTheDocument();
    expect(screen.getByText('GE0/0/2')).toBeInTheDocument();
  });

  it('非 SSH 模式：点击新增端口打开弹窗，可切换单条模式', async () => {
    const user = userEvent.setup();
    hoisted.networkPorts = [
      {
        id: 1,
        port_name: 'GE0/0/1',
        usage_status: 'free',
        customer_name: null,
        notes: null,
        port_info: null
      }
    ];
    render(
      <UnifiedPortTab
        deviceId={1}
        hasSsh={false}
        renderPortActions={() => <span>PA</span>}
        renderBatchActions={() => <div data-testid="batch-port-actions">BatchPortActions</div>}
      />,
      { wrapper: makeWrapper() }
    );

    await user.click(screen.getByText('新增端口'));

    await waitFor(() => {
      expect(screen.getByText('端口类型')).toBeInTheDocument();
    });

    await user.click(screen.getByText('单条添加'));
    await waitFor(() => {
      expect(screen.getByText('端口名称')).toBeInTheDocument();
    });
  });

  it('SSH 模式：点击同步数据触发同步提交', async () => {
    const user = userEvent.setup();
    hoisted.sshPorts = [
      {
        port_name: 'GE0/0/1',
        usage_status: 'free',
        link_status: 'up',
        customer_name: null,
        notes: null
      }
    ];
    render(
      <UnifiedPortTab
        deviceId={1}
        hasSsh
        renderPortActions={() => <span>PA</span>}
        renderBatchActions={() => <div data-testid="batch-port-actions">BatchPortActions</div>}
      />,
      { wrapper: makeWrapper() }
    );
    await user.click(screen.getByText('同步数据'));
    await waitFor(() => expect(hoisted.syncStub).toHaveBeenCalledWith(1));
  });

  it('F13 SSE 端口事件 → 高亮端口，3s 后自动清除', async () => {
    hoisted.sshPorts = [
      {
        port_name: 'GE0/0/1',
        usage_status: 'free',
        link_status: 'up',
        customer_name: null,
        notes: null
      },
      {
        port_name: 'GE0/0/2',
        usage_status: 'occupied',
        link_status: 'down',
        customer_name: null,
        notes: null
      }
    ];
    render(
      <UnifiedPortTab
        deviceId={1}
        hasSsh
        renderPortActions={() => <span>PA</span>}
        renderBatchActions={() => <div data-testid="batch-port-actions">BatchPortActions</div>}
      />,
      { wrapper: makeWrapper() }
    );

    const rowOf = (name: string) => screen.getByText(name).closest('tr');
    expect(rowOf('GE0/0/1')).not.toHaveClass('ant-table-row-selected');

    vi.useFakeTimers();
    act(() => {
      hoisted.sseCallback?.({
        op_type: 'port_action_result',
        success: true,
        affected_ports: ['GE0/0/1']
      } as Record<string, unknown>);
    });

    expect(rowOf('GE0/0/1')).toHaveClass('ant-table-row-selected');
    expect(rowOf('GE0/0/2')).not.toHaveClass('ant-table-row-selected');

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(rowOf('GE0/0/1')).not.toHaveClass('ant-table-row-selected');

    vi.useRealTimers();
  });
});
