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
import { useTranslation } from 'react-i18next';
import { useMemo } from 'react';
import i18next from '@/i18n';
import { useComponentTemplates } from '@/services/component-template';
import type { ComponentTemplate } from '@/services/component-template';

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
  showPreview = true
}: NicConfigFieldsProps) {
  const { t } = useTranslation('device');
  const { data: nicTemplates = [], isLoading: nicTplLoading } = useComponentTemplates(
    'nic',
    customerId
  );

  const nicPortsValue = Form.useWatch(prefix ? [prefix, listName] : listName, form);

  const portPreview = useMemo(() => {
    if (!nicPortsValue || !Array.isArray(nicPortsValue)) return [];
    const result: {
      nic_number: number;
      port_number: number;
      port_type: string;
      port_speed: string;
      nic_name: string;
      port_name: string;
      description: string;
    }[] = [];
    let nicNum = 1;
    for (const item of nicPortsValue) {
      if (!item?.template_id) {
        nicNum++;
        continue;
      }
      const tpl = nicTemplates.find((t: ComponentTemplate) => t.id === item.template_id);
      if (!tpl?.spec) {
        nicNum++;
        continue;
      }
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
          nic_name: model
            ? t('nic.autoPortName', { model, index: i + 1 })
            : t('nic.autoNicName', { index: nicNum }),
          port_name: `port${i + 1}`,
          description: combinedDesc
        });
      }
      nicNum++;
    }
    return result;
  }, [nicPortsValue, nicTemplates, t]);

  return (
    <>
      <Divider plain>{t('node.field.nic')}</Divider>
      <Form.List name={prefix ? [prefix, listName] : listName} initialValue={[{}]}>
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key, name, ...restField }, idx) => (
              <Row key={key} gutter={8} align="middle" style={{ marginBottom: 8 }}>
                <Col xs={20} md={14}>
                  <Form.Item
                    {...restField}
                    name={[name, 'template_id']}
                    label={t('nic.itemLabel', { index: idx + 1 })}
                  >
                    <Select
                      allowClear
                      showSearch
                      loading={nicTplLoading}
                      placeholder={t('nic.templatePlaceholder')}
                      optionFilterProp="label"
                      options={nicTemplates.map((template) => ({
                        label: t('nic.templateOption', {
                          brand: template.brand,
                          model: template.model,
                          ports: template.spec?.port_count ?? '?',
                          speed: template.spec?.port_speed ?? '?',
                          type: template.spec?.port_type ?? ''
                        }),
                        value: template.id
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={4} md={2}>
                  {fields.length > 1 && (
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ color: '#ff4d4f' }}
                    />
                  )}
                </Col>
              </Row>
            ))}
            <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />} size="small">
              {t('nic.add')}
            </Button>
          </>
        )}
      </Form.List>

      {/* 端口预览 */}
      {showPreview && portPreview.length > 0 && (
        <Alert
          type="info"
          message={t('nic.preview.summary', {
            count: portPreview.length,
            nics: new Set(portPreview.map((p) => p.nic_number)).size
          })}
          description={
            <div style={{ marginTop: 4 }}>
              {portPreview.map((p, i) => (
                <Tag key={i} style={{ marginBottom: 4 }}>
                  {p.nic_name} {p.port_type} {p.port_speed}
                  {p.description ? ` (${p.description})` : ''}
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

/**
 * 从 Form.List 的 nic_ports 值展开为后端需要的端口列表
 * 供提交时使用，替代 AddDevicesModal 中硬编码的 expandNicTemplates
 *
 * nic_name 格式: {model}:端口{N}（如 X710-DA2:端口1）
 * port_name 格式: port{N}（如 port1，留给客户自定义）
 * description 取自 remark + spec.form_factor 合并（如 "双口网卡 PCIe"）
 */
export function expandNicPorts(
  nicPortsFormVal: { template_id?: number }[] | undefined,
  nicTemplates: ComponentTemplate[]
): ExpandedNicPort[] {
  if (!nicPortsFormVal || nicPortsFormVal.length === 0) return [];
  const result: ExpandedNicPort[] = [];
  let nicNum = 1;
  for (const nicItem of nicPortsFormVal) {
    if (!nicItem.template_id) {
      nicNum++;
      continue;
    }
    const tpl = nicTemplates.find((t) => t.id === nicItem.template_id);
    if (!tpl?.spec) {
      nicNum++;
      continue;
    }
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
        nic_name: model
          ? i18next.t('nic.autoPortName', { ns: 'device', model, index: i + 1 })
          : i18next.t('nic.autoNicName', { ns: 'device', index: nicNum }),
        port_name: `port${i + 1}`,
        description: combinedDesc
      });
    }
    nicNum++;
  }
  return result;
}
