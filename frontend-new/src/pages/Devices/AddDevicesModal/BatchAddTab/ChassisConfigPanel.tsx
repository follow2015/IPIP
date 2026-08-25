/**
 * ChassisConfigPanel — 机箱模式的子节点配置区
 *
 * 节点行×列 / 命名规则 / 「生成子节点」开关；勾选生成子节点后展开硬件与网卡配置。
 * 内部用 Form.useWatch 监听 auto_create_nodes，避免从组合根透传派生态。
 */

import React from 'react';
import { Form, Card, Row, Col, Input, InputNumber, Checkbox } from 'antd';
import HardwareConfigFields from '@/components/HardwareConfigFields';
import NicConfigFields from '@/components/NicConfigFields';

interface ChassisConfigPanelProps {
  form: ReturnType<typeof Form.useForm>[0];
}

const ChassisConfigPanel: React.FC<ChassisConfigPanelProps> = ({ form }) => {
  const autoCreate = Form.useWatch('auto_create_nodes', form);

  return (
    <Card
      title="机箱子节点配置"
      size="small"
      style={{ marginBottom: 12 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <Row gutter={16}>
        <Col span={6}>
          <Form.Item name="node_rows" label="节点行数" initialValue={2}>
            <InputNumber min={1} max={16} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="node_cols" label="节点列数" initialValue={2}>
            <InputNumber min={1} max={16} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="node_naming_pattern" label="命名规则">
            <Input placeholder="{NAME}-Node{POS}" />
          </Form.Item>
        </Col>
      </Row>
      <Form.Item
        name="auto_create_nodes"
        label="生成子节点"
        valuePropName="checked"
        initialValue={true}
      >
        <Checkbox>创建时自动按行×列规格生成所有子节点</Checkbox>
      </Form.Item>
      {/* 勾选生成子节点后，显示硬件配置和网卡配置 */}
      {autoCreate !== false && (
        <>
          <HardwareConfigFields form={form} />
          <NicConfigFields form={form} />
        </>
      )}
    </Card>
  );
};

export default ChassisConfigPanel;
