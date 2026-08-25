/**
 * 用户表单（新增/编辑 Modal）
 * - 密码双次确认 + 复杂度提示
 * - 角色选择
 * - 编辑时密码非必填，用户名禁用
 */
import { useEffect, useMemo } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import type { User } from '@/types/models';

const PASSWORD_TIPS = '至少8位，需包含大写字母、小写字母、数字和特殊字符';

interface UserFormProps {
  open: boolean;
  editRecord: User | null;
  onCancel: () => void;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
  roleOptions?: { label: string; value: string | number }[];
}

function UserForm({ open, editRecord, onCancel, onOk, loading, roleOptions }: UserFormProps) {
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
      title={isEdit ? '编辑用户' : '新增用户'}
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
          label="用户名"
          rules={[{ required: true, message: '请输入用户名' }]}
        >
          <Input placeholder="用户名" disabled={isEdit} />
        </Form.Item>

        <Form.Item
          name="password"
          label="密码"
          rules={isEdit
            ? [{ required: false }]
            : [
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少8位' },
              ]
          }
          extra={!isEdit ? PASSWORD_TIPS : '留空则不修改'}
        >
          <Input.Password placeholder={isEdit ? '留空则不修改' : '请输入密码'} />
        </Form.Item>

        {!isEdit && (
          <Form.Item
            name="confirm_password"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="再次输入密码" />
          </Form.Item>
        )}

        <Form.Item
          name="email"
          label="邮箱"
          rules={[{ required: !isEdit, message: '请输入邮箱' }]}
        >
          <Input placeholder="邮箱" />
        </Form.Item>

        <Form.Item name="name" label="姓名">
          <Input placeholder="真实姓名" />
        </Form.Item>

        <Form.Item name="department" label="部门">
          <Input placeholder="部门" />
        </Form.Item>

        <Form.Item name="contact_phone" label="联系电话">
          <Input placeholder="联系电话" />
        </Form.Item>

        <Form.Item name="roles" label="角色">
          <Select
            mode="multiple"
            placeholder="选择角色"
            options={roleOptions}
            allowClear
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default UserForm;
