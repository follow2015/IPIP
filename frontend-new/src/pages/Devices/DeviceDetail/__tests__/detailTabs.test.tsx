import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DeviceDetail from '@/pages/Devices/DeviceDetail';
import { DeviceType } from '@/types/enums';

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const deviceById: Record<number, Record<string, unknown>> = {};
vi.mock('@/services/device', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    useDeviceSuspenseDetail: (id: number) => ({ data: deviceById[id], refetch: vi.fn() })
  };
});
vi.mock('@/services/switch', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    useSwitchWithPorts: () => ({ data: { switch: { has_ssh: true } } }),
    useSyncSwitchInfo: () => ({ mutateAsync: vi.fn(), isPending: false })
  };
});
vi.mock('@/hooks/useDeviceEvents', () => ({ useDeviceEvents: () => undefined }));
vi.mock('@/hooks/useMessage', () => ({
  useMessage: () => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() })
}));

const wrap = (ui: ReactNode) => (
  <QueryClientProvider client={qc}>
    <MemoryRouter initialEntries={['/devices/1']}>
      <Routes>
        <Route path="/devices/:id" element={ui} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>
);

describe('DeviceDetail tabs (config-driven, 真实渲染)', () => {
  it('network 设备渲染 ports/vlans/lag 且不抛错（验证 hasSsh 已接入）', async () => {
    deviceById[1] = {
      id: 1,
      device_name: 'SW-1',
      device_type: DeviceType.NETWORK,
      status: 1,
      is_chassis: false,
      switch_credential: { has_ssh: true }
    };
    render(wrap(<DeviceDetail />));
    await waitFor(() => expect(screen.getByText('端口')).toBeTruthy());
    expect(screen.getByText('VLAN')).toBeTruthy();
    expect(screen.getByText('链路聚合')).toBeTruthy();
  });

  it('chassis(server) 设备渲染 子节点 tab', async () => {
    deviceById[1] = {
      id: 1,
      device_name: 'CHS-1',
      device_type: DeviceType.SERVER,
      status: 1,
      is_chassis: true,
      total_nodes: 4,
      node_rows: 2,
      node_cols: 2
    };
    render(wrap(<DeviceDetail />));
    await waitFor(() => expect(screen.getByText('子节点')).toBeTruthy());
  });

  it('非 chassis 的 server 不渲染 子节点 tab', async () => {
    deviceById[1] = {
      id: 1,
      device_name: 'SRV-1',
      device_type: DeviceType.SERVER,
      status: 1,
      is_chassis: false
    };
    render(wrap(<DeviceDetail />));
    await waitFor(() => expect(screen.getByText('基本信息')).toBeTruthy());
    expect(screen.queryByText('子节点')).toBeNull();
  });

  it('other 设备含 网卡 tab 且不含 端口（对齐现状 SERVER||OTHER）', async () => {
    deviceById[1] = {
      id: 1,
      device_name: 'PDU-1',
      device_type: DeviceType.OTHER,
      status: 1,
      is_chassis: false
    };
    render(wrap(<DeviceDetail />));
    await waitFor(() => expect(screen.getByText('基本信息')).toBeTruthy());
    expect(screen.getByText('网卡')).toBeTruthy();
    expect(screen.queryByText('端口')).toBeNull();
  });
});
