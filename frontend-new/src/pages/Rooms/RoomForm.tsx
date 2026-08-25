/**
 * 机房表单（新增/编辑 Modal）
 * - 使用 SchemaForm 声明式驱动
 */
import { useEffect, useRef } from 'react';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm/SchemaForm';
import type { FormInstance } from 'antd/es/form';
import { useCreateRoom, useUpdateRoom, type CreateRoomRequest, type UpdateRoomRequest } from '@/services/room';
import type { Room } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';

interface RoomFormProps {
  open: boolean;
  editRecord: Room | null;
  onClose: () => void;
}

const ROOM_SCHEMA: FormSchema = {
  fields: [
    { name: 'name', label: '机房名称', type: 'input', required: true, placeholder: '请输入机房名称' },
    { name: 'location', label: '机房位置', type: 'input', required: true, placeholder: '请输入机房位置' },
    { name: 'contact', label: '联系人', type: 'input', placeholder: '联系人（可选）' },
    { name: 'contact_phone', label: '联系电话', type: 'input', placeholder: '联系电话（可选）' },
  ],
};

function RoomForm({ open, editRecord, onClose }: RoomFormProps) {
  const formRef = useRef<FormInstance>(null);
  const message = useMessage();
  const createRoom = useCreateRoom();
  const updateRoom = useUpdateRoom();
  const isEdit = !!editRecord;

  useEffect(() => {
    if (open && formRef.current) {
      if (editRecord) {
        formRef.current.setFieldsValue(editRecord);
      } else {
        formRef.current.resetFields();
      }
    }
  }, [open, editRecord]);

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      if (isEdit) {
        await updateRoom.mutateAsync({ id: editRecord!.id, ...values } as UpdateRoomRequest);
        message.success('更新成功');
      } else {
        await createRoom.mutateAsync(values as CreateRoomRequest);
        message.success('创建成功');
      }
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return (
    <SchemaForm
      schema={ROOM_SCHEMA}
      formRef={formRef}
      onSubmit={handleSubmit}
      onCancel={onClose}
      loading={createRoom.isPending || updateRoom.isPending}
      modalProps={{
        open,
        title: isEdit ? '编辑机房' : '新增机房',
        destroyOnHidden: true,
      }}
    />
  );
}

export default RoomForm;
