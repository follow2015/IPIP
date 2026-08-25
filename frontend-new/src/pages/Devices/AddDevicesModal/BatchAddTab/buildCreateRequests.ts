/**
 * BatchAddTab 提交请求构建（纯函数，无 React 依赖）
 *
 * 把原单体 BatchAddTab.handleSubmit 中「表单值 → CreateDeviceRequest[]」的映射逻辑
 * 与「非网管型网络设备端口生成」逻辑下沉为可单测纯函数。
 *
 * 说明：表单动态值(values)类型无法在编译期确定，这里用 any（与原单体保持一致），
 * 转换边界集中在本模块，调用方仍受 TypeScript 约束。
 */

import type { CreateDeviceRequest } from '@/services/device';
import type { Device } from '@/types/models';
import { buildStorageSummary, buildStorageList } from '@/components/HardwareConfigFields';
import { expandNicPorts } from '@/components/NicConfigFields';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import type { DeviceBatchRow } from '../shared';

export interface BuildCreateDevicesParams {
  rows: DeviceBatchRow[];
  
  values: Record<string, any>;
  isNodeMode: boolean;
  isNetworkType: boolean;
  isChassisMode: boolean;
  isServerType: boolean;
  selectedChassis?: Device | undefined;
  nicComponentTemplates?: any[];
}


export function buildCreateDevices(params: BuildCreateDevicesParams): CreateDeviceRequest[] {
  const {
    rows,
    values,
    isNodeMode,
    isNetworkType,
    isChassisMode,
    isServerType,
    selectedChassis,
    nicComponentTemplates
  } = params;

  return rows.map((row) => {
    
    const nodePosition =
      isNodeMode && row.node_row && row.node_col && selectedChassis
        ? (row.node_row - 1) * (selectedChassis.node_cols || 1) + row.node_col
        : undefined;

    return {
      device_name: row.device_name,
      device_type: values.device_type,
      device_subtype: values.device_subtype,
      device_model: row.device_model || undefined,
      serial_number: row.serial_number || undefined,
      cabinet_id: values.cabinet_id || undefined,
      u_position: isNodeMode ? undefined : (row.u_position ?? undefined),
      height_u: isNodeMode ? 0 : row.height_u,
      status: row.status,
      
      ...(isNetworkType && values.has_ssh
        ? { switch_config: { has_ssh: true, ip: '', port: 22, protocol: 'ssh' } }
        : {}),
      
      is_chassis: isChassisMode ? true : undefined,
      node_rows: isChassisMode ? (row.node_rows ?? values.node_rows ?? 2) : undefined,
      node_cols: isChassisMode ? (row.node_cols ?? values.node_cols ?? 2) : undefined,
      total_nodes: isChassisMode
        ? (row.node_rows ?? values.node_rows ?? 2) * (row.node_cols ?? values.node_cols ?? 2)
        : undefined,
      
      auto_create_nodes: isChassisMode ? values.auto_create_nodes !== false : undefined,
      node_naming_pattern: isChassisMode ? values.node_naming_pattern || undefined : undefined,
      
      parent_device_id: isNodeMode ? row.parent_device_id : undefined,
      node_position: nodePosition,
      node_row: isNodeMode ? row.node_row : undefined,
      node_col: isNodeMode ? row.node_col : undefined,
      notes:
        isNodeMode && selectedChassis && nodePosition
          ? `${selectedChassis.device_name} 节点 ${nodePosition}`
          : undefined,
      
      ...(isServerType && !isChassisMode
        ? {
            cpu: values.cpu || undefined,
            cpu_way: values.cpu_way || undefined,
            cpu_cores: values.cpu_cores || undefined,
            cpu_template_id: values.cpu_template_id || undefined,
            memory: values.memory || undefined,
            memory_size_gb: values.memory_size_gb || undefined,
            memory_template_id: values.memory_template_id || undefined,
            memory_dimm_count: values.memory_dimm_count || undefined,
            gpu: values.gpu || undefined,
            gpu_count: values.gpu_count || undefined,
            gpu_template_id: values.gpu_template_id || undefined,
            storage_summary: buildStorageSummary(values.storage_items) || undefined,
            
            storage_items: buildStorageList(values.storage_items) || undefined,
            nic_ports: expandNicPorts(values.nic_ports, nicComponentTemplates ?? []) || undefined
          }
        : {}),
      
      ...(isChassisMode && values.auto_create_nodes !== false
        ? {
            node_hardware: {
              cpu: values.cpu || undefined,
              cpu_way: values.cpu_way || undefined,
              cpu_cores: values.cpu_cores || undefined,
              cpu_template_id: values.cpu_template_id || undefined,
              memory: values.memory || undefined,
              memory_size_gb: values.memory_size_gb || undefined,
              memory_template_id: values.memory_template_id || undefined,
              memory_dimm_count: values.memory_dimm_count || undefined,
              gpu: values.gpu || undefined,
              gpu_count: values.gpu_count || undefined,
              gpu_template_id: values.gpu_template_id || undefined,
              storage_summary: buildStorageSummary(values.storage_items) || undefined
            },
            
            storage_items: buildStorageList(values.storage_items) || undefined,
            nic_ports: expandNicPorts(values.nic_ports, nicComponentTemplates ?? []) || undefined
          }
        : {})
    };
  });
}


export interface SwitchPortGenConfig {
  template?: string;
  slot?: number;
  card?: number;
  start?: number;
  end?: number;
  customPrefix?: string;
}

export interface SwitchPortPayload {
  port_name: string;
  port_type?: string;
  speed?: string;
  usage_status: string;
}


export function buildSwitchPorts(cfg: SwitchPortGenConfig): SwitchPortPayload[] | null {
  const { template, slot, card, start, end, customPrefix } = cfg;
  if (!template || start == null || end == null) return null;
  const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
  const prefix = template === 'custom' ? (customPrefix ?? '') : (tpl?.prefix ?? '');
  const speed = template === 'custom' ? '' : (tpl?.speed ?? '');
  const portType = template === 'custom' ? '' : (tpl?.value ?? '');
  if (!prefix || start > end) return null;
  const slotNum = slot ?? 0;
  const cardNum = card ?? 0;
  const ports: SwitchPortPayload[] = [];
  for (let i = start; i <= end; i++) {
    ports.push({
      port_name: `${prefix}${slotNum}/${cardNum}/${i}`,
      port_type: portType,
      speed,
      usage_status: 'free'
    });
  }
  return ports.length > 0 ? ports : null;
}
