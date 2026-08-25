import { describe, it, expect, vi, beforeEach } from 'vitest';


class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 1;
  url: string;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  close() {}
  emit(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}
vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);

vi.mock('@/stores/auth', () => ({
  useAuthStore: { getState: () => ({ token: 'test-token' }) }
}));

import { getDeviceBus, releaseDeviceBus } from './DeviceEventBus';
import type { DeviceChangeEvent } from './DeviceEventBus';

function makePortSync(deviceId: number, affectedPorts: string[]): DeviceChangeEvent {
  return {
    event_id: `e-${deviceId}`,
    device_id: deviceId,
    op_type: 'port_sync',
    seq: 1,
    ts: Date.now(),
    affected_ports: affectedPorts,
    affected_vlans: [],
    affected_lags: [],
    affected_connections: [],
    success: true
  };
}

describe('DeviceEventBus.dispatch — connections 通道派发（端口同步回归）', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
  });

  it('port_sync 带 affected_ports、affected_connections 为空 → 仍派发到 connections 通道', () => {
    const deviceId = 7;
    const bus = getDeviceBus(deviceId);
    const connHandler = vi.fn();
    const unsub = bus.on('connections', connHandler);

    const es = MockEventSource.instances[0];
    expect(es).toBeDefined();

    es.emit(makePortSync(deviceId, ['GE1/0/1', 'GE1/0/2']));

    expect(connHandler).toHaveBeenCalledTimes(1);
    const evt = connHandler.mock.calls[0][0] as DeviceChangeEvent;
    expect(evt.op_type).toBe('port_sync');
    expect(evt.affected_ports).toEqual(['GE1/0/1', 'GE1/0/2']);

    unsub();
    releaseDeviceBus(deviceId);
  });

  it('回归护栏：端口变化同时影响 connections 与 ports 两通道，缺一不可漏派', () => {
    const deviceId = 8;
    const bus = getDeviceBus(deviceId);
    const connHandler = vi.fn();
    const portsHandler = vi.fn();
    const unsubConn = bus.on('connections', connHandler);
    const unsubPorts = bus.on('ports', portsHandler);

    const es = MockEventSource.instances[0];
    es.emit(makePortSync(deviceId, ['GE1/0/1']));

    expect(connHandler).toHaveBeenCalledTimes(1);
    expect(portsHandler).toHaveBeenCalledTimes(1);

    unsubConn();
    unsubPorts();
    releaseDeviceBus(deviceId);
  });

  it('核心回归：port_sync 且 affected_ports 为空（后端 sync_members / on_commit 真实行为）→ 仍派发 connections 与 ports 通道', () => {
    const deviceId = 9;
    const bus = getDeviceBus(deviceId);
    const connHandler = vi.fn();
    const portsHandler = vi.fn();
    const unsubConn = bus.on('connections', connHandler);
    const unsubPorts = bus.on('ports', portsHandler);

    const es = MockEventSource.instances[0];
    es.emit(makePortSync(deviceId, [])); // 空 affected_ports

    expect(connHandler).toHaveBeenCalledTimes(1);
    expect(portsHandler).toHaveBeenCalledTimes(1);
    const evt = connHandler.mock.calls[0][0] as DeviceChangeEvent;
    expect(evt.op_type).toBe('port_sync');

    unsubConn();
    unsubPorts();
    releaseDeviceBus(deviceId);
  });

  it('核心回归：scan_complete 且 affected_ports 为空（sync_ports 端点真实行为）→ 派发 connections 通道', () => {
    const deviceId = 10;
    const bus = getDeviceBus(deviceId);
    const connHandler = vi.fn();
    const unsub = bus.on('connections', connHandler);

    const es = MockEventSource.instances[0];
    es.emit({
      event_id: 'e10',
      device_id: deviceId,
      op_type: 'scan_complete',
      seq: 1,
      ts: Date.now(),
      affected_ports: [],
      affected_vlans: [],
      affected_lags: [],
      affected_connections: [],
      success: true
    });

    expect(connHandler).toHaveBeenCalledTimes(1);

    unsub();
    releaseDeviceBus(deviceId);
  });
});
