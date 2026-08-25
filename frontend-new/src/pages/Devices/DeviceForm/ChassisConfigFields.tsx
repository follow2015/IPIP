/**
 * ChassisConfigFields — 设备「机箱节点配置」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。包含节点行列数/总节点数/命名规则，以及
 * 「生成子节点」勾选后内嵌的批量硬件/网卡配置（复用共用组件）。
 * 需要 form 实例用于 node_rows/node_cols 的联动计算。
 */
import { Form, Input, InputNumber, Row, Col, Divider, Checkbox, Alert } from 'antd';
import type { FormInstance } from 'antd';
import HardwareConfigFields from '@/components/HardwareConfigFields';
import NicConfigFields from '@/components/NicConfigFields';

interface ChassisConfigFieldsProps {
  form: FormInstance;
  customerId: number | undefined;
  generateNodes: boolean;
  onGenerateNodesChange: (checked: boolean) => void;
  isEdit: boolean;
}

export default function ChassisConfigFields({
  form,
  customerId,
  generateNodes,
  onGenerateNodesChange,
  isEdit
}: ChassisConfigFieldsProps) {
  return (
    <>
      <Divider plain>机箱节点配置</Divider>
      <Row gutter={16}>
        <Col span={6}>
          <Form.Item
            name="node_rows"
            label="节点行数"
            rules={[{ required: true, message: '请输入行数' }]}
          >
            <InputNumber
              min={1}
              max={16}
              style={{ width: '100%' }}
              placeholder="行数"
              onChange={() => {
                const rows = form.getFieldValue('node_rows');
                const cols = form.getFieldValue('node_cols');
                if (rows && cols) form.setFieldsValue({ total_nodes: rows * cols });
              }}
            />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item
            name="node_cols"
            label="节点列数"
            rules={[{ required: true, message: '请输入列数' }]}
          >
            <InputNumber
              min={1}
              max={16}
              style={{ width: '100%' }}
              placeholder="列数"
              onChange={() => {
                const rows = form.getFieldValue('node_rows');
                const cols = form.getFieldValue('node_cols');
                if (rows && cols) form.setFieldsValue({ total_nodes: rows * cols });
              }}
            />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="total_nodes" label="总节点数">
            <InputNumber
              min={1}
              max={256}
              style={{ width: '100%' }}
              disabled
              placeholder="自动计算"
            />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="node_naming_pattern" label="命名规则">
            <Input placeholder="{NAME}-Node{POS}" />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={24}>
          <Checkbox
            checked={generateNodes}
            onChange={(e) => onGenerateNodesChange(e.target.checked)}
          >
            生成子节点（保存时自动按行×列规格生成所有子节点
            {isEdit ? '，已有子节点将被覆盖' : ''}）
          </Checkbox>
          {generateNodes && (
            <Alert
              type={isEdit ? 'warning' : 'info'}
              title={
                isEdit
                  ? '保存时将删除已有子节点并重新生成所有子节点，使用下方硬件配置统一设置'
                  : '保存时将自动创建所有子节点，并使用下方硬件配置统一设置所有子节点硬件信息'
              }
              style={{ marginTop: 8 }}
              showIcon
            />
          )}
        </Col>
      </Row>
      {/* 勾选生成子节点后，显示硬件配置用于批量设置 */}
      {generateNodes && <HardwareConfigFields form={form} customerId={customerId} showIpmi />}
      {/* 勾选生成子节点后，显示网卡配置区域 */}
      {generateNodes && <NicConfigFields form={form} customerId={customerId} />}
    </>
  );
}
