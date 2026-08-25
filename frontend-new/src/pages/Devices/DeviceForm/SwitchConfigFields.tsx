/**
 * SwitchConfigFields — 设备「交换机配置」表单区块（Card）
 *
 * 从原 DeviceForm.tsx 拆出。纯表单字段区块，复用父级 <Form> 上下文。
 * 仅网络设备且开启管理权限（has_ssh）时由父级条件渲染。
 */
import { Form, Input, InputNumber, Select, Card, Row, Col } from 'antd';
import { SWITCH_DEVICE_TYPE_OPTIONS, SSH_PROTOCOL_OPTIONS } from '@/types/enums';

interface SwitchConfigFieldsProps {
  
  isEdit: boolean;
}

export default function SwitchConfigFields({ isEdit }: SwitchConfigFieldsProps) {
  return (
    <Card
      title="交换机配置"
      size="small"
      style={{ marginBottom: 16 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name={['switch_config', 'ip']} label="管理IP">
            <Input placeholder="管理IP" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name={['switch_config', 'port']} label="SSH端口" initialValue={22}>
            <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="默认22" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name={['switch_config', 'protocol']} label="协议" initialValue="ssh">
            <Select placeholder="请选择" options={SSH_PROTOCOL_OPTIONS} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name={['switch_config', 'username']} label="用户名">
            <Input placeholder="登录用户名" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name={['switch_config', 'password']}
            label="密码"
            extra={isEdit ? '留空则不修改' : undefined}
          >
            <Input.Password placeholder={isEdit ? '留空则不修改' : '登录密码'} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name={['switch_config', 'authentication_method']}
            label="认证方法"
            initialValue="password"
          >
            <Select
              placeholder="请选择"
              options={[
                { label: '密码', value: 'password' },
                { label: '证书', value: 'certificate' }
              ]}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name={['switch_config', 'device_type']} label="设备驱动">
            <Select placeholder="请选择" allowClear options={SWITCH_DEVICE_TYPE_OPTIONS} />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );
}
