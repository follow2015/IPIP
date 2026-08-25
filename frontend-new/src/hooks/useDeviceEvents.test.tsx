import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDeviceEvents } from './useDeviceEvents';
import type { DeviceChangeEvent } from '@/services/DeviceEventBus';


const hoisted = vi.hoisted(() => ({
  handlers: {} as Record<string, ((e: DeviceChangeEvent) => void) | undefined>
}));

vi.mock('@/services/DeviceEventBus', () => ({
  getDeviceBus: () => ({
    on: (resource: string, handler: (e: DeviceChangeEvent) => void) => {
      hoisted.handlers[resource] = handler;
      return () => {
        hoisted.handlers[resource] = undefined;
      };
    }
  }),
  releaseDeviceBus: () => {}
}));

function makePortSync(deviceId: number, ports: string[]): DeviceChangeEvent {
  return {
    event_id: `e-${deviceId}`,
    device_id: deviceId,
    op_type: 'port_sync',
    seq: 1,
    ts: Date.now(),
    affected_ports: ports,
    affected_vlans: [],
    affected_lags: [],
    affected_connections: [],
    success: true
  };
}

describe('useDeviceEvents — connections 通道失效连接缓存（端口同步回归）', () => {
  let qc: QueryClient;

  beforeEach(() => {
    hoisted.handlers = {};
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
    });
  });

  function renderHook(deviceId: number) {
    function Harness() {
      useDeviceEvents(deviceId, 'connections');
      return null;
    }
    return render(<Harness />, {
      wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    });
  }

  it('端口同步事件(port_sync, 空 affected_ports) → 失效 connections / port-links / connections-switch 缓存', () => {
    renderHook(1);
    const invalidate = vi.spyOn(qc, 'invalidateQueries');

    act(() => {
      hoisted.handlers['connections']?.(makePortSync(1, []));
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'port-links'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections', 'switch'] });
  });

  it('端口同步事件(scan_complete, 空 affected_ports) → 同样失效连接缓存', () => {
    renderHook(1);
    const invalidate = vi.spyOn(qc, 'invalidateQueries');

    act(() => {
      hoisted.handlers['connections']?.({
        event_id: 'e1',
        device_id: 1,
        op_type: 'scan_complete',
        seq: 1,
        ts: Date.now(),
        affected_ports: [],
        affected_vlans: [],
        affected_lags: [],
        affected_connections: [],
        success: true
      });
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'port-links'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['devices', 1, 'connections', 'switch'] });
  });
});
