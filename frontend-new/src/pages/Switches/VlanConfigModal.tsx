import { useEffect } from 'react';
import { Modal, Form, InputNumber, Input, Select } from 'antd';

export interface VlanConfigValues {
  vlan_id: number;
  mode: 'access' | 'trunk';
  allowed_vlans?: string;
}

interface VlanConfigModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  portType: string;
  initialVlanId?: number;
  onSubmit: (values: VlanConfigValues) => void;
}

export function VlanConfigModal({
  open,
  onClose,
  portName,
  portType,
  initialVlanId,
  onSubmit
}: VlanConfigModalProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ vlan_id: initialVlanId ?? undefined, mode: 'access' });
    }
  }, [open, initialVlanId, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({
        vlan_id: Number(values.vlan_id),
        mode: values.mode as 'access' | 'trunk',
        allowed_vlans: values.allowed_vlans as string | undefined
      });
    } catch {
    }
  };

  return (
    <Modal
      title={`配置 VLAN — ${portName}`}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnHidden
    >
      <div
        style={{
          marginBottom: 12,
          padding: 8,
          background: '#fff2f0',
          borderRadius: 4,
          fontSize: 12,
          color: '#cf1322',
          lineHeight: 1.8,
          border: '1px solid #ffccc7'
        }}
      >
        <div>
          <b>⚠ 注意：</b>此操作将清空端口现有配置，并导致端口 up/down 一次。
        </div>
      </div>
      <div
        style={{
          marginBottom: 12,
          padding: 8,
          background: '#f6f8fa',
          borderRadius: 4,
          fontSize: 12,
          color: '#666',
          lineHeight: 1.8
        }}
      >
        <div>若输入的 VLAN ID 在交换机上不存在，系统将自动创建该 VLAN。</div>
        <div>Access 模式适合终端设备接入，Trunk 模式适合交换机互连。</div>
        <div>Trunk 模式下，允许 VLAN 列表中的所有 VLAN 也会被自动创建。</div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.mode !== cur.mode}>
          {({ getFieldValue }) => (
            <Form.Item
              name="vlan_id"
              label={
                getFieldValue('mode') === 'trunk'
                  ? 'PVID / Native VLAN (1-4094)'
                  : 'VLAN ID (1-4094)'
              }
              rules={[{ required: true, message: '请输入VLAN ID' }]}
            >
              <InputNumber
                min={1}
                max={4094}
                style={{ width: '100%' }}
                disabled={portType === 'vlan'}
                placeholder={
                  getFieldValue('mode') === 'trunk' ? 'Trunk 端口的默认 VLAN' : '例如：100'
                }
              />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item name="mode" label="端口模式" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'access', label: 'Access（单VLAN，适合终端设备）' },
              { value: 'trunk', label: 'Trunk（多VLAN，适合交换机互连）' }
            ]}
          />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.mode !== cur.mode}>
          {({ getFieldValue }) =>
            getFieldValue('mode') === 'trunk' ? (
              <Form.Item
                name="allowed_vlans"
                label="允许 VLAN（Trunk 模式）"
                rules={[{ required: true, message: 'Trunk 模式必须指定允许的 VLAN 范围' }]}
                help="例如：10-12,14。这些 VLAN 不存在时会自动创建"
              >
                <Input placeholder="1-10,20,30-40" />
              </Form.Item>
            ) : null
          }
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default VlanConfigModal;
