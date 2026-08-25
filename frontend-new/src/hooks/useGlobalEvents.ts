/**
 * useGlobalEvents — 全局 SSE 事件 Hook
 *
 * 订阅 /realtime/sse/global 全局事件流（对应 ASGI 网关 global_event_stream()），
 * 接收不绑定特定交换机的广播事件，如机房扫描完成、批量配置变更等，
 * 驱动相关 TanStack Query 缓存失效。
 *
 * SSE 服务已从 Flask 迁移至独立 ASGI 推送网关（realtime_gateway/），
 * 通过反向代理 /realtime/ 路径访问。
 *
 * 设计原则：
 * - 全局事件在应用布局层（AppLayout）挂载一次，不在页面组件重复订阅
 * - 页面组件通过 useGlobalEventListener 注册回调接收事件，不创建额外 SSE 连接
 * - 复用 useSSEConnection 的连接管理（token 认证、断线轮询降级、去重）
 * - 事件驱动缓存失效，不直接操作 UI 状态（UI 响应由各查询 hook 的 onSuccess 处理）
 *
 * 后端对应：
 *   emit_global_event("room_scan_complete", {"room_id": 3})
 *   → Redis Pub/Sub → ASGI 网关 → GET /realtime/sse/global SSE 流
 *   → data: {"event_type": "room_scan_complete", "payload": {"room_id": 3}, "ts": ...}
 */
import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/services/query-keys';
import { useSSEConnection } from './useSSEConnection';


export interface GlobalEvent {
  event_type: string;
  payload: Record<string, unknown>;
  ts: number;
}

interface RoomScanCompletePayload {
  scope: string;
  room_id?: number | null;
  virtual_room_id?: number | null;
}

interface ResourceChangePayload {
  resource: string;
  op: string;
  ids: number[];
  extra?: Record<string, unknown>;
}

interface TaskFailedPayload {
  task_id: string;
  task_type: string;
  error: string;
}

interface NotificationCreatedPayload {
  notification_id: number;
  type: string;
  severity: string;
}

const RESOURCE_QUERY_MAP: Record<string, readonly unknown[]> = {
  device: queryKeys.devices.all,
  cabinet: queryKeys.cabinets.all,
  room: queryKeys.rooms.all,
  customer: queryKeys.customers.all,
  user: queryKeys.users.all,
  network: queryKeys.networks.all,
  ip: queryKeys.ip.all,
  virtual_room: ['virtual-rooms'] as const
};


type GlobalEventHandler = (event: GlobalEvent) => void;

const _globalListeners = new Set<GlobalEventHandler>();

/**
 * 注册全局事件监听器。
 * 在 AppLayout 中 useGlobalEvents 收到 SSE 事件后，会通知所有已注册的监听器。
 *
 * @param handler - 事件处理回调
 * @returns 取消注册函数
 */
export function onGlobalEvent(handler: GlobalEventHandler): () => void {
  _globalListeners.add(handler);
  return () => _globalListeners.delete(handler);
}

/**
 * React Hook：在组件中注册全局事件监听器，组件卸载时自动取消注册。
 *
 * 用法：
 * ```tsx
 * useGlobalEventListener((event) => {
 *   if (event.event_type === 'scan_progress') { ... }
 * });
 * ```
 *
 * @param handler - 事件处理回调（建议用 useCallback 包裹）
 */
export function useGlobalEventListener(handler: GlobalEventHandler): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const stableHandler: GlobalEventHandler = (event) => handlerRef.current(event);
    _globalListeners.add(stableHandler);
    return () => {
      _globalListeners.delete(stableHandler);
    };
  }, []);
}


interface UseGlobalEventsOptions {
  enabled?: boolean;
}


/**
 * 订阅全局 SSE 事件流，自动驱动相关查询缓存失效。
 *
 * **仅在 AppLayout 中调用一次**，不要在页面组件中重复调用。
 * 页面组件如需接收全局事件，使用 useGlobalEventListener 注册回调。
 *
 * @param options - 订阅选项
 */
export function useGlobalEvents({ enabled = true }: UseGlobalEventsOptions = {}) {
  const queryClient = useQueryClient();

  const handleRoomScanComplete = useCallback(
    (payload: RoomScanCompletePayload) => {
      const { room_id, virtual_room_id } = payload;

      queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });

      queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });

      queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });

      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats });

      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });

      queryClient.invalidateQueries({ queryKey: queryKeys.topology.all });

      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });

      if (room_id) {
        queryClient.invalidateQueries({
          queryKey: [...queryKeys.switches.all, 'scan-progress', room_id]
        });
        queryClient.invalidateQueries({
          queryKey: [...queryKeys.networks.all, 'scan-status', room_id]
        });
      }

      if (virtual_room_id) {
        queryClient.invalidateQueries({
          queryKey: ['virtual-rooms']
        });
      }
    },
    [queryClient]
  );

  const handleResourceChange = useCallback(
    (payload: ResourceChangePayload) => {
      const queryKey = RESOURCE_QUERY_MAP[payload.resource];
      if (queryKey) {
        queryClient.invalidateQueries({ queryKey });
      }

      if (payload.resource === 'device') {
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats });
        queryClient.invalidateQueries({ queryKey: queryKeys.topology.all });
        queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
        if (payload.op === 'location_change' || payload.op === 'status_change') {
          queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
        }
      }

      if (payload.resource === 'cabinet') {
        queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      }

      if (payload.resource === 'customer') {
        queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.all });
        queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
        queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
        queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
      }
    },
    [queryClient]
  );

  const handleEvent = useCallback(
    (event: GlobalEvent) => {
      switch (event.event_type) {
        case 'room_scan_complete':
          handleRoomScanComplete(event.payload as unknown as RoomScanCompletePayload);
          break;

        case 'bulk_config_change':
          queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
          break;

        case 'resource_change':
          handleResourceChange(event.payload as unknown as ResourceChangePayload);
          break;

        case 'notification_created':
          queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
          break;

        case 'task_failed':
          break;

        case 'ip_scan_complete':
          queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
          queryClient.invalidateQueries({ queryKey: queryKeys.networks.all });
          break;

        case 'scan_failed':
          queryClient.invalidateQueries({ queryKey: queryKeys.ip.all });
          break;

        case 'monitor_alert':
        case 'monitor_recover':
        case 'monitor_ack':
          queryClient.invalidateQueries({ queryKey: queryKeys.monitor.alertsAll });
          queryClient.invalidateQueries({ queryKey: queryKeys.monitor.statusesAll });
          queryClient.invalidateQueries({ queryKey: queryKeys.monitor.overview });
          queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
          break;

        default:
          break;
      }

      _globalListeners.forEach((h) => {
        try {
          h(event);
        } catch (err) {
          console.error('[GlobalEvent]', err);
        }
      });
    },
    [handleRoomScanComplete, handleResourceChange, queryClient]
  );

  const refreshAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
  }, [queryClient]);

  useSSEConnection({
    url: '/realtime/sse/global',
    enabled,
    onMessage: (data: string) => {
      try {
        const event: GlobalEvent = JSON.parse(data);
        handleEvent(event);
      } catch {
      }
    },
    onFallbackPoll: refreshAll,
    label: 'SSE-Global'
  });
}
