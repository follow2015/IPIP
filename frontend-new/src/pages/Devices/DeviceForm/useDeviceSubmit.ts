/**
 * useDeviceSubmit — DeviceForm 提交/payload 构建逻辑
 *
 * 从原 DeviceForm.tsx 的 handleSubmit 拆出。集中了：
 *   - 表单字段清理（移除辅助字段、端口/网卡配置字段）
 *   - 机箱+生成子节点场景下 node_hardware / nic_ports / storage_items 的注入
 *   - 创建/编辑两条路径的差异处理
 *   - 编辑模式下网卡端口的单独更新、创建模式下批量端口/网卡的生成
 *   - N2N 上行连接的自动创建（含编辑模式下旧连接清理）
 *
 * 拆出的动机：这是全文件中 payload 构建最集中、也是历史上 P0（node_hardware
 * 遗漏 GPU 字段等）反复出现的区域，独立成文件后可单独审查/单元测试，
 * 不必每次都在 1600+ 行的表单组件里定位。
 */

import type { Form } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { get, post, put, del } from '@/services/api-client';
import { expandNicPorts } from '@/components/NicConfigFields';
import { buildStorageSummary, buildStorageList } from '@/components/HardwareConfigFields';
import type { StorageItem } from './deviceFormUtils';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import type { Device } from '@/types/models';
import { DeviceType } from '@/types/enums';

interface UseDeviceSubmitParams {
  form: ReturnType<typeof Form.useForm>[0];
  isEdit: boolean;
  editRecord: Device | null;
  
  generateNodes: boolean;
  
  nicComponentTemplates: any[];
  createDevice: { mutateAsync: (values: any) => Promise<{ data?: { id?: number } } | any> };
  updateDevice: { mutateAsync: (values: any) => Promise<any> };
  message: {
    success: (msg: string) => void;
    warning: (msg: string, duration?: number) => void;
    error: (msg: string) => void;
  };
  onClose: () => void;
}


const SUBMIT_DATE_FIELDS = [
  'purchase_date',
  'warranty_start',
  'warranty_end',
  'online_date',
  'offline_date'
];


function serializeDateField(value: unknown): unknown {
  if (dayjs.isDayjs(value)) {
    return (value as Dayjs).format('YYYY-MM-DD');
  }
  return value;
}


function buildNodeHardware(values: Record<string, any>) {
  return {
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
    storage_summary: values.storage_summary || undefined
  };
}

