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
import { useTranslation } from 'react-i18next';

interface VirtualRoomFormProps {
  open: boolean;
  editRecord: VirtualRoom | null;
  onClose: () => void;
}

function VirtualRoomForm({ open, editRecord, onClose }: VirtualRoomFormProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
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
        message.success(tc('message.updateSuccess'));
      } else {
        await createVirtualRoom.mutateAsync({
          name: values.name,
          description: values.description || '',
          device_ids: values.device_ids || [],
        });
        message.success(tc('message.createSuccess'));
      }
      onClose();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return; // 表单验证错误，antd 自动显示
      }
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return (
    <Modal
      open={open}
      title={isEdit ? td('virtualRoom.edit') : td('virtualRoom.add')}
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
          label={td('virtualRoom.field.name')}
          rules={[{ required: true, message: td('virtualRoom.form.namePlaceholder') }]}
        >
          <Input placeholder={td('virtualRoom.form.namePlaceholder')} maxLength={255} />
        </Form.Item>
        <Form.Item name="description" label={tc('field.description')}>
          <Input.TextArea
            placeholder={td('virtualRoom.form.descriptionPlaceholder')}
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
