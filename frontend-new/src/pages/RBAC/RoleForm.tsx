/**
 * 角色编辑表单
 * - 支持新增和编辑模式
 */
import { useEffect } from 'react';
import { Modal, Form, Input } from 'antd';
import type { Role } from '@/types/models';

interface RoleFormProps {
  open: boolean;
  editRecord?: Role | null;
  onCancel: () => void;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
}

function RoleForm({ open, editRecord, onCancel, onOk, loading }: RoleFormProps) {
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
      title={isEdit ? '编辑角色' : '新增角色'}
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
          label="角色名"
          rules={[{ required: true, message: '请输入角色名' }]}
        >
          <Input placeholder="如 admin" disabled={isEdit} />
        </Form.Item>
        <Form.Item
          name="display_name"
          label="显示名"
          rules={[{ required: true, message: '请输入显示名' }]}
        >
          <Input placeholder="如 管理员" />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default RoleForm;
