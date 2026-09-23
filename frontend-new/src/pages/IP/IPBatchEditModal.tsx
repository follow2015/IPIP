import { useEffect } from 'react';
import { Modal, Form, Select, Input, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('network');
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
      title={mode === 'customer' ? t('ip.batchEdit.titleCustomer') : t('ip.batchEdit.titleNotes')}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={submitting}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {mode === 'customer'
          ? t('ip.batchEdit.descCustomer', { count })
          : t('ip.batchEdit.descNotes', { count })}
      </Typography.Paragraph>
      <Form form={form} layout="vertical">
        {mode === 'customer' ? (
          <Form.Item
            name="customer_id"
            label={t('ip.field.customer')}
            rules={[{ required: true, message: t('ip.batchEdit.customerRequired') }]}
          >
            <Select
              placeholder={t('ip.edit.selectCustomer')}
              options={customerOptions}
              allowClear
            />
          </Form.Item>
        ) : (
          <Form.Item name="notes" label={t('ip.field.notes')}>
            <Input.TextArea
              rows={3}
              placeholder={t('ip.batchEdit.notesPlaceholder')}
              maxLength={200}
              showCount
            />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
