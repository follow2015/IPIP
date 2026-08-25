/**
 * 设备连接服务
 * - CRUD + TanStack Query hooks
 * - device_to_network: 通过 /api/device-connections 查询
 * - network_to_network: 通过 /api/devices/:id/port-links 直接查 network_ports
 */
import { useQuery } from '@tanstack/react-query';
import { get, post, put, del } from './api-client';
import { queryKeys } from './query-keys';
import { useInvalidatingMutation } from '@/hooks/useInvalidatingMutation';
import type { DeviceConnection } from '@/types/models';

export interface PortLink {
  id: number;
  local_port_id: number;
  local_device_id: number;
  peer_device_id: number;
  link_type: 'network_to_network';
  connection_type: string | null;
  vlan_id: number | null;
  status: string;
  notes: string | null;
  bandwidth: string | null;
  description: string | null;
  lag_group_id: number | null;
  port_name: string;
  port_type: string | null;
  speed: string | null;
  usage_status: string;
  device_id: number;
  device_name?: string;
  peer_port_name?: string;
  peer_port_id?: number;
  peer_port_type?: string | null;
  peer_port_speed?: string | null;
  peer_device_id_ref?: number;
  peer_device_name?: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConnectionRequest {
  device_id: number;
  switch_device_id: number;
  switch_port_id?: number;
  peer_port_id?: number;
  device_nics_port_id?: number;
  connection_type?: string;
  link_type?: 'device_to_network' | 'network_to_network';
  vlan_id?: number;
  status?: string;
  notes?: string;
}

export function useDeviceConnections(deviceId: number) {
  return useQuery({
    queryKey: queryKeys.devices.connections(deviceId),
    queryFn: async () => {
      const res = await get<DeviceConnection[]>('/device-connections', { device_id: deviceId });
      return res.data;
    },
    enabled: deviceId > 0
  });
}

export function useSwitchConnections(switchDeviceId: number) {
  return useQuery({
    queryKey: [...queryKeys.devices.connections(switchDeviceId), 'switch'],
    queryFn: async () => {
      const res = await get<DeviceConnection[]>('/device-connections', {
        switch_device_id: switchDeviceId
      });
      return res.data;
    },
    enabled: switchDeviceId > 0
  });
}

export function usePortLinks(deviceId: number) {
  return useQuery({
    queryKey: [...queryKeys.devices.detail(deviceId), 'port-links'],
    queryFn: async () => {
      const res = await get<PortLink[]>(`/devices/${deviceId}/port-links`);
      return res.data;
    },
    enabled: deviceId > 0
  });
}

export function useCreateConnection(deviceId: number) {
  return useInvalidatingMutation(
    (data: Omit<ConnectionRequest, 'device_id'>) =>
      post<DeviceConnection>('/device-connections', { ...data, device_id: deviceId }),
    (_data, variables) => {
      const keys: Array<readonly unknown[]> = [
        queryKeys.devices.connections(deviceId),
        [...queryKeys.devices.detail(deviceId), 'port-links'],
        queryKeys.devices.networkPorts(deviceId)
      ];
      if (variables.switch_device_id) {
        keys.push(
          queryKeys.devices.connections(variables.switch_device_id),
          [...queryKeys.devices.detail(variables.switch_device_id), 'port-links'],
          queryKeys.devices.networkPorts(variables.switch_device_id)
        );
      }
      return keys;
    }
  );
}

export function useUpdateConnection() {
  return useInvalidatingMutation(
    ({ connId, data }: { connId: number; data: Partial<ConnectionRequest> }) =>
      put<DeviceConnection>(`/device-connections/${connId}`, data),
    queryKeys.devices.all
  );
}

export function useDeleteConnection(deviceId: number) {
  return useInvalidatingMutation(
    (params: { connId: number; switchDeviceId?: number }) =>
      del<void>(`/device-connections/${params.connId}`),
    (_data, variables) => {
      const keys: Array<readonly unknown[]> = [queryKeys.devices.connections(deviceId)];
      if (variables.switchDeviceId) {
        keys.push(queryKeys.devices.connections(variables.switchDeviceId));
      }
      return keys;
    }
  );
}

export function useDisconnectPortLink(deviceId: number) {
  return useInvalidatingMutation(
    (connectionId: number) =>
      del<{ peer_device_id: number }>(`/devices/${deviceId}/port-links/${connectionId}`),
    (res) => {
      const keys: Array<readonly unknown[]> = [
        [...queryKeys.devices.detail(deviceId), 'port-links'],
        queryKeys.devices.networkPorts(deviceId)
      ];
      const peerDeviceId = res.data?.peer_device_id;
      if (peerDeviceId) {
        keys.push(
          [...queryKeys.devices.detail(peerDeviceId), 'port-links'],
          queryKeys.devices.networkPorts(peerDeviceId)
        );
      }
      return keys;
    }
  );
}

export interface PortLinkUpdateRequest {
  connection_type?: string;
  vlan_id?: number | null;
  status?: string;
  notes?: string | null;
  bandwidth?: string | null;
  description?: string | null;
  lag_group_id?: number | null;
}

export function useUpdatePortLink(deviceId: number) {
  return useInvalidatingMutation(
    ({ connectionId, data }: { connectionId: number; data: PortLinkUpdateRequest }) =>
      put<PortLink>(`/devices/${deviceId}/port-links/${connectionId}`, data),
    [...queryKeys.devices.detail(deviceId), 'port-links']
  );
}