export function useDeviceSubmit({
  form,
  isEdit,
  editRecord,
  generateNodes,
  nicComponentTemplates,
  createDevice,
  updateDevice,
  message,
  onClose
}: UseDeviceSubmitParams) {
  const handleSubmit = async () => {
    try {
      const values = (await form.validateFields()) as Record<string, any>;
      
      
      for (const f of SUBMIT_DATE_FIELDS) {
        if (values[f] !== undefined) {
          values[f] = serializeDateField(values[f]);
        }
      }
      
      delete values.device_gap;
      
      const portGroupsVal = values.port_groups;
      delete values.port_groups;
      delete values.nic_templates;
      

      if (values.device_subtype === 'chassis') {
        values.is_chassis = true;
      }

      
      const nicPortsFormVal = values.nic_ports as { template_id?: number }[] | undefined;
      
      
      const isChassisWithNodes = generateNodes && values.is_chassis;
      if (!isChassisWithNodes) {
        delete values.nic_ports;
      } else {
        
        const expandedNicPorts = expandNicPorts(nicPortsFormVal, nicComponentTemplates);
        if (expandedNicPorts.length > 0) {
          values.nic_ports = expandedNicPorts;
        } else {
          delete values.nic_ports;
        }
      }

      
      const storageItems = values.storage_items as
        (StorageItem & { template_id?: number })[] | undefined;
      if (storageItems && storageItems.length > 0) {
        values.storage_summary = buildStorageSummary(storageItems);
        values.storage_items = buildStorageList(storageItems);
      } else {
        delete values.storage_items;
      }

      if (isEdit) {
        
        
        if (generateNodes && values.is_chassis) {
          values.auto_create_nodes = true;
          values.overwrite_nodes = true;
          values.node_hardware = buildNodeHardware(values);
          
        }

        
        await updateDevice.mutateAsync({ id: editRecord!.id, ...values });

        
        if (
          !values.is_chassis &&
          values.device_type === DeviceType.SERVER &&
          nicPortsFormVal &&
          nicPortsFormVal.length > 0
        ) {
          try {
            const expandedNicPorts = expandNicPorts(nicPortsFormVal, nicComponentTemplates);
            if (expandedNicPorts.length > 0) {
              
              const nicGroups: Record<number, typeof expandedNicPorts> = {};
              for (const p of expandedNicPorts) {
                const num = p.nic_number;
                if (!nicGroups[num]) nicGroups[num] = [];
                nicGroups[num].push(p);
              }
              const nics = Object.entries(nicGroups).map(([, ports]) => ({
                nic_number: ports[0].nic_number,
                nic_name: ports[0].nic_name,
                ports: ports.map((p) => ({
                  port_number: p.port_number,
                  port_type: p.port_type,
                  speed: p.port_speed,
                  port_name: p.port_name,
                  description: p.description
                }))
              }));
              await put(`/devices/${editRecord!.id}/nics`, { nics });
            }
          } catch {
            
          }
        }

        
        let n2nWarning = '';
        if (values.device_type === DeviceType.NETWORK && values.switch_config) {
          const sc = values.switch_config;
          const uplinkDevId = sc.uplink_device_id;
          const peerPortIds: number[] = sc.peer_port_ids ?? []; 
          
          
          let uplinkPortIds: number[] = sc.uplink_port_ids ?? [];

          if (uplinkDevId && peerPortIds.length > 0) {
            
            if (isEdit) {
              try {
                
                const { data: freshLinks } = await get<any[]>(
                  `/devices/${editRecord!.id}/port-links`
                );
                const oldConns = (freshLinks || []).filter(
                  (link: any) =>
                    link.peer_device_id === uplinkDevId || link.local_device_id === uplinkDevId
                );
                for (const conn of oldConns) {
                  try {
                    await del(`/devices/${editRecord!.id}/port-links/${conn.id}`);
                  } catch (err: any) {
                    
                    if (err?.response?.status !== 404) {
                      console.warn('删除旧上行连接失败:', conn.id, err);
                    }
                  }
                }
              } catch {
                
              }
            }

            
            if (uplinkPortIds.length === 0 && isEdit) {
              try {
                const { data: freshLinks } = await get<any[]>(
                  `/devices/${editRecord!.id}/port-links`
                );
                const conns = (freshLinks || []).filter(
                  (link: any) =>
                    link.peer_device_id === uplinkDevId || link.local_device_id === uplinkDevId
                );
                uplinkPortIds = conns.map((link: any) =>
                  link.local_device_id === editRecord!.id ? link.local_port_id : link.peer_port_id
                );
              } catch {
                
              }
            }

            
            const pairCount = Math.min(uplinkPortIds.length, peerPortIds.length);
            if (pairCount === 0) {
              n2nWarning =
                '已选择上行设备与对端互联端口，但无法确定本机上行端口，上行连接未创建（请同时选择上行端口）';
            } else {
              const createErrors: string[] = [];
              for (let i = 0; i < pairCount; i++) {
                try {
                  await post('/device-connections', {
                    device_id: editRecord!.id,
                    switch_device_id: uplinkDevId,
                    switch_port_id: uplinkPortIds[i], 
                    peer_port_id: peerPortIds[i], 
                    link_type: 'network_to_network',
                    connection_type: 'fiber',
                    notes: '上行'
                  });
                } catch (err: any) {
                  createErrors.push(
                    `端口对 ${i + 1}: ${err?.response?.data?.message || err?.message || '未知错误'}`
                  );
                }
              }
              if (createErrors.length > 0) {
                n2nWarning = `部分上行连接创建失败：${createErrors.join('; ')}`;
              }
            }
          } else if (uplinkDevId && peerPortIds.length === 0) {
            
            n2nWarning = '已选择上行设备但未选择对端互联端口，上行连接未创建';
          }
        }

        message.success('更新成功');
        if (n2nWarning) {
          message.warning(n2nWarning, 5);
        }
      } else {
        
        if (values.device_type === DeviceType.NETWORK && values.switch_config) {
          
        }

        
        if (generateNodes && values.is_chassis) {
          values.auto_create_nodes = true;
          values.node_hardware = buildNodeHardware(values);
          
        }

        const result = await createDevice.mutateAsync(values);
        message.success('创建成功');
        const deviceId = result?.data?.id;

        
        if (
          deviceId &&
          values.device_type === DeviceType.NETWORK &&
          !values.switch_config?.has_ssh &&
          portGroupsVal?.length > 0
        ) {
          try {
            const allPorts: {
              port_name: string;
              port_type?: string;
              speed?: string;
              usage_status?: string;
            }[] = [];
            for (const group of portGroupsVal) {
              const { template, slot, card, start, end, custom_prefix } = group ?? {};
              if (!template || !start || !end || start > end) continue;
              const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
              const prefix = template === 'custom' ? (custom_prefix ?? '') : (tpl?.prefix ?? '');
              const speed = template === 'custom' ? '' : (tpl?.speed ?? '');
              const portType = template === 'custom' ? '' : (tpl?.value ?? '');
              if (!prefix) continue;
              const s = slot ?? 0;
              const c = card ?? 0;
              for (let i = start; i <= end; i++) {
                allPorts.push({
                  port_name: `${prefix}${s}/${c}/${i}`,
                  port_type: portType,
                  speed,
                  usage_status: 'free'
                });
              }
            }
            if (allPorts.length > 0) {
              await post('/devices/switch-ports/batch', { device_id: deviceId, ports: allPorts });
              message.success(`已生成 ${allPorts.length} 个端口`);
            }
          } catch {
            
          }
        }

        
        if (
          deviceId &&
          values.device_type === DeviceType.SERVER &&
          nicPortsFormVal &&
          nicPortsFormVal.length > 0 &&
          !values.is_chassis
        ) {
          try {
            const nicPorts = expandNicPorts(nicPortsFormVal, nicComponentTemplates);
            if (nicPorts.length > 0) {
              await post(`/devices/${deviceId}/nics/batch-create`, { ports: nicPorts });
              message.success(`已创建 ${nicPorts.length} 个网卡端口`);
            }
          } catch {
            
          }
        }
      }
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return { handleSubmit };
}
