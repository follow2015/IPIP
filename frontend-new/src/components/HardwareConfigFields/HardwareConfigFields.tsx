/**
 * 硬件配置共用组件
 *
 * 【智能组件】内部通过 useComponentTemplates 获取配件模板数据，
 * 调用方仅需传入 customerId 即可，无需自行获取模板列表。
 *
 * 统一设备新增（DeviceForm）和批量创建（AddDevicesModal）的硬件配置表单，
 * 消除两者在 CPU/内存/存储配置上的实现差异。
 *
 * 功能：
 * - CPU 型号下拉（自动回填 cpu/cpu_way/cpu_cores）
 * - 内存型号下拉（自动回填 memory，联动条数×单条容量=总容量）
 * - 存储配置 Form.List（模板下拉 + 数量 + 容量 + 类型 + 接口）
 * - 可选 IPMI 配置
 * - 所有配件模板按 customerId 过滤
 */
import { Form, Input, InputNumber, Select, Row, Col, Divider, Space, Button } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import { useComponentTemplates } from '@/services/component-template';
import type { ComponentTemplate } from '@/services/component-template';


export interface StorageItem {
  count?: number;
  capacity?: string;
  storage_type?: string;
  interface_type?: string | null;
  template_id?: number;
}


export interface HardwareConfigFieldsProps {
  
  form: FormInstance;
  
  customerId?: number | null;
  
  showIpmi?: boolean;
  
  showIpmiAddress?: boolean;
  
  prefix?: string;
  
  storageListName?: string;
  
  storageOnly?: boolean;
}


function prefixedName(prefix: string | undefined, field: string): string | (string | number)[] {
  return prefix ? [prefix, field] : field;
}


function formatCapacity(capacityGb?: number): string {
  if (!capacityGb) return '';
  if (capacityGb >= 1024) {
    const tb = capacityGb / 1024;
    return Number.isInteger(tb) ? `${tb}TB` : `${parseFloat(tb.toFixed(2))}TB`;
  }
  return `${capacityGb}GB`;
}


