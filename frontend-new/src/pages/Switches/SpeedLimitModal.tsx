import { useEffect } from 'react';
import { Modal, Form, InputNumber } from 'antd';

export interface SpeedLimitValues {
  inbound: number;
  outbound: number;
}

interface SpeedLimitModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  maxSpeed: number;
  onSubmit: (values: SpeedLimitValues) => void;
}


export function SpeedLimitModal({
  open,
  onClose,
  portName,
  maxSpeed,
  onSubmit
}: SpeedLimitModalProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({ inbound: Number(values.inbound), outbound: Number(values.outbound) });
    } catch {
      
    }
  };

  return (
    <Modal
      title={`设置端口限速 — ${portName}`}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnHidden
      width={480}
    >
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
        <div>使用 QoS 策略限速（traffic-policy / qos policy）</div>
        <div>
          <b>上行（inbound）</b>：流量进入交换机端口的方向，即用户上传方向
        </div>
        <div>
          <b>下行（outbound）</b>：流量离开交换机端口的方向，即用户下载方向
        </div>
        <div>
          输入 <b>0</b> 表示取消该方向限速，端口速率上限：{maxSpeed} Mbps
        </div>
      </div>
      <Form form={form} layout="vertical">
        <Form.Item
          name="inbound"
          label="上行限速 (Mbps)"
          rules={[{ required: true, message: '请输入上行限速' }]}
        >
          <InputNumber
            min={0}
            max={maxSpeed}
            placeholder={`0-${maxSpeed}，0 取消限速`}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item
          name="outbound"
          label="下行限速 (Mbps)"
          rules={[{ required: true, message: '请输入下行限速' }]}
        >
          <InputNumber
            min={0}
            max={maxSpeed}
            placeholder={`0-${maxSpeed}，0 取消限速`}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default SpeedLimitModal;
