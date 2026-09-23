/**
 * PortGenerationFields — 设备「端口生成」表单区块（Form.List, Card）
 *
 * 从原 DeviceForm.tsx 拆出。非网管型网络设备（新建）多组端口模板录入。
 * 复用父级 <Form> 上下文，Form.List 的 add/remove 由渲染 prop 提供，无需 form 实例。
 */
import { Form, InputNumber, Select, Button, Card, Alert, Row, Col } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';

interface PortGenerationFieldsProps {
  portPreview: string[];
}

export default function PortGenerationFields({ portPreview }: PortGenerationFieldsProps) {
  const { t } = useTranslation('device');
  return (
    <Card
      title={t('form.section.portGeneration')}
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
        {t('form.portGeneration.intro')}
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
                <Col xs={12} md={6}>
                  <Form.Item
                    {...restField}
                    name={[name, 'template']}
                    label={t('nic.column.portType')}
                    initialValue="GE"
                    style={{ marginBottom: 0 }}
                  >
                    <Select
                      options={PORT_TYPE_TEMPLATES}
                      placeholder={t('form.portGeneration.template.placeholder')}
                      size="small"
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={3}>
                  <Form.Item
                    {...restField}
                    name={[name, 'slot']}
                    label={t('form.portGeneration.slot.label')}
                    initialValue={0}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col xs={12} md={3}>
                  <Form.Item
                    {...restField}
                    name={[name, 'card']}
                    label={t('form.portGeneration.card.label')}
                    initialValue={0}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={99} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item
                    {...restField}
                    name={[name, 'start']}
                    label={t('form.portGeneration.start.label')}
                    initialValue={1}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item
                    {...restField}
                    name={[name, 'end']}
                    label={t('form.portGeneration.end.label')}
                    initialValue={24}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0} max={9999} style={{ width: '100%' }} size="small" />
                  </Form.Item>
                </Col>
                <Col xs={12} md={3} style={{ textAlign: 'right', paddingTop: 22 }}>
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
              {t('form.portGeneration.addGroup')}
            </Button>
          </>
        )}
      </Form.List>
      {portPreview.length > 0 && (
        <Alert
          type="info"
          title={t('form.portGeneration.preview', {
            count: portPreview.length,
            list: portPreview.slice(0, 5).join(', '),
            ellipsis: portPreview.length > 5 ? ' ...' : ''
          })}
          style={{ marginBottom: 8 }}
          showIcon
        />
      )}
    </Card>
  );
}
