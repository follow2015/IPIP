import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getDeviceBus, releaseDeviceBus, type DeviceChangeEvent } from '@/services/DeviceEventBus';
import { queryKeys } from '@/services/query-keys';


const PORT_DATA_OP_TYPES = new Set([
  'port_sync',
  'scan_complete',
  'info_refresh',
  'port_action_result'
]);

function isPortDataChanged(event: DeviceChangeEvent): boolean {
  return PORT_DATA_OP_TYPES.has(event.op_type) || (event.affected_ports?.length ?? 0) > 0;
}

export function useD2NConnectionSync(deviceId: number, switchIds: number[]): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (switchIds.length === 0) return;

    const unsubs: Array<() => void> = [];
    const releases: Array<() => void> = [];

    for (const sid of switchIds) {
      const bus = getDeviceBus(sid);
      releases.push(() => releaseDeviceBus(sid));
      const handler = (event: DeviceChangeEvent) => {
        if (isPortDataChanged(event)) {
          queryClient.invalidateQueries({ queryKey: queryKeys.devices.connections(deviceId) });
        }
      };
      unsubs.push(bus.on('all', handler));
    }

    return () => {
      unsubs.forEach((u) => u());
      releases.forEach((r) => r());
    };
  }, [deviceId, switchIds, queryClient]);
}
