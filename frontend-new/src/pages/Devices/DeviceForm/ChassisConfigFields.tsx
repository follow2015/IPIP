/**
 * ChassisConfigFields — 设备「机箱节点配置」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。包含节点行列数/总节点数/命名规则，以及
 * 「生成子节点」勾选后内嵌的批量硬件/网卡配置（复用共用组件）。
 * 需要 form 实例用于 node_rows/node_cols 的联动计算。
 */
import { Form, Input, InputNumber, Row, Col, Divider, Checkbox, Alert } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('device');
  return (
    <>
      <Divider plain>{t('form.section.chassis')}</Divider>
      <Row gutter={16}>
        <Col xs={12} md={6}>
          <Form.Item
            name="node_rows"
            label={t('form.chassis.rows.label')}
            rules={[{ required: true, message: t('form.chassis.rows.required') }]}
          >
            <InputNumber
              min={1}
              max={16}
              style={{ width: '100%' }}
              placeholder={t('form.chassis.rows.placeholder')}
              onChange={() => {
                const rows = form.getFieldValue('node_rows');
                const cols = form.getFieldValue('node_cols');
                if (rows && cols) form.setFieldsValue({ total_nodes: rows * cols });
              }}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item
            name="node_cols"
            label={t('form.chassis.cols.label')}
            rules={[{ required: true, message: t('form.chassis.cols.required') }]}
          >
            <InputNumber
              min={1}
              max={16}
              style={{ width: '100%' }}
              placeholder={t('form.chassis.cols.placeholder')}
              onChange={() => {
                const rows = form.getFieldValue('node_rows');
                const cols = form.getFieldValue('node_cols');
                if (rows && cols) form.setFieldsValue({ total_nodes: rows * cols });
              }}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item name="total_nodes" label={t('form.chassis.totalNodes.label')}>
            <InputNumber
              min={1}
              max={256}
              style={{ width: '100%' }}
              disabled
              placeholder={t('form.chassis.totalNodes.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item name="node_naming_pattern" label={t('form.chassis.namingPattern.label')}>
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
            {t('form.chassis.generateNodes.label', {
              suffix: isEdit ? t('form.chassis.generateNodes.overwriteSuffix') : ''
            })}
          </Checkbox>
          {generateNodes && (
            <Alert
              type={isEdit ? 'warning' : 'info'}
              title={
                isEdit
                  ? t('form.chassis.generateNodes.alertOverwrite')
                  : t('form.chassis.generateNodes.alertCreate')
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
