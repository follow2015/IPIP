/**
 * 角色编辑表单
 * - 支持新增和编辑模式
 */
import { useEffect } from 'react';
import { Modal, Form, Input } from 'antd';
import type { Role } from '@/types/models';
import { useTranslation } from 'react-i18next';

interface RoleFormProps {
  open: boolean;
  editRecord?: Role | null;
  onCancel: () => void;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
}

function RoleForm({ open, editRecord, onCancel, onOk, loading }: RoleFormProps) {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [form] = Form.useForm();
  const isEdit = !!editRecord;

  useEffect(() => {
    if (open && editRecord) {
      form.setFieldsValue({
        name: editRecord.name,
        display_name: editRecord.display_name,
        description: editRecord.description,
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, editRecord, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    await onOk(values);
  };

  return (
    <Modal
      title={isEdit ? t('role.modal.editTitle') : t('role.modal.createTitle')}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      width={480}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t('role.field.name')}
          rules={[{ required: true, message: t('role.validation.nameRequired') }]}
        >
          <Input placeholder={t('role.placeholder.name')} disabled={isEdit} />
        </Form.Item>
        <Form.Item
          name="display_name"
          label={t('role.field.displayName')}
          rules={[{ required: true, message: t('role.validation.displayNameRequired') }]}
        >
          <Input placeholder={t('role.placeholder.displayName')} />
        </Form.Item>
        <Form.Item name="description" label={tc('field.description')}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default RoleForm;
