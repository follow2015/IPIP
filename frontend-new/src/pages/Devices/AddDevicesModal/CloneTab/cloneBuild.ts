/**
 * cloneBuild — 克隆请求构建纯逻辑
 *
 * 把 CloneTab.handleSubmit 中「模板 → 创建请求」的映射逻辑下沉为纯函数，
 * 使主 hook 只做编排（校验 / 提交 / 结果处理），便于单元测试与跨组件复用。
 */
import type { Device } from '@/types/models';
import type { CreateDeviceRequest } from '@/services/device';
import type { DeviceBatchRow } from '../shared';
import { DeviceType } from '@/types/enums';


export const CLONE_EXCLUDE_KEYS = new Set<string>([
  'id',
  'device_name',
  'serial_number',
  'hostname',
  'management_ip',
  'mac_address',
  'ip_address',
  'asset_number',
  'u_position',
  'created_at',
  'updated_at',
  'deleted_at',
  'ipmi_address',
  
  'cabinet_number',
  'status_name',
  'customer_name',
  'room_id',
  'room_name',
  'responsible_person_name',
  'responsible_person_username',
  'available_u',
  'device_count',
  'u_usage_rate',
  'power_usage_rate',
  'parent_u_position',
  'parent_height_u',
  'switch_credential',
  'port_summary',
  'deleted_location_snapshot',
  'deleted_children_snapshot'
]);

export interface BuildCloneOptions {
  targetCabinetId: number | null;
  isNodeTemplate: boolean;
  isChassisTemplate: boolean;
  selectedChassis?: Device | null;
}


export function checkNodePositionConflict(
  diffRows: DeviceBatchRow[],
  selectedChassis?: Device | null
): boolean {
  const usedPositions = new Set<number>();
  for (const r of diffRows) {
    if (!r.node_row || !r.node_col) continue;
    const cols = selectedChassis?.node_cols || 1;
    const pos = (r.node_row - 1) * cols + r.node_col;
    if (pos > 0) usedPositions.add(pos);
  }
  return usedPositions.size < diffRows.length;
}


export function buildCloneRequests(
  templateDetail: Device,
  diffRows: DeviceBatchRow[],
  opts: BuildCloneOptions
): CreateDeviceRequest[] {
  
  const baseClone: Partial<CreateDeviceRequest> = {};
  for (const [k, v] of Object.entries(templateDetail as any)) {
    if (!CLONE_EXCLUDE_KEYS.has(k) && v != null) {
      (baseClone as Record<string, unknown>)[k] = v;
    }
  }
  
  if (opts.targetCabinetId) {
    baseClone.cabinet_id = opts.targetCabinetId;
  }

  
  if (
    templateDetail.storage_items &&
    Array.isArray(templateDetail.storage_items) &&
    templateDetail.storage_items.length > 0
  ) {
    baseClone.storage_items = templateDetail.storage_items.map((si: any) => ({
      template_id: si.template_id ?? undefined,
      storage_type: si.storage_type ?? undefined,
      capacity: si.capacity ?? undefined,
      interface_type: si.interface_type ?? undefined,
      slot_number: si.slot_number ?? undefined
    }));
  }
  if (
    templateDetail.nic_ports &&
    Array.isArray(templateDetail.nic_ports) &&
    templateDetail.nic_ports.length > 0
  ) {
    baseClone.nic_ports = templateDetail.nic_ports.map((np: any) => ({
      template_id: np.template_id ?? undefined,
      nic_number: np.nic_number ?? undefined,
      port_number: np.port_number ?? undefined,
      port_name: np.port_name ?? undefined,
      port_type: np.port_type ?? undefined,
      port_speed: np.port_speed ?? undefined,
      port_status: np.port_status ?? undefined,
      description: np.description ?? undefined
    }));
  }

  
  if (templateDetail.device_type === DeviceType.NETWORK && templateDetail.switch_credential) {
    const sc: any = templateDetail.switch_credential;
    baseClone.switch_config = {
      protocol: sc.protocol ?? undefined,
      device_type: sc.device_type ?? undefined,
      authentication_method: sc.authentication_method ?? undefined,
      has_ssh: sc.has_ssh ?? undefined,
      switch_role: sc.switch_role ?? undefined,
      layer: sc.layer ?? undefined,
      uplink_device_id: sc.uplink_device_id ?? undefined,
      core_device_id: sc.core_device_id ?? undefined,
      port_num: sc.port_num ?? undefined
    };
  }

  return diffRows.map((row) => {
    const item: Partial<CreateDeviceRequest> = {
      ...baseClone,
      device_name: row.device_name,
      serial_number: row.serial_number || undefined,
      status: row.status
    };

    
    if (
      opts.isNodeTemplate &&
      row.parent_device_id &&
      row.node_row &&
      row.node_col &&
      opts.selectedChassis
    ) {
      const nodePosition =
        (row.node_row - 1) * (opts.selectedChassis.node_cols || 1) + row.node_col;
      item.height_u = 0;
      item.parent_device_id = row.parent_device_id;
      item.node_position = nodePosition;
      item.node_row = row.node_row;
      item.node_col = row.node_col;
      return item as CreateDeviceRequest;
    }
    
    if (opts.isChassisTemplate) {
      item.height_u = templateDetail.height_u;
      item.u_position = row.u_position ?? undefined;
      item.is_chassis = true;
      item.node_rows = row.node_rows ?? templateDetail.node_rows ?? 2;
      item.node_cols = row.node_cols ?? templateDetail.node_cols ?? 2;
      item.total_nodes =
        (row.node_rows ?? templateDetail.node_rows ?? 2) *
        (row.node_cols ?? templateDetail.node_cols ?? 2);
      item.node_naming_pattern = templateDetail.node_naming_pattern ?? undefined;
      item.auto_create_nodes = true;
      return item as CreateDeviceRequest;
    }
    
    item.height_u = templateDetail.height_u;
    item.u_position = row.u_position ?? undefined;
    return item as CreateDeviceRequest;
  });
}
