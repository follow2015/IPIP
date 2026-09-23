/**
 * ConnectionEditModal — 编辑连接表单 Modal
 *
 * 从 ConnectionTab.tsx 拆出。复用父级 editForm 实例（父级负责提交与校验），
 * 根据 editRecord.link_type 条件渲染 N2N 专属字段（VLAN / 带宽 / LAG / 描述）。
 */
import { useTranslation } from 'react-i18next';
import { Form, Modal, Select, Input, Row, Col } from 'antd';
import type { FormInstance, SelectProps } from 'antd';
import type { DeviceConnection } from '@/types/models';
import type { PortLink } from '@/services/device-connection';

interface ConnectionEditModalProps {
  open: boolean;
  onOk: () => void;
  onCancel: () => void;
  form: FormInstance;
  editRecord: DeviceConnection | PortLink | null;
  connectionTypeOptions: SelectProps['options'];
  vlanOptions?: SelectProps['options'];
  lagOptions?: SelectProps['options'];
}

export default function ConnectionEditModal({
  open,
  onOk,
  onCancel,
  form,
  editRecord,
  connectionTypeOptions,
  vlanOptions,
  lagOptions
}: ConnectionEditModalProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const isN2N = editRecord?.link_type === 'network_to_network';

  return (
    <Modal
      title={t('connection.editTitle')}
      open={open}
      onOk={onOk}
      onCancel={onCancel}
      width={600}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="connection_type" label={t('connection.column.connectionType')}>
              <Select
                placeholder={tCommon('message.selectRequired')}
                options={connectionTypeOptions}
                allowClear
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="status" label={tCommon('field.status')}>
              <Select
                placeholder={tCommon('message.selectRequired')}
                options={[
                  { label: t('connectionStatus.ACTIVE'), value: 'active' },
                  { label: t('connectionStatus.INACTIVE'), value: 'inactive' }
                ]}
              />
            </Form.Item>
          </Col>
        </Row>
        {isN2N && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="vlan_id" label={t('connection.column.vlan')}>
                <Select
                  placeholder={t('connection.form.selectVlan')}
                  options={vlanOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="bandwidth" label={t('connection.column.bandwidth')}>
                <Input placeholder={t('connection.form.bandwidthHint')} />
              </Form.Item>
            </Col>
          </Row>
        )}
        {isN2N && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="lag_group_id" label={t('connection.column.lagGroup')}>
                <Select
                  placeholder={t('connection.form.selectLagGroup')}
                  options={lagOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="description" label={tCommon('field.description')}>
                <Input.TextArea rows={1} />
              </Form.Item>
            </Col>
          </Row>
        )}
        <Form.Item name="notes" label={tCommon('field.remarks')}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
