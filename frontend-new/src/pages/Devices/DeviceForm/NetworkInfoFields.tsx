/**
 * NetworkInfoFields — 设备「网络信息」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。纯表单字段区块，复用父级 <Form> 上下文，
 * 不持有 form 实例，可独立复用与测试。
 */
import { Form, Input, Divider, Row, Col, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
import { parseIPAddressString, type ParsedIPEntry } from '@/utils/ip';

interface NetworkInfoFieldsProps {
  isNetwork: boolean;
}

export default function NetworkInfoFields({ isNetwork }: NetworkInfoFieldsProps) {
  const { t } = useTranslation('device');
  return (
    <>
      {/* ── 网络信息区块 ── */}
      <Divider plain>{t('form.section.network')}</Divider>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item name="management_ip" label={t('field.managementIp')}>
            <Input placeholder={t('form.network.managementIp.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name="mac_address" label={t('form.network.macAddress.label')}>
            <Input placeholder={t('form.network.macAddress.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name="ip_address"
            label={t('basic.field.businessIp')}
            tooltip={t('form.network.businessIp.tooltip')}
            rules={[
              {
                validator: (_: unknown, value: string) => {
                  if (!value) return Promise.resolve();
                  const entries = parseIPAddressString(value);
                  const invalid = entries.filter((e: ParsedIPEntry) => !e.valid);
                  if (invalid.length > 0) {
                    return Promise.reject(
                      new Error(
                        t('form.network.businessIp.formatError', {
                          list: invalid.map((e: ParsedIPEntry) => e.raw).join(', ')
                        })
                      )
                    );
                  }
                  return Promise.resolve();
                }
              }
            ]}
          >
            <Input.TextArea
              placeholder="192.168.1.2,192.168.1.4-10,192.168.1.0/24"
              autoSize={{ minRows: 1, maxRows: 4 }}
            />
          </Form.Item>
        </Col>
      </Row>
      {/* 管理权限开关（仅网络设备显示） */}
      {isNetwork && (
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item
              name={['switch_config', 'has_ssh']}
              label={t('form.network.managementAccess.label')}
              valuePropName="checked"
            >
              <Switch
                checkedChildren={t('form.network.managementAccess.on')}
                unCheckedChildren={t('form.network.managementAccess.off')}
              />
            </Form.Item>
          </Col>
        </Row>
      )}
    </>
  );
}
