/**
 * usePortAction — 异步端口操作 Hook
 *
 * 提交端口操作到后台线程，通过 SSE 接收结果驱动缓存刷新。
 * 操作结果由后端 NotificationService.notify() 创建站内信，
 * 前端通过 NotificationBell 展示，不再弹出 antd notification 卡片。
 * 所有 SSH 操作提交后自动启动兜底轮询，防止 SSE 事件丢失导致列表不刷新。
 *
 * 网管设备(hasSsh=true): 异步SSH操作，SSE推送结果，提交后兜底轮询。
 * 非网管设备(hasSsh=false): 同步DB操作，后端立即返回结果，无需轮询。
 */
import { useCallback, useEffect, useRef } from 'react';
import { useMessage } from '@/hooks/useMessage';
import { post } from '@/services/api-client';
import { useQueryClient } from '@tanstack/react-query';
import type { DeviceChangeEvent } from '@/hooks/useDeviceEvents';
import { queryKeys } from '@/services/query-keys';

const ACTION_LABELS: Record<string, string> = {
  enable_port: '启用端口',
  disable_port: '关闭端口',
  update_port_info: '修改端口信息',
  set_port_speed: '设置端口限速',
  set_port_vlan: '配置VLAN',
  set_port_ip: '配置IP',
  delete_port_ip: '删除IP',
  clear_port_config: '清除端口配置',
  delete_interface: '删除接口',
  add_port_to_trunk: '加入链路聚合',
  delete_trunk: '删除链路聚合',
  create_port_channel: '创建链路聚合',
  remove_port_from_channel: '移除链路聚合成员',
  delete_vlan: '删除VLAN'
};

const FALLBACK_POLL_INTERVAL = 5_000;
const FALLBACK_POLL_MAX = 3;

interface UsePortActionOptions {
  switchId: number;
  onRefresh?: () => void;
  hasSsh?: boolean;
}

/**
 * 异步端口操作 Hook
 *
 * 提交操作到后台线程，通过 SSE 接收结果驱动缓存刷新。
 * 操作结果由站内信承载，不再弹出 notification 卡片。
 */
export function usePortAction({ switchId, onRefresh, hasSsh = true }: UsePortActionOptions) {
  const message = useMessage();
  const queryClient = useQueryClient();

  const pendingRef = useRef<
    Map<
      string,
      {
        action: string;
        port: string;
      }
    >
  >(new Map());

  const pollTimersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  useEffect(() => {
    return () => {
      pendingRef.current.clear();
      pollTimersRef.current.forEach(clearInterval);
      pollTimersRef.current.clear();
    };
  }, []);

  const handleSseEvent = useCallback(
    (event: DeviceChangeEvent) => {
      if (event.op_type !== 'port_action_result' || !event.task_id) return;

      const pending = pendingRef.current;
      const info = pending.get(event.task_id);
      if (!info) return;

      pending.delete(event.task_id);

      queryClient.invalidateQueries({ queryKey: ['switches', switchId, 'ports'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.vlans.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.all });
      onRefresh?.();
    },
    [switchId, queryClient, onRefresh]
  );

  const onEvent = useCallback(
    (event: DeviceChangeEvent) => {
      handleSseEvent(event);
    },
    [handleSseEvent]
  );

  const submitAction = useCallback(
    async (action: string, port: string, params: Record<string, unknown> = {}) => {
      const label = ACTION_LABELS[action] || action;

      try {
        if (!hasSsh) {
          const res = await post<{
            action: string;
            status: string;
            result?: { success: boolean; message?: string; error?: string };
          }>(`/switch/${switchId}/ports/action`, { action, port, params });

          const result = res.data?.result;
          if (result?.success) {
            message.success(result.message || `${label}成功`);
          } else {
            message.error(result?.error || `${label}失败`);
          }
          queryClient.invalidateQueries({ queryKey: ['switches', switchId, 'ports'] });
          queryClient.invalidateQueries({ queryKey: queryKeys.vlans.all });
          queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.all });
          onRefresh?.();
          return;
        }

        const res = await post<{
          task_id: string;
          action: string;
          status: string;
        }>(`/switch/${switchId}/ports/action`, { action, port, params });

        const task_id = res.data?.task_id;
        if (!task_id) return;

        message.info(`${label}已提交，完成后将通过消息通知您`);

        pendingRef.current.set(task_id, { action, port });

        if (onRefresh) {
          let count = 0;
          const pollTimer = setInterval(() => {
            onRefresh();
            queryClient.invalidateQueries({ queryKey: ['switches', switchId, 'ports'] });
            queryClient.invalidateQueries({ queryKey: queryKeys.vlans.all });
            queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.all });
            if (++count >= FALLBACK_POLL_MAX) {
              clearInterval(pollTimer);
              pollTimersRef.current.delete(pollTimer);
            }
          }, FALLBACK_POLL_INTERVAL);
          pollTimersRef.current.add(pollTimer);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        message.error(`${label}提交失败：${msg}`);
      }
    },
    [switchId, hasSsh, message, onRefresh, queryClient]
  );

  return { submitAction, onEvent };
}
