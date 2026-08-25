import { useEffect } from 'react';
import { Modal, Form, Select, Input, Typography } from 'antd';
import type { SelectOption } from '@/services';

interface IPBatchEditModalProps {
  open: boolean;
  mode: 'customer' | 'notes';
  count: number;
  customerOptions?: SelectOption[];
  submitting: boolean;
  onClose: () => void;
  
  onSubmit: (values: { customer_id?: number | null; notes?: string }) => void;
}


export function IPBatchEditModal({
  open,
  mode,
  count,
  customerOptions,
  submitting,
  onClose,
  onSubmit
}: IPBatchEditModalProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    if (mode === 'customer') {
      onSubmit({ customer_id: values.customer_id ?? null });
    } else {
      onSubmit({ notes: values.notes ?? '' });
    }
  };

  return (
    <Modal
      title={mode === 'customer' ? '批量分配客户' : '批量修改备注'}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={submitting}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        将对选中的 {count} 个 IP {mode === 'customer' ? '分配客户' : '修改备注'}。
      </Typography.Paragraph>
      <Form form={form} layout="vertical">
        {mode === 'customer' ? (
          <Form.Item
            name="customer_id"
            label="客户"
            rules={[{ required: true, message: '请选择客户' }]}
          >
            <Select placeholder="选择客户" options={customerOptions} allowClear />
          </Form.Item>
        ) : (
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} placeholder="输入备注内容" maxLength={200} showCount />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
