/**
 * 客户表单（新增/编辑 Modal）
 * - 使用 useCrudForm 管理表单逻辑（回填/提交/confirmLoading）
 * - 渲染层保留手写 JSX（字段简单，无需 SchemaForm）
 */
import { Modal, Form, Input, Select } from 'antd';
import { useCrudForm } from '@/hooks/useCrudForm';
import {
  useCreateCustomer,
  useUpdateCustomer,
  type CreateCustomerRequest,
  type UpdateCustomerRequest
} from '@/services/customer';
import { getCustomerStatusOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Customer } from '@/types/models';

interface CustomerFormProps {
  open: boolean;
  editRecord?: Customer | null;
  onCancel: () => void;
}

function CustomerForm({ open, editRecord, onCancel }: CustomerFormProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { form, isEdit, handleSubmit, confirmLoading } = useCrudForm<
    Customer,
    CreateCustomerRequest,
    UpdateCustomerRequest
  >({
    open,
    editRecord: editRecord ?? null,
    onClose: onCancel,
    useCreate: useCreateCustomer,
    useUpdate: useUpdateCustomer
  });

  return (
    <Modal
      title={isEdit ? td('customer.edit') : td('customer.add')}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      width={560}
      confirmLoading={confirmLoading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="customer_name"
          label={td('customer.field.name')}
          rules={[{ required: true, message: td('customer.form.nameRequired') }]}
        >
          <Input placeholder={td('customer.form.namePlaceholder')} />
        </Form.Item>
        <Form.Item name="customer_status" label={td('customer.field.status')}>
          <Select
            options={getCustomerStatusOptions(td)}
            placeholder={td('cabinet.form.statusPlaceholder')}
            allowClear
          />
        </Form.Item>
        <Form.Item name="contact_person" label={td('customer.field.contactPerson')}>
          <Input placeholder={td('customer.form.contactPersonPlaceholder')} />
        </Form.Item>
        <Form.Item name="contact_phone" label={td('customer.field.contactPhone')}>
          <Input placeholder={td('customer.form.contactPhonePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="email"
          label={td('customer.field.email')}
          rules={[{ type: 'email', message: td('customer.form.emailInvalid') }]}
        >
          <Input placeholder={td('customer.form.emailPlaceholder')} />
        </Form.Item>
        <Form.Item name="address" label={td('customer.field.address')}>
          <Input placeholder={td('customer.form.addressPlaceholder')} />
        </Form.Item>
        <Form.Item name="notes" label={tc('field.remarks')}>
          <Input.TextArea rows={3} placeholder={td('customer.form.notesPlaceholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default CustomerForm;
