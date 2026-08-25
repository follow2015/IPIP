/**
 * NetworkInfoFields — 设备「网络信息」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。纯表单字段区块，复用父级 <Form> 上下文，
 * 不持有 form 实例，可独立复用与测试。
 */
import { Form, Input, Divider, Row, Col, Switch } from 'antd';
import { parseIPAddressString, type ParsedIPEntry } from '@/utils/ip';

interface NetworkInfoFieldsProps {
  isNetwork: boolean;
}

export default function NetworkInfoFields({ isNetwork }: NetworkInfoFieldsProps) {
  return (
    <>
      {/* ── 网络信息区块 ── */}
      <Divider plain>网络信息</Divider>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="management_ip" label="管理IP">
            <Input placeholder="管理IP地址" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="mac_address" label="MAC地址">
            <Input placeholder="MAC地址" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name="ip_address"
            label="业务IP"
            tooltip="支持多种格式：单个IP、逗号分隔、CIDR、子网掩码、范围"
            rules={[
              {
                validator: (_: unknown, value: string) => {
                  if (!value) return Promise.resolve();
                  const entries = parseIPAddressString(value);
                  const invalid = entries.filter((e: ParsedIPEntry) => !e.valid);
                  if (invalid.length > 0) {
                    return Promise.reject(
                      new Error(`格式错误: ${invalid.map((e: ParsedIPEntry) => e.raw).join(', ')}`)
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
          <Col span={8}>
            <Form.Item name={['switch_config', 'has_ssh']} label="管理权限" valuePropName="checked">
              <Switch checkedChildren="开" unCheckedChildren="关" />
            </Form.Item>
          </Col>
        </Row>
      )}
    </>
  );
}
