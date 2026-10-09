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
import { useEffect, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getDeviceBus, releaseDeviceBus } from '@/services/DeviceEventBus';
import type { DeviceChangeEvent } from '@/services/DeviceEventBus';
import { queryKeys } from '@/services/query-keys';
import { createCoalescedInvalidator } from '@/utils/coalescedInvalidate';

type ResourceType = 'ports' | 'vlans' | 'lags' | 'connections';

/**
 * 订阅设备事件并自动失效相关缓存
 *
 * @param deviceId  设备 ID
 * @param resource  资源类型（ports/vlans/lags/connections）
 * @param onEvent   可选的事件回调
 * @param enabled   是否启用订阅，默认 true；设为 false 时不建立 SSE 连接
 */
export function useDeviceEvents(
  deviceId: number,
  resource: ResourceType,
  onEvent?: (event: DeviceChangeEvent) => void,
  enabled: boolean = true
): void {
  const queryClient = useQueryClient();
  const invalidator = useMemo(() => createCoalescedInvalidator(queryClient), [queryClient]);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!deviceId || !enabled) return;
    const bus = getDeviceBus(deviceId);

    const unsubscribe = bus.on(resource, (event) => {
      switch (resource) {
        case 'ports':
          invalidator.invalidate(queryKeys.switches.withPorts(deviceId));
          invalidator.invalidate(queryKeys.devices.networkPorts(deviceId));
          if (event.op_type === 'info_refresh' || event.op_type === 'scan_complete') {
            invalidator.invalidate(queryKeys.switches.detail(deviceId));
            invalidator.invalidate(queryKeys.devices.detail(deviceId));
            invalidator.invalidate(queryKeys.switches.all);
            invalidator.invalidate(queryKeys.devices.all);
          }
          event.affected_ports.forEach((portName) => {
            invalidator.invalidate(queryKeys.switches.portDetail(deviceId, portName));
          });
          break;
        case 'vlans':
          invalidator.invalidate(queryKeys.vlans.byDevice(deviceId));
          event.affected_vlans.forEach((vlanDbId) => {
            invalidator.invalidate(queryKeys.vlans.detail(vlanDbId));
          });
          if (event.affected_ports.length > 0) {
            invalidator.invalidate(queryKeys.switches.withPorts(deviceId));
            invalidator.invalidate(queryKeys.devices.networkPorts(deviceId));
          }
          break;
        case 'lags':
          invalidator.invalidate(queryKeys.linkAggregation.byDevice(deviceId));
          event.affected_lags.forEach((lagId) => {
            invalidator.invalidate(queryKeys.linkAggregation.detail(lagId));
          });
          if (event.affected_ports.length > 0) {
            invalidator.invalidate(queryKeys.switches.withPorts(deviceId));
            invalidator.invalidate(queryKeys.devices.networkPorts(deviceId));
          }
          break;
        case 'connections':
          invalidator.invalidate(queryKeys.devices.connections(deviceId));
          invalidator.invalidate([...queryKeys.devices.detail(deviceId), 'port-links']);
          invalidator.invalidate([...queryKeys.devices.connections(deviceId), 'switch']);
          if (event.affected_ports.length > 0) {
            invalidator.invalidate(queryKeys.switches.withPorts(deviceId));
            invalidator.invalidate(queryKeys.devices.networkPorts(deviceId));
          }
          break;
      }
      onEventRef.current?.(event);
    });

    return () => {
      unsubscribe();
      releaseDeviceBus(deviceId);
      invalidator.flush();
    };
  }, [deviceId, resource, invalidator, enabled]);
}

/**
 * 订阅端口操作结果事件（op_type === 'port_action_result'）
 *
 * @param deviceId  设备 ID
 * @param onResult  操作结果回调
 */
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
