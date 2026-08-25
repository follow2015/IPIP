import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useD2NConnectionSync } from './useD2NConnectionSync';
import * as DeviceEventBusModule from '@/services/DeviceEventBus';

const busHandlers = new Map<number, (e: any) => void>();
const unsubSpies = new Map<number, ReturnType<typeof vi.fn>>();

vi.mock('@/services/DeviceEventBus', () => {
  const getDeviceBus = vi.fn((id: number) => ({
    on: vi.fn((_resource: string, handler: (e: any) => void) => {
      busHandlers.set(id, handler);
      const unsub = vi.fn();
      unsubSpies.set(id, unsub);
      return unsub;
    })
  }));
  const releaseDeviceBus = vi.fn();
  return { getDeviceBus, releaseDeviceBus };
});

function makeEvent(op_type: string, affected_ports: string[] = []) {
  return {
    event_id: 'evt-1',
    device_id: 9,
    op_type,
    seq: 1,
    ts: 1,
    affected_ports,
    affected_vlans: [],
    affected_lags: [],
    affected_connections: []
  };
}

let qc: QueryClient;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  qc = new QueryClient();
  busHandlers.clear();
  unsubSpies.clear();
  vi.clearAllMocks();
});

describe('useD2NConnectionSync', () => {
  it('对端交换机 port_sync → 失效本机 D2N 连接缓存', () => {
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    renderHook(() => useD2NConnectionSync(1, [9]), { wrapper });

    const handler = busHandlers.get(9)!;
    expect(handler).toBeTypeOf('function');

    act(() => {
      handler(makeEvent('port_sync'));
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
  });

  it('对端交换机 scan_complete（空 affected_ports）→ 同样失效', () => {
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    renderHook(() => useD2NConnectionSync(1, [9]), { wrapper });
    act(() => {
      busHandlers.get(9)!(makeEvent('scan_complete'));
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
  });

  it('无关事件（vlan_sync）→ 不触发失效', () => {
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    renderHook(() => useD2NConnectionSync(1, [9]), { wrapper });
    act(() => {
      busHandlers.get(9)!(makeEvent('vlan_sync'));
    });
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('卸载时退订并释放对端交换机 bus（引用计数 -1）', () => {
    const { unmount } = renderHook(() => useD2NConnectionSync(1, [9]), { wrapper });
    expect(DeviceEventBusModule.getDeviceBus).toHaveBeenCalledWith(9);
    unmount();
    expect(unsubSpies.get(9)).toHaveBeenCalled();
    expect(DeviceEventBusModule.releaseDeviceBus).toHaveBeenCalledWith(9);
  });

  it('switchIds 为空时不订阅任何 bus', () => {
    renderHook(() => useD2NConnectionSync(1, []), { wrapper });
    expect(DeviceEventBusModule.getDeviceBus).not.toHaveBeenCalled();
  });
});
