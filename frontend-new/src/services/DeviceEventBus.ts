/**
 * DeviceEventBus — 每台设备单例 SSE 连接 + 事件分发总线
 *
 * 核心职责：
 * - 每台设备（deviceId）维护一个 EventSource 连接
 * - 收到事件后按 affected_* 字段分发到对应资源类型的监听器
 * - 通过 _busRegistry 实现引用计数，多组件共享同一连接
 * - 断线自动重连（指数退避，最大 30s）
 * - SSE 连接携带 token 认证参数（EventSource 不支持自定义 Header）
 *
 * SSE 服务已从 Flask 迁移至独立 ASGI 推送网关（realtime_gateway/），
 * 通过反向代理 /realtime/ 路径访问。seq 由网关单进程分配，天然全局唯一。
 */
import { useAuthStore } from '@/stores/auth';
import { fetchSSETicket } from '@/services/sseTicket';
export interface DeviceChangeEvent {
  event_id: string;
  device_id: number;
  op_type: string;
  seq: number;
  ts: number;
  affected_ports: string[];
  affected_vlans: number[];
  affected_lags: number[];
  affected_connections: number[];
  task_id?: string;
  success?: boolean;
  message?: string;
  error?: string;
  detail_op_type?: string;
}

type ResourceType = 'ports' | 'vlans' | 'lags' | 'connections' | 'all';
type EventHandler = (event: DeviceChangeEvent) => void;

class DeviceEventBus {
  private seq = 0;
  private source: EventSource | null = null;
  private listeners = new Map<ResourceType, Set<EventHandler>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private destroyed = false;
  private unrecoverable = false;

  constructor(private readonly deviceId: number) {
    this.connect();
  }

  private async connect(): Promise<void> {
    if (this.destroyed || this.unrecoverable) return;

    if (this.source) {
      this.source.close();
      this.source = null;
    }
    const token = useAuthStore.getState().token;
    if (!token) {
      this.reconnectTimer = setTimeout(() => {
        void this.connect();
      }, 1000);
      return;
    }
    const ticket = await fetchSSETicket(this.deviceId);
    if (!ticket) {
      this.reconnectTimer = setTimeout(() => {
        void this.connect();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30_000);
      return;
    }
    const base = `/realtime/sse/switch/${this.deviceId}`;
    const qs =
      this.seq > 0
        ? `since_seq=${this.seq}&ticket=${encodeURIComponent(ticket)}`
        : `ticket=${encodeURIComponent(ticket)}`;
    const url = `${base}?${qs}`;
    this.source = new EventSource(url);

    this.source.onmessage = (e) => {
      try {
        this.dispatch(JSON.parse(e.data));
        this.reconnectDelay = 1000;
      } catch {
        /* ignore parse errors */
      }
    };

    this.source.onerror = () => {
      const readyState = this.source?.readyState;
      this.source?.close();
      this.source = null;
      if (this.destroyed) return;
      this.checkRecoverable();
    };
  }

  private async checkRecoverable(): Promise<void> {
    const ticket = await fetchSSETicket(this.deviceId);
    if (!ticket) {
      this.reconnectTimer = setTimeout(() => {
        void this.connect();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30_000);
      return;
    }
    try {
      const url = `/realtime/sse/switch/${this.deviceId}?ticket=${encodeURIComponent(ticket)}`;
      const res = await fetch(url, { method: 'HEAD' });
      if (res.status === 404 || res.status === 410) {
        this.unrecoverable = true;
        console.warn(
          `[DeviceEventBus] 设备 ${this.deviceId} SSE 端点不可用 (${res.status})，停止重连`
        );
        return;
      }
    } catch {
    }
    this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30_000);
  }

  private dispatch(event: DeviceChangeEvent): void {
    this.seq = Math.max(this.seq, event.seq);

    const isPortActionResult = event.op_type === 'port_action_result';
    const isDeviceEvent = event.op_type === 'info_refresh' || event.op_type === 'scan_complete';
    const isSyncEvent = event.op_type === 'port_sync';

    const portDataChanged =
      isPortActionResult || isDeviceEvent || isSyncEvent || event.affected_ports.length > 0;

    if (portDataChanged) this.emit('ports', event);
    if (event.affected_vlans.length > 0 || isSyncEvent) this.emit('vlans', event);
    if (event.affected_lags.length > 0 || isSyncEvent) this.emit('lags', event);
    if (portDataChanged || event.affected_connections.length > 0) this.emit('connections', event);
    this.emit('all', event);
  }

  private emit(resource: ResourceType, event: DeviceChangeEvent): void {
    this.listeners.get(resource)?.forEach((h) => {
      try {
        h(event);
      } catch (err) {
        console.error('[DeviceEventBus]', err);
      }
    });
  }

  on(resource: ResourceType, handler: EventHandler): () => void {
    if (!this.listeners.has(resource)) {
      this.listeners.set(resource, new Set());
    }
    this.listeners.get(resource)!.add(handler);
    return () => this.listeners.get(resource)!.delete(handler);
  }

  destroy(): void {
    this.destroyed = true;
    this.source?.close();
    this.source = null;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.listeners.clear();
  }
}

const _busRegistry = new Map<number, { bus: DeviceEventBus; refCount: number }>();

/**
 * 获取设备事件总线（引用计数 +1）
 * 首次调用时创建连接，后续调用复用同一连接
 */
export function getDeviceBus(deviceId: number): DeviceEventBus {
  if (!_busRegistry.has(deviceId)) {
    _busRegistry.set(deviceId, {
      bus: new DeviceEventBus(deviceId),
      refCount: 0
    });
  }
  const entry = _busRegistry.get(deviceId)!;
  entry.refCount++;
  return entry.bus;
}

/**
 * 释放设备事件总线（引用计数 -1）
 * 引用计数归零时销毁连接并从注册表移除
 */
export function releaseDeviceBus(deviceId: number): void {
  const entry = _busRegistry.get(deviceId);
  if (!entry) return;
  entry.refCount--;
  if (entry.refCount <= 0) {
    entry.bus.destroy();
    _busRegistry.delete(deviceId);
  }
}
