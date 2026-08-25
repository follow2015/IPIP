/**
 * PortEditModal — 编辑端口弹窗（非网管模式）
 * 自包含：内部填充表单（兼容网管/非网管两套字段名）+ 提交更新
 */
import { useEffect } from 'react';
import { Modal, Form, Input, Select, Row, Col } from 'antd';
import type { SwitchPort } from '@/types/models';
import { useUpdateNetworkPort } from '@/services/network-port';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useMessage } from '@/hooks/useMessage';
import { USAGE_STATUS_FORM_OPTIONS } from './constants';

interface PortEditModalProps {
  deviceId: number;
  port: SwitchPort | null;
  onClose: () => void;
}

export function PortEditModal({ deviceId, port, onClose }: PortEditModalProps) {
  const message = useMessage();
  const [editForm] = Form.useForm();
  const updatePort = useUpdateNetworkPort(deviceId);
  const { data: customerOptions } = useAllocatableCustomerOptions();

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
      message.success('端口更新成功');
      onClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal
      title="编辑端口"
      open={!!port}
      onOk={handleEditSubmit}
      onCancel={onClose}
      destroyOnHidden
      width={600}
    >
      <Form form={editForm} layout="vertical">
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="port_name" label="端口名称">
              <Input disabled />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="port_type" label="端口类型">
              <Input disabled />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="speed" label="速率">
              <Input placeholder="如 1G、10G" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="usage_status" label="占用状态">
              <Select options={USAGE_STATUS_FORM_OPTIONS} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="vlan" label="VLAN">
              <Input placeholder="如 100" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="customer_id" label="客户">
              <Select
                allowClear
                showSearch
                placeholder="选择客户"
                options={customerOptions ?? []}
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="mac" label="MAC地址">
              <Input placeholder="如 00:1A:2B:3C:4D:5E" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="ip_address" label="IP地址">
              <Input placeholder="如 192.168.1.1" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label="备注">
          <Input placeholder="端口备注" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
