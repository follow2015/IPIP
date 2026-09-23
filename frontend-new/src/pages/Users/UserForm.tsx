/**
 * 用户表单（新增/编辑 Modal）
 * - 密码双次确认 + 复杂度提示
 * - 角色选择
 * - 编辑时密码非必填，用户名禁用
 */
import { useEffect, useMemo } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import type { User } from '@/types/models';
import { useTranslation } from 'react-i18next';

const PASSWORD_TIPS_KEY = 'user.field.passwordTips' as const;

interface UserFormProps {
  open: boolean;
  editRecord: User | null;
  onCancel: () => void;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
  roleOptions?: { label: string; value: string | number }[];
}

function UserForm({ open, editRecord, onCancel, onOk, loading, roleOptions }: UserFormProps) {
  const { t } = useTranslation('settings');
  const { t: ta } = useTranslation('auth');
  const [form] = Form.useForm();
  const isEdit = !!editRecord;

  useEffect(() => {
    if (open && editRecord) {
      form.setFieldsValue({
        username: editRecord.username,
        email: editRecord.email,
        name: editRecord.name,
        department: editRecord.department,
        contact_phone: editRecord.contact_phone,
        password: undefined,
        confirm_password: undefined,
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, editRecord, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const { confirm_password, ...submitValues } = values;
    await onOk(submitValues);
  };

  return (
    <Modal
      title={isEdit ? t('user.modal.editTitle') : t('user.modal.createTitle')}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      width={520}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="username"
          label={ta('field.username')}
          rules={[{ required: true, message: ta('validation.usernameRequired') }]}
        >
          <Input placeholder={ta('field.username')} disabled={isEdit} />
        </Form.Item>

        <Form.Item
          name="password"
          label={ta('field.password')}
          rules={isEdit
            ? [{ required: false }]
            : [
                { required: true, message: ta('validation.passwordRequired') },
                { min: 8, message: t('user.validation.passwordMinLength') },
              ]
          }
          extra={!isEdit ? t(PASSWORD_TIPS_KEY) : t('user.field.passwordKeepHint')}
        >
          <Input.Password
            placeholder={isEdit ? t('user.field.passwordKeepHint') : ta('validation.passwordRequired')}
          />
        </Form.Item>

        {!isEdit && (
          <Form.Item
            name="confirm_password"
            label={t('user.field.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('user.validation.confirmPasswordRequired') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('user.validation.passwordMismatch')));
                },
              }),
            ]}
          >
            <Input.Password placeholder={t('user.field.passwordAgain')} />
          </Form.Item>
        )}

        <Form.Item
          name="email"
          label={t('user.field.email')}
          rules={[{ required: !isEdit, message: t('user.validation.emailRequired') }]}
        >
          <Input placeholder={t('user.field.email')} />
        </Form.Item>

        <Form.Item name="name" label={t('user.field.fullName')}>
          <Input placeholder={t('user.field.realNamePlaceholder')} />
        </Form.Item>

        <Form.Item name="department" label={t('user.field.department')}>
          <Input placeholder={t('user.field.department')} />
        </Form.Item>

        <Form.Item name="contact_phone" label={t('user.field.contactPhone')}>
          <Input placeholder={t('user.field.contactPhone')} />
        </Form.Item>

        <Form.Item name="roles" label={t('role.label')}>
          <Select
            mode="multiple"
            placeholder={t('role.selectPlaceholder')}
            options={roleOptions}
            allowClear
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default UserForm;
