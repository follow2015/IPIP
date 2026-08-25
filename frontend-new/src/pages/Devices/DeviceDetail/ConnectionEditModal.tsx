/**
 * ConnectionEditModal — 编辑连接表单 Modal
 *
 * 从 ConnectionTab.tsx 拆出。复用父级 editForm 实例（父级负责提交与校验），
 * 根据 editRecord.link_type 条件渲染 N2N 专属字段（VLAN / 带宽 / LAG / 描述）。
 */
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
  const isN2N = editRecord?.link_type === 'network_to_network';

  return (
    <Modal title="编辑连接" open={open} onOk={onOk} onCancel={onCancel} width={600} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="connection_type" label="连接类型">
              <Select placeholder="请选择" options={connectionTypeOptions} allowClear />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="status" label="状态">
              <Select
                placeholder="请选择"
                options={[
                  { label: '活跃', value: 'active' },
                  { label: '不活跃', value: 'inactive' }
                ]}
              />
            </Form.Item>
          </Col>
        </Row>
        {isN2N && (
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="vlan_id" label="VLAN">
                <Select
                  placeholder="选择 VLAN"
                  options={vlanOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="bandwidth" label="带宽">
                <Input placeholder="如 10G" />
              </Form.Item>
            </Col>
          </Row>
        )}
        {isN2N && (
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="lag_group_id" label="LAG 组">
                <Select
                  placeholder="选择 LAG 组"
                  options={lagOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="description" label="描述">
                <Input.TextArea rows={1} />
              </Form.Item>
            </Col>
          </Row>
        )}
        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
