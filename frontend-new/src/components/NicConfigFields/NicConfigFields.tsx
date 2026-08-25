/**
 * 网卡配置共用组件
 *
 * 【智能组件】内部通过 useComponentTemplates 获取网卡模板数据，
 * 调用方仅需传入 customerId 即可，无需自行获取模板列表。
 *
 * 统一设备新增（DeviceForm）和批量创建（AddDevicesModal）的网卡配置表单，
 * 消除两者在数据源（后端API vs 前端硬编码）和交互方式上的差异。
 *
 * 功能：
 * - Form.List 模式：每行一个网卡模板下拉，可添加多行
 * - 数据源统一为后端 useComponentTemplates('nic', customerId)
 * - 选项显示格式：品牌 型号（端口数×速率 类型）
 * - 可选端口预览
 */
import { Form, Select, Row, Col, Divider, Button, Tag, Alert } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import { useComponentTemplates } from '@/services/component-template';
import type { ComponentTemplate } from '@/services/component-template';
import { useMemo } from 'react';


export interface NicConfigFieldsProps {
  
  form: FormInstance;
  
  customerId?: number | null;
  
  prefix?: string;
  
  listName?: string;
  
  showPreview?: boolean;
}


function prefixedName(prefix: string | undefined, field: string): string | (string | number)[] {
  return prefix ? [prefix, field] : field;
}


export default function NicConfigFields({
  form,
  customerId,
  prefix,
  listName = 'nic_ports',
  showPreview = true,
}: NicConfigFieldsProps) {
  
  const { data: nicTemplates = [], isLoading: nicTplLoading } = useComponentTemplates('nic', customerId);

  
  const nicPortsValue = Form.useWatch(prefix ? [prefix, listName] : listName, form);

  
  const portPreview = useMemo(() => {
    if (!nicPortsValue || !Array.isArray(nicPortsValue)) return [];
    const result: { nic_number: number; port_number: number; port_type: string; port_speed: string; nic_name: string; port_name: string; description: string }[] = [];
    let nicNum = 1;
    for (const item of nicPortsValue) {
      if (!item?.template_id) { nicNum++; continue; }
      const tpl = nicTemplates.find((t: ComponentTemplate) => t.id === item.template_id);
      if (!tpl?.spec) { nicNum++; continue; }
      const portCount = (tpl.spec.port_count as number) ?? 0;
      const portType = (tpl.spec.port_type as string) ?? '';
      const portSpeed = (tpl.spec.port_speed as string) ?? '';
      const model = tpl.model ?? '';
      const formFactor = (tpl.spec.form_factor as string) ?? '';
      const remark = (tpl.remark as string) ?? '';
      
      const combinedDesc = [remark, formFactor].filter(Boolean).join(' ');
      for (let i = 0; i < portCount; i++) {
        result.push({
          nic_number: nicNum, port_number: i + 1, port_type: portType, port_speed: portSpeed,
          nic_name: model ? `${model}:端口${i + 1}` : `网卡${nicNum}`,
          port_name: `port${i + 1}`,
          description: combinedDesc,
        });
      }
      nicNum++;
    }
    return result;
  }, [nicPortsValue, nicTemplates]);

  return (
    <>
      <Divider plain>网卡配置</Divider>
      <Form.List name={prefix ? [prefix, listName] : listName} initialValue={[{}]}>
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key, name, ...restField }, idx) => (
              <Row key={key} gutter={8} align="middle" style={{ marginBottom: 8 }}>
                <Col span={14}>
                  <Form.Item {...restField} name={[name, 'template_id']} label={`网卡 ${idx + 1}`}>
                    <Select
                      allowClear
                      showSearch
                      loading={nicTplLoading}
                      placeholder="选择网卡模板（自动展开端口）"
                      optionFilterProp="label"
                      options={nicTemplates.map(t => ({
                        label: `${t.brand} ${t.model}（${t.spec?.port_count ?? '?'}×${t.spec?.port_speed ?? '?'} ${t.spec?.port_type ?? ''}）`,
                        value: t.id,
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col span={2}>
                  {fields.length > 1 && <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#ff4d4f' }} />}
                </Col>
              </Row>
            ))}
            <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />} size="small">添加网卡</Button>
          </>
        )}
      </Form.List>

      {}
      {showPreview && portPreview.length > 0 && (
        <Alert
          type="info"
          message={`共 ${portPreview.length} 个端口，${new Set(portPreview.map(p => p.nic_number)).size} 块网卡`}
          description={
            <div style={{ marginTop: 4 }}>
              {portPreview.map((p, i) => (
                <Tag key={i} style={{ marginBottom: 4 }}>
                  {p.nic_name} {p.port_type} {p.port_speed}{p.description ? ` (${p.description})` : ''}
                </Tag>
              ))}
            </div>
          }
          style={{ marginBottom: 8, marginTop: 8 }}
          showIcon
        />
      )}
    </>
  );
}


export interface ExpandedNicPort {
  nic_number: number;
  port_number: number;
  port_type: string;
  port_speed: string;
  
  nic_name: string;
  
  port_name: string;
  
  description: string;
}


export function expandNicPorts(
  nicPortsFormVal: { template_id?: number }[] | undefined,
  nicTemplates: ComponentTemplate[],
): ExpandedNicPort[] {
  if (!nicPortsFormVal || nicPortsFormVal.length === 0) return [];
  const result: ExpandedNicPort[] = [];
  let nicNum = 1;
  for (const nicItem of nicPortsFormVal) {
    if (!nicItem.template_id) { nicNum++; continue; }
    const tpl = nicTemplates.find(t => t.id === nicItem.template_id);
    if (!tpl?.spec) { nicNum++; continue; }
    const portCount = (tpl.spec.port_count as number) ?? 0;
    const portType = (tpl.spec.port_type as string) ?? '';
    const portSpeed = (tpl.spec.port_speed as string) ?? '';
    const model = tpl.model ?? '';
    const formFactor = (tpl.spec.form_factor as string) ?? '';
    const remark = (tpl.remark as string) ?? '';
    
    const combinedDesc = [remark, formFactor].filter(Boolean).join(' ');
    for (let i = 0; i < portCount; i++) {
      result.push({
        nic_number: nicNum,
        port_number: i + 1,
        port_type: portType,
        port_speed: portSpeed,
        nic_name: model ? `${model}:端口${i + 1}` : `网卡${nicNum}`,
        port_name: `port${i + 1}`,
        description: combinedDesc,
      });
    }
    nicNum++;
  }
  return result;
}
