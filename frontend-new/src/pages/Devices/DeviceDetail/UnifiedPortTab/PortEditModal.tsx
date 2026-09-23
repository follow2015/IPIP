/**
 * PortEditModal — 编辑端口弹窗（非网管模式）
 * 自包含：内部填充表单（兼容网管/非网管两套字段名）+ 提交更新
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Form, Input, Select, Row, Col } from 'antd';
import type { SwitchPort } from '@/types/models';
import { useUpdateNetworkPort } from '@/services/network-port';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';
import { getUsageStatusFormOptions } from './constants';

interface PortEditModalProps {
  deviceId: number;
  port: SwitchPort | null;
  onClose: () => void;
}

export function PortEditModal({ deviceId, port, onClose }: PortEditModalProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const [editForm] = Form.useForm();
  const updatePort = useUpdateNetworkPort(deviceId);
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const usageStatusOptions = getUsageStatusFormOptions(t);

  useEffect(() => {
    if (!port) return;
    const macValue = port.mac ?? '';
    editForm.setFieldsValue({
      port_name: port.port_name,
      port_type: port.port_type ?? '',
      speed: port.speed ?? '',
      usage_status: port.usage_status ?? 'free',
      description: port.description ?? '',
      vlan: port.vlan ?? '',
      mac: macValue,
      ip_address: port.ip_address ?? '',
      customer_id: port.customer_id ?? null
    });
  }, [port, editForm]);

  const handleEditSubmit = async () => {
    if (!port) return;
    try {
      const values = await editForm.validateFields();

      const { port_name, port_type, ...updateData } = values;
      await updatePort.mutateAsync({ portId: port.id, data: updateData });
      message.success(t('port.message.updated'));
      onClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal
      title={t('nic.editTitle')}
      open={!!port}
      onOk={handleEditSubmit}
      onCancel={onClose}
      destroyOnHidden
      width={600}
    >
      <Form form={editForm} layout="vertical">
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="port_name" label={t('nic.column.portName')}>
              <Input disabled />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="port_type" label={t('nic.column.portType')}>
              <Input disabled />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="speed" label={t('nic.column.speed')}>
              <Input placeholder={t('port.field.speedHintMulti')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="usage_status" label={t('port.column.usageStatus')}>
              <Select options={usageStatusOptions} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="vlan" label={t('connection.column.vlan')}>
              <Input placeholder={t('port.field.vlanHint')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="customer_id" label={tCommon('field.customer')}>
              <Select
                allowClear
                showSearch
                placeholder={t('port.field.selectCustomer')}
                options={customerOptions ?? []}
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="mac" label={t('form.network.macAddress.label')}>
              <Input placeholder={t('port.field.macHint')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="ip_address" label={t('port.column.ipAddress')}>
              <Input placeholder={t('port.field.ipHint')} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label={tCommon('field.remarks')}>
          <Input placeholder={t('port.field.remarksHint')} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
