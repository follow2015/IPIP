/**
 * 虚拟机房表单（新增/编辑 Modal）
 * - 名称 + 描述
 * - 创建时可选成员交换机
 */
import { useEffect, useRef } from 'react';
import { Form, Input, Modal } from 'antd';
import { useCreateVirtualRoom, useUpdateVirtualRoom } from '@/services/virtual-room';
import type { VirtualRoom } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';

interface VirtualRoomFormProps {
  open: boolean;
  editRecord: VirtualRoom | null;
  onClose: () => void;
}


function VirtualRoomForm({ open, editRecord, onClose }: VirtualRoomFormProps) {
  const [form] = Form.useForm();
  const message = useMessage();
  const createVirtualRoom = useCreateVirtualRoom();
  const updateVirtualRoom = useUpdateVirtualRoom();
  const isEdit = !!editRecord;

  
  useEffect(() => {
    if (open) {
      if (editRecord) {
        form.setFieldsValue({
          name: editRecord.name,
          description: editRecord.description,
        });
      } else {
        form.resetFields();
      }
    }
  }, [open, editRecord, form]);

  
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit) {
        await updateVirtualRoom.mutateAsync({ id: editRecord!.id, data: values });
        message.success('更新成功');
      } else {
        await createVirtualRoom.mutateAsync({
          name: values.name,
          description: values.description || '',
          device_ids: values.device_ids || [],
        });
        message.success('创建成功');
      }
      onClose();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return; 
      }
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return (
    <Modal
      open={open}
      title={isEdit ? '编辑虚拟机房' : '新增虚拟机房'}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={createVirtualRoom.isPending || updateVirtualRoom.isPending}
      destroyOnHidden
      width={520}
    >
      <Form
        form={form}
        layout="vertical"
        autoComplete="off"
        style={{ marginTop: 16 }}
      >
        <Form.Item
          name="name"
          label="虚拟机房名称"
          rules={[{ required: true, message: '请输入虚拟机房名称' }]}
        >
          <Input placeholder="请输入虚拟机房名称" maxLength={255} />
        </Form.Item>
        <Form.Item
          name="description"
          label="描述"
        >
          <Input.TextArea
            placeholder="请输入描述（可选）"
            maxLength={500}
            showCount
            rows={3}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default VirtualRoomForm;
