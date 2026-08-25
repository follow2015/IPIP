/**
 * useDeviceEvents — 基于 DeviceEventBus 的 React Hook
 *
 * 订阅设备 SSE 事件，根据资源类型自动失效 TanStack Query 缓存，
 * 并支持额外的 onEvent 回调供组件处理业务逻辑。
 *
 * 用法：
 *   useDeviceEvents(deviceId, 'ports', (event) => { ... });
 *   useDeviceEvents(deviceId, 'vlans');
 */
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getDeviceBus, releaseDeviceBus } from '@/services/DeviceEventBus';
import type { DeviceChangeEvent } from '@/services/DeviceEventBus';
import { queryKeys } from '@/services/query-keys';

type ResourceType = 'ports' | 'vlans' | 'lags' | 'connections';


export function useDeviceEvents(
  deviceId: number,
  resource: ResourceType,
  onEvent?: (event: DeviceChangeEvent) => void,
  enabled: boolean = true
): void {
  const queryClient = useQueryClient();
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!deviceId || !enabled) return;
    const bus = getDeviceBus(deviceId);

    const unsubscribe = bus.on(resource, (event) => {
      switch (resource) {
        case 'ports':
          queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
          queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
          
          if (event.op_type === 'info_refresh' || event.op_type === 'scan_complete') {
            queryClient.invalidateQueries({ queryKey: queryKeys.switches.detail(deviceId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(deviceId) });
            
            queryClient.invalidateQueries({ queryKey: queryKeys.switches.all });
            queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
          }
          event.affected_ports.forEach((portName) => {
            queryClient.invalidateQueries({
              queryKey: queryKeys.switches.portDetail(deviceId, portName)
            });
          });
          break;
        case 'vlans':
          queryClient.invalidateQueries({ queryKey: queryKeys.vlans.byDevice(deviceId) });
          event.affected_vlans.forEach((vlanDbId) => {
            queryClient.invalidateQueries({ queryKey: queryKeys.vlans.detail(vlanDbId) });
          });
          if (event.affected_ports.length > 0) {
            queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
          }
          break;
        case 'lags':
          queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.byDevice(deviceId) });
          event.affected_lags.forEach((lagId) => {
            queryClient.invalidateQueries({ queryKey: queryKeys.linkAggregation.detail(lagId) });
          });
          if (event.affected_ports.length > 0) {
            queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
          }
          break;
        case 'connections':
          queryClient.invalidateQueries({ queryKey: queryKeys.devices.connections(deviceId) });
          
          
          queryClient.invalidateQueries({
            queryKey: [...queryKeys.devices.detail(deviceId), 'port-links']
          });
          
          
          queryClient.invalidateQueries({
            queryKey: [...queryKeys.devices.connections(deviceId), 'switch']
          });
          if (event.affected_ports.length > 0) {
            queryClient.invalidateQueries({ queryKey: queryKeys.switches.withPorts(deviceId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.devices.networkPorts(deviceId) });
          }
          break;
      }
      onEventRef.current?.(event);
    });

    return () => {
      unsubscribe();
      releaseDeviceBus(deviceId);
    };
  }, [deviceId, resource, queryClient, enabled]);
}


export function usePortActionResult(
  deviceId: number,
  onResult: (event: DeviceChangeEvent) => void
): void {
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  useEffect(() => {
    if (!deviceId) return;
    const bus = getDeviceBus(deviceId);
    const unsubscribe = bus.on('all', (event) => {
      if (event.op_type === 'port_action_result') {
        onResultRef.current(event);
      }
    });
    return () => {
      unsubscribe();
      releaseDeviceBus(deviceId);
    };
  }, [deviceId]);
}

export type { DeviceChangeEvent };
