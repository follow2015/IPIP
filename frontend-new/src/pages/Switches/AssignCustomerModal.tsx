import { useEffect } from 'react';
import { Modal, Form, Select, Input } from 'antd';
import { useTranslation } from 'react-i18next';
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
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
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
    <Modal title={td('switch.assign.title')} open={open} onOk={handleOk} onCancel={onClose} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Form.Item label={td('switch.assign.port')}>
          <span>{portName}</span>
        </Form.Item>
        <Form.Item name="customer_id" label={tc('field.customer')}>
          <Select
            placeholder={td('port.field.selectCustomer')}
            options={[{ value: 0, label: td('switch.assign.none') }, ...(customerOptions ?? [])]}
            allowClear
          />
        </Form.Item>
        <Form.Item name="description" label={td('switch.assign.description')}>
          <Input.TextArea rows={2} placeholder={td('switch.assign.descriptionPlaceholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default AssignCustomerModal;
