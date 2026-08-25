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
import { CUSTOMER_STATUS_OPTIONS } from '@/types/enums';
import type { Customer } from '@/types/models';

interface CustomerFormProps {
  open: boolean;
  editRecord?: Customer | null;
  onCancel: () => void;
}


function CustomerForm({ open, editRecord, onCancel }: CustomerFormProps) {
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
      title={isEdit ? '编辑客户' : '新增客户'}
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
          label="客户名称"
          rules={[{ required: true, message: '请输入客户名称' }]}
        >
          <Input placeholder="请输入客户名称" />
        </Form.Item>
        <Form.Item name="customer_status" label="客户状态">
          <Select options={CUSTOMER_STATUS_OPTIONS} placeholder="请选择状态" allowClear />
        </Form.Item>
        <Form.Item name="contact_person" label="联系人">
          <Input placeholder="请输入联系人" />
        </Form.Item>
        <Form.Item name="contact_phone" label="联系电话">
          <Input placeholder="请输入联系电话" />
        </Form.Item>
        <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
          <Input placeholder="请输入邮箱" />
        </Form.Item>
        <Form.Item name="address" label="地址">
          <Input placeholder="请输入地址" />
        </Form.Item>
        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={3} placeholder="请输入备注" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default CustomerForm;
