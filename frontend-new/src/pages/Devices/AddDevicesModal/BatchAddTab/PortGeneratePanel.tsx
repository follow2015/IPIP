/**
 * PortGeneratePanel — 非网管型网络设备的端口生成区
 *
 * 端口类型 / 槽位 / 卡号 / 起止端口，自定义前缀；实时预览将生成的端口。
 * 内部用 Form.useWatch 监听 port_template（判断是否显示自定义前缀输入框）。
 */

import React from 'react';
import { Form, Card, Row, Col, Input, InputNumber, Select, Alert } from 'antd';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';

interface PortGeneratePanelProps {
  form: ReturnType<typeof Form.useForm>[0];
  portPreview: string[];
}

const PortGeneratePanel: React.FC<PortGeneratePanelProps> = ({ form, portPreview }) => {
  const portTemplate = Form.useWatch('port_template', form);

  return (
    <Card
      title="端口生成"
      size="small"
      style={{ marginBottom: 12 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="port_template" label="端口类型" initialValue="GE">
            <Select options={PORT_TYPE_TEMPLATES} placeholder="选择端口类型" />
          </Form.Item>
        </Col>
        <Col span={4}>
          <Form.Item name="port_slot" label="槽位" initialValue={0}>
            <InputNumber min={0} max={99} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={4}>
          <Form.Item name="port_card" label="卡号" initialValue={0}>
            <InputNumber min={0} max={99} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={4}>
          <Form.Item name="port_start" label="起始端口" initialValue={1}>
            <InputNumber min={1} max={9999} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={4}>
          <Form.Item name="port_end" label="结束端口" initialValue={24}>
            <InputNumber min={1} max={9999} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      {portTemplate === 'custom' && (
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              name="port_custom_prefix"
              label="自定义前缀"
              rules={[{ required: true, message: '请输入前缀' }]}
            >
              <Input placeholder="如 GE" />
            </Form.Item>
          </Col>
        </Row>
      )}
      {portPreview.length > 0 && (
        <Alert
          type="info"
          title={`将生成 ${portPreview.length} 个端口：${portPreview.slice(0, 5).join(', ')}${portPreview.length > 5 ? ' ...' : ''}`}
          style={{ marginBottom: 8 }}
          showIcon
        />
      )}
    </Card>
  );
};

export default PortGeneratePanel;
