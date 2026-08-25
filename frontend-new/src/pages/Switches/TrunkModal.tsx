import { useEffect } from 'react';
import { Modal, Form, InputNumber } from 'antd';

export interface TrunkValues {
  trunk_id: number;
}

interface TrunkModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  onSubmit: (values: TrunkValues) => void;
}


export function TrunkModal({ open, onClose, portName, onSubmit }: TrunkModalProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({ trunk_id: Number(values.trunk_id) });
    } catch {
      
    }
  };

  return (
    <Modal
      title={`端口汇聚 — ${portName}`}
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
        <div>将当前端口加入指定的链路聚合组（Eth-Trunk）。</div>
        <div>若输入的 Eth-Trunk ID 在交换机上不存在，系统将自动创建。</div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item
          name="trunk_id"
          label="Eth-Trunk ID"
          rules={[{ required: true, message: '请输入Trunk ID' }]}
        >
          <InputNumber min={0} placeholder="例如：1" style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default TrunkModal;
