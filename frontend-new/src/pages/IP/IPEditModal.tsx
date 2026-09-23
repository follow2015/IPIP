import { useEffect } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { IPAddress } from '@/types/models';
import type { SelectOption } from '@/services';

interface IPEditModalProps {
  open: boolean;
  onClose: () => void;
  ip: IPAddress | null;
  customerOptions: SelectOption[];
  submitting: boolean;
  onSubmit: (values: { customer_id?: number; notes?: string }) => void;
}

export function IPEditModal({
  open,
  onClose,
  ip,
  customerOptions,
  submitting,
  onSubmit
}: IPEditModalProps) {
  const { t } = useTranslation('network');
  const [form] = Form.useForm();

  useEffect(() => {
    if (open && ip) {
      form.setFieldsValue({ customer_id: ip.customer_id ?? undefined, notes: ip.notes });
    }
  }, [open, ip, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    onSubmit({ customer_id: values.customer_id ?? null, notes: values.notes });
  };

  return (
    <Modal
      title={t('ip.edit.title')}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={submitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item label={t('ip.field.ipAddress')}>
          <Input value={ip?.ip_address} disabled />
        </Form.Item>
        <Form.Item name="customer_id" label={t('ip.field.customer')}>
          <Select placeholder={t('ip.edit.selectCustomer')} options={customerOptions} allowClear />
        </Form.Item>
        <Form.Item name="notes" label={t('ip.field.notes')}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
