/**
 * PortGenerationFields — 设备「端口生成」表单区块（Form.List, Card）
 *
 * 从原 DeviceForm.tsx 拆出。非网管型网络设备（新建）多组端口模板录入。
 * 复用父级 <Form> 上下文，Form.List 的 add/remove 由渲染 prop 提供，无需 form 实例。
 */
import { Form, InputNumber, Select, Button, Card, Alert, Row, Col } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';

interface PortGenerationFieldsProps {
  portPreview: string[];
}

export default function PortGenerationFields({ portPreview }: PortGenerationFieldsProps) {
  return (
    <Card
      title="端口生成"
      size="small"
      style={{ marginBottom: 16 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <div
        style={{
          marginBottom: 8,
          padding: '6px 12px',
          background: '#fafafa',
          borderRadius: 6,
          fontSize: 12,
          lineHeight: 1.8,
          color: '#595959'
        }}
      >
        支持多组端口，如 48口GE + 4口10GE。命名规则：前缀 + 槽位/卡号/端口号
      </div>
      <Form.List
        name="port_groups"
        initialValue={[{ template: 'GE', slot: 0, card: 0, start: 1, end: 24 }]}
      >
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key, name, ...restField }) => (
              <Row
                key={key}
                gutter={8}
                align="top"
                style={{
                  marginBottom: 8,
                  padding: '8px 0',
                  borderBottom: '1px dashed #f0f0f0'
                }}
              >
                <Col span={6}>
                  <Form.Item
                    {...restField}
                    name={[name, 'template']}
                    label="端口类型"
                    initialValue="GE"
                    style={{ marginBottom: 0 }}
                  >
                    <Select options={PORT_TYPE_TEMPLATES} placeholder="选择类型" size="small" />
                  </Form.Item>
                </Col>
                <Col span={3}>
                  <Form.Item
                    {...restField}
                    name={[name, 'slot']}
                    label="槽位"
                    initialValue={0}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col span={3}>
                  <Form.Item
                    {...restField}
                    name={[name, 'card']}
                    label="卡号"
                    initialValue={0}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col span={4}>
                  <Form.Item
                    {...restField}
                    name={[name, 'start']}
                    label="起始"
                    initialValue={1}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col span={4}>
                  <Form.Item
                    {...restField}
                    name={[name, 'end']}
                    label="结束"
                    initialValue={24}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col span={3} style={{ textAlign: 'right', paddingTop: 22 }}>
                  {fields.length > 1 && (
                    <Button
                      type="text"
                      danger
                      icon={<MinusCircleOutlined />}
                      onClick={() => remove(name)}
                      size="small"
                    />
                  )}
                </Col>
              </Row>
            ))}
            <Button
              type="dashed"
              onClick={() => add({ template: 'GE', slot: 0, card: 0, start: 1, end: 24 })}
              icon={<PlusOutlined />}
              size="small"
              style={{ marginBottom: 8 }}
            >
              添加端口组
            </Button>
          </>
        )}
      </Form.List>
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
}
