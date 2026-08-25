/**
 * usePortSync — SSH（网管）模式专属逻辑
 * 承接原组件顶部的：useSyncSwitchPorts / usePortAction / useDeviceEvents(SSE) / 回退轮询 / handleSync
 *
 * 注意：该 hook 在组合根无条件调用（不限于 hasSsh），以保留「非 SSH 模式也订阅端口 SSE」的原始行为。
 */
import { useEffect, useRef } from 'react';
import { useSyncSwitchPorts } from '@/services/switch';
import { usePortAction } from '@/hooks/usePortAction';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import { useMessage } from '@/hooks/useMessage';
import { confirm } from '@/utils/confirm';
import { startPolling } from './portSortFilter';

interface UsePortSyncArgs {
  deviceId: number;
  refetch: () => void;
  setHighlightPort: (port: string | null) => void;
  
  scheduleClearHighlight: () => void;
  
  hasSsh?: boolean;
}

export function usePortSync({
  deviceId,
  refetch,
  setHighlightPort,
  scheduleClearHighlight,
  hasSsh = true
}: UsePortSyncArgs) {
  const message = useMessage();
  const syncSwitchPorts = useSyncSwitchPorts();
  
  const cancelPollingRef = useRef<(() => void) | null>(null);

  const { submitAction, onEvent: onPortActionEvent } = usePortAction({
    switchId: deviceId,
    onRefresh: () => refetch(),
    hasSsh
  });

  
  useEffect(() => {
    return () => {
      cancelPollingRef.current?.();
    };
  }, []);

  
  useDeviceEvents(deviceId, 'ports', (event) => {
    onPortActionEvent(event);
    if (event.op_type === 'info_refresh') {
      if (event.success !== false) {
        refetch();
        cancelPollingRef.current?.();
        cancelPollingRef.current = null;
      }
    }
    if (event.op_type === 'scan_complete') {
      if (event.success !== false) {
        refetch();
        cancelPollingRef.current?.();
        cancelPollingRef.current = null;
      }
    }
    if (event.op_type === 'port_sync' && event.affected_ports?.includes('*')) {
      refetch();
      cancelPollingRef.current?.();
      cancelPollingRef.current = null;
    }
    if (
      [
        'port_vlan_config',
        'port_ip_set',
        'vlan_delete',
        'lag_delete',
        'port_update',
        'port_disable',
        'port_enable'
      ].includes(event.op_type)
    ) {
      refetch();
    }
    if (event.op_type === 'port_action_result' && event.success) {
      refetch();
    }
    const port = event.affected_ports?.[0];
    if (port) {
      setHighlightPort(port);
      scheduleClearHighlight();
    }
  });

  
  const handleSync = () => {
    confirm({
      title: '确认同步',
      content: '将从设备获取所有端口信息并更新，此操作在后台执行，完成后自动刷新。',
      onOk: async () => {
        try {
          await syncSwitchPorts.mutateAsync(deviceId);
          message.info('端口同步已提交，完成后将通过消息通知您');
          cancelPollingRef.current?.();
          cancelPollingRef.current = startPolling(() => refetch(), 5000, 3);
        } catch {
          
        }
      }
    });
  };

  return { handleSync, isPending: syncSwitchPorts.isPending, submitAction };
}
