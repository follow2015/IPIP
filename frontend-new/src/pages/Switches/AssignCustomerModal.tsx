import { useEffect } from 'react';
import { Modal, Form, Select, Input } from 'antd';
import type { SelectOption } from '@/services';

export interface AssignCustomerValues {
  customer_id: number | null;
  description: string;
}

interface AssignCustomerModalProps {
  open: boolean;
  onClose: () => void;
  portName: string;
  initialCustomerId: number | null;
  initialDescription: string;
  customerOptions?: SelectOption[];
  onSubmit: (values: AssignCustomerValues) => void;
}


export function AssignCustomerModal({
  open,
  onClose,
  portName,
  initialCustomerId,
  initialDescription,
  customerOptions,
  onSubmit
}: AssignCustomerModalProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ customer_id: initialCustomerId ?? 0, description: initialDescription });
    }
  }, [open, initialCustomerId, initialDescription, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit({
        customer_id: (values.customer_id ?? null) as number | null,
        description: (values.description ?? '') as string
      });
    } catch {
      
    }
  };

  return (
    <Modal title="分配客户" open={open} onOk={handleOk} onCancel={onClose} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Form.Item label="端口">
          <span>{portName}</span>
        </Form.Item>
        <Form.Item name="customer_id" label="客户">
          <Select
            placeholder="选择客户"
            options={[{ value: 0, label: '无' }, ...(customerOptions ?? [])]}
            allowClear
          />
        </Form.Item>
        <Form.Item name="description" label="描述/备注">
          <Input.TextArea rows={2} placeholder="端口描述..." />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default AssignCustomerModal;