export default function HardwareConfigFields({
  form,
  customerId,
  showIpmi = false,
  showIpmiAddress = true,
  prefix,
  storageListName = 'storage_items',
  storageOnly = false
}: HardwareConfigFieldsProps) {
  
  const { data: cpuTemplates = [] } = useComponentTemplates('cpu', customerId);
  const { data: memoryTemplates = [] } = useComponentTemplates('memory', customerId);
  const { data: diskTemplates = [] } = useComponentTemplates('disk', customerId);
  const { data: gpuTemplates = [] } = useComponentTemplates('gpu', customerId);

  
  const setFields = (values: Record<string, unknown>) => {
    const mapped: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      mapped[prefix ? `${prefix}.${k}` : k] = v;
    }
    form.setFieldsValue(mapped);
  };

  
  const getField = (field: string) => {
    return form.getFieldValue(prefixedName(prefix, field));
  };

  return (
    <>
      {!storageOnly && <Divider plain>硬件配置</Divider>}

      {!storageOnly && (
        <>
          {}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={prefixedName(prefix, 'cpu_template_id')} label="CPU型号">
                <Select
                  placeholder="选择CPU模板（可搜索品牌/型号）"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={cpuTemplates.map((t) => ({
                    label: `${t.brand} ${t.model}`,
                    value: t.id
                  }))}
                  onChange={(id: number | undefined) => {
                    const tpl = cpuTemplates.find((t) => t.id === id);
                    if (tpl?.spec) {
                      setFields({
                        cpu: `${tpl.brand} ${tpl.model}`,
                        cpu_way: (tpl.spec.way as number) ?? undefined,
                        cpu_cores:
                          (tpl.spec.cores_per_cpu as number) ??
                          (tpl.spec.cores as number) ??
                          undefined
                      });
                    } else {
                      setFields({ cpu: undefined, cpu_way: undefined, cpu_cores: undefined });
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'cpu_way')} label="CPU路数">
                <InputNumber min={1} max={8} style={{ width: '100%' }} placeholder="路数" />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'cpu_cores')} label="单颗核心数">
                <InputNumber min={1} style={{ width: '100%' }} placeholder="核心数" />
              </Form.Item>
            </Col>
          </Row>

          {}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={prefixedName(prefix, 'memory_template_id')} label="内存型号">
                <Select
                  placeholder="选择内存模板"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={memoryTemplates.map((t) => ({
                    label: `${t.brand} ${t.model} ${t.spec?.capacity_gb ? `${t.spec.capacity_gb}GB` : ''} ${t.spec?.type ?? ''}`,
                    value: t.id
                  }))}
                  onChange={(id: number | undefined) => {
                    const tpl = memoryTemplates.find((t) => t.id === id);
                    if (tpl?.spec) {
                      setFields({ memory: `${tpl.brand} ${tpl.model}` });
                      
                      const dimmCount = getField('memory_dimm_count');
                      if (tpl.spec.capacity_gb && dimmCount) {
                        form.setFieldValue(
                          prefixedName(prefix, 'memory_size_gb'),
                          (tpl.spec.capacity_gb as number) * dimmCount
                        );
                      }
                    } else {
                      setFields({
                        memory: undefined,
                        memory_dimm_count: undefined,
                        memory_size_gb: undefined
                      });
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'memory_dimm_count')} label="内存条数">
                <InputNumber
                  min={1}
                  max={32}
                  style={{ width: '100%' }}
                  placeholder="条数"
                  addonAfter="条"
                  onChange={(n: number | null) => {
                    const id = getField('memory_template_id');
                    const tpl = memoryTemplates.find((t: ComponentTemplate) => t.id === id);
                    if (tpl?.spec?.capacity_gb && n) {
                      form.setFieldValue(
                        prefixedName(prefix, 'memory_size_gb'),
                        (tpl.spec.capacity_gb as number) * n
                      );
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'memory_size_gb')} label="内存总容量">
                <InputNumber
                  min={0}
                  style={{ width: '100%' }}
                  placeholder="GB"
                  addonAfter="GB"
                  disabled
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'os_version')} label="操作系统">
                <Input placeholder="如 CentOS 7.9" />
              </Form.Item>
            </Col>
          </Row>

          {}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={prefixedName(prefix, 'gpu_template_id')} label="显卡型号">
                <Select
                  placeholder="选择显卡模板（可搜索品牌/型号）"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={gpuTemplates.map((t) => ({
                    label: `${t.brand} ${t.model} ${t.spec?.vram_gb ? `${t.spec.vram_gb}GB` : ''} ${t.spec?.gpu_memory_type ?? ''}`,
                    value: t.id
                  }))}
                  onChange={(id: number | undefined) => {
                    const tpl = gpuTemplates.find((t) => t.id === id);
                    if (tpl?.spec) {
                      const updates: Record<string, unknown> = { gpu: `${tpl.brand} ${tpl.model}` };
                      const currentCount = getField('gpu_count');
                      if (!currentCount) {
                        updates.gpu_count = 1;
                      }
                      setFields(updates);
                    } else {
                      setFields({ gpu: undefined, gpu_count: undefined });
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name={prefixedName(prefix, 'gpu_count')} label="显卡数量">
                <InputNumber
                  min={0}
                  max={16}
                  style={{ width: '100%' }}
                  placeholder="0"
                  addonAfter="张"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={prefixedName(prefix, 'gpu')} label="显卡描述">
                <Input placeholder="如 NVIDIA A100 80GB × 8" />
              </Form.Item>
            </Col>
          </Row>

          {}
          {showIpmi && (
            <Row gutter={16}>
              {showIpmiAddress && (
                <Col span={8}>
                  <Form.Item name={prefixedName(prefix, 'ipmi_address')} label="IPMI地址">
                    <Input placeholder="IPMI管理地址" />
                  </Form.Item>
                </Col>
              )}
              <Col span={8}>
                <Form.Item name={prefixedName(prefix, 'ipmi_username')} label="IPMI用户名">
                  <Input placeholder="IPMI登录用户名" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name={prefixedName(prefix, 'ipmi_password')} label="IPMI密码">
                  <Input.Password placeholder="IPMI登录密码" />
                </Form.Item>
              </Col>
            </Row>
          )}
        </>
      )}

      {}
      <div style={{ marginBottom: 8 }}>
        <div style={{ marginBottom: 4, fontWeight: 500, fontSize: 14 }}>存储配置</div>
        <Form.List
          name={prefix ? [prefix, storageListName] : storageListName}
          initialValue={[{ count: 1, template_id: undefined }]}
        >
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => (
                <Space key={key} style={{ display: 'flex', marginBottom: 4 }} align="baseline">
                  <Form.Item
                    {...restField}
                    name={[name, 'template_id']}
                    label={name === 0 ? '硬盘型号' : ''}
                  >
                    <Select
                      placeholder="选择硬盘模板"
                      allowClear
                      showSearch
                      style={{ width: 220 }}
                      optionFilterProp="label"
                      options={diskTemplates.map((t) => ({
                        label: `${t.brand} ${t.model} ${t.spec?.capacity_gb ? `${t.spec.capacity_gb}GB` : ''} ${t.spec?.interface_type ?? ''}`,
                        value: t.id
                      }))}
                      onChange={(id: number | undefined) => {
                        const tpl = diskTemplates.find((t) => t.id === id);
                        if (tpl?.spec) {
                          const listName = prefix ? [prefix, storageListName] : storageListName;
                          form.setFieldValue(
                            [listName, name, 'storage_type'],
                            (tpl.spec.type as string) ?? (tpl.spec.storage_type as string) ?? ''
                          );
                          form.setFieldValue(
                            [listName, name, 'capacity'],
                            formatCapacity(tpl.spec.capacity_gb as number)
                          );
                          form.setFieldValue(
                            [listName, name, 'interface_type'],
                            (tpl.spec.interface_type as string) ??
                              (tpl.spec.interface as string) ??
                              ''
                          );
                        }
                      }}
                    />
                  </Form.Item>
                  <Form.Item {...restField} name={[name, 'count']} label={name === 0 ? '数量' : ''}>
                    <InputNumber
                      min={1}
                      max={128}
                      placeholder="1"
                      style={{ width: 72 }}
                      addonAfter="块"
                    />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'capacity']}
                    label={name === 0 ? '容量' : ''}
                  >
                    <Input placeholder="480GB" style={{ width: 100 }} />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'storage_type']}
                    label={name === 0 ? '类型' : ''}
                  >
                    <Select
                      style={{ width: 90 }}
                      options={[
                        { label: 'SSD', value: 'SSD' },
                        { label: 'HDD', value: 'HDD' },
                        { label: 'NVMe', value: 'NVMe' }
                      ]}
                    />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'interface_type']}
                    label={name === 0 ? '接口' : ''}
                  >
                    <Select
                      style={{ width: 90 }}
                      allowClear
                      placeholder="可选"
                      options={[
                        { label: 'SATA', value: 'SATA' },
                        { label: 'SAS', value: 'SAS' },
                        { label: 'NVMe', value: 'NVMe' }
                      ]}
                    />
                  </Form.Item>
                  {fields.length > 1 && (
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ color: '#ff4d4f' }}
                    />
                  )}
                </Space>
              ))}
              <Button
                type="dashed"
                onClick={() => add({ count: 1 })}
                icon={<PlusOutlined />}
                size="small"
              >
                添加硬盘
              </Button>
            </>
          )}
        </Form.List>
      </div>
    </>
  );
}


export function buildStorageSummary(items?: StorageItem[]): string {
  if (!items?.length) return '';
  return items
    .filter((it) => it.capacity || it.template_id)
    .map(
      (it) =>
        `${it.count ?? 1}×${it.capacity || '(模板默认)'} ${it.storage_type || ''}${it.interface_type ? ' ' + it.interface_type : ''}`
    )
    .join(' + ');
}


export function buildStorageList(
  items?: StorageItem[]
): { template_id?: number; storage_type: string; capacity: string; interface_type?: string }[] {
  if (!items?.length) return [];
  const list: {
    template_id?: number;
    storage_type: string;
    capacity: string;
    interface_type?: string;
  }[] = [];
  for (const it of items) {
    
    if (!it.template_id && (!it.capacity || !it.storage_type)) continue;
    if (!it.capacity && !it.storage_type && !it.template_id) continue;
    const count = it.count ?? 1;
    for (let i = 0; i < count; i++) {
      list.push({
        template_id: it.template_id,
        storage_type: it.storage_type ?? '',
        capacity: it.capacity ?? '',
        interface_type: it.interface_type || undefined
      });
    }
  }
  return list;
}
