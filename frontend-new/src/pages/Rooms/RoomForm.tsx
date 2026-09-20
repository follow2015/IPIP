import { useEffect, useRef } from 'react';
import { AutoComplete, Form, Typography } from 'antd';
import SchemaForm from '@/components/SchemaForm';
import type { FormSchema } from '@/components/SchemaForm/SchemaForm';
import type { FormInstance } from 'antd/es/form';
import {
  useCreateRoom,
  useUpdateRoom,
  useRoomBuildings,
  useRoomFloors,
  useRoomNameOptions,
  type CreateRoomRequest,
  type UpdateRoomRequest
} from '@/services/room';
import type { Room } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { useConfirm } from '@/utils/confirm';

interface RoomFormProps {
  open: boolean;
  editRecord: Room | null;
  onClose: () => void;
}

function BuildingInput(props: { value?: string | null; onChange?: (value: string) => void }) {
  const { data: buildings } = useRoomBuildings();
  return (
    <AutoComplete
      allowClear
      {...props}
      placeholder="如：A栋（可选，留空归入「未分组」）"
      options={(buildings ?? []).map((b) => ({ value: b }))}
      filterOption={(input, option) =>
        String(option?.value ?? '')
          .toLowerCase()
          .includes(input.toLowerCase())
      }
    />
  );
}

function NameInput(props: { value?: string; onChange?: (value: string) => void }) {
  const { data: options } = useRoomNameOptions();
  const name = Form.useWatch<string>('name');

  const matched = (options ?? []).find(
    (o) => o.name.toLowerCase() === (name ?? '').trim().toLowerCase()
  );

  return (
    <div>
      <AutoComplete
        allowClear
        {...props}
        placeholder="机房名称（同名机房将归为一组）"
        options={(options ?? []).map((o) => ({ value: o.name }))}
        filterOption={(input, option) =>
          String(option?.value ?? '')
            .toLowerCase()
            .includes(input.toLowerCase())
        }
      />
      {matched && matched.room_count > 0 ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          将并入「{matched.name}」机房组（现有 {matched.room_count} 条记录）
        </Typography.Text>
      ) : null}
    </div>
  );
}

function FloorInput(props: { value?: string | null; onChange?: (value: string) => void }) {
  const building = Form.useWatch<string>('building');
  const { data: floors } = useRoomFloors(building || undefined);
  return (
    <AutoComplete
      allowClear
      {...props}
      placeholder="如：3F（可选，留空表示未标注）"
      options={(floors ?? []).map((f) => ({ value: f }))}
      filterOption={(input, option) =>
        String(option?.value ?? '')
          .toLowerCase()
          .includes(input.toLowerCase())
      }
    />
  );
}

const ROOM_SCHEMA: FormSchema = {
  fields: [
    {
      name: 'name',
      label: '机房名称',
      type: 'custom',
      component: NameInput,
      required: true
    },
    {
      name: 'room_number',
      label: '房间号',
      type: 'input',
      required: true,
      placeholder: '如：01（同一机房名称下不可重复）'
    },
    {
      name: 'location',
      label: '机房位置',
      type: 'input',
      required: true,
      placeholder: '请输入机房位置'
    },
    { name: 'building', label: '所属楼栋', type: 'custom', component: BuildingInput },
    { name: 'floor', label: '所属楼层', type: 'custom', component: FloorInput },
    { name: 'contact', label: '联系人', type: 'input', placeholder: '联系人（可选）' },
    { name: 'contact_phone', label: '联系电话', type: 'input', placeholder: '联系电话（可选）' }
  ]
};

function RoomForm({ open, editRecord, onClose }: RoomFormProps) {
  const formRef = useRef<FormInstance>(null);
  const message = useMessage();
  const confirm = useConfirm();
  const createRoom = useCreateRoom();
  const updateRoom = useUpdateRoom();
  const nameOptions = useRoomNameOptions();
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

  const isNewGroupName = (name: string) => {
    const v = name.trim().toLowerCase();
    if (!v) return false;
    return !(nameOptions.data ?? []).some((o) => o.name.toLowerCase() === v);
  };

  const doSubmit = async (values: Record<string, unknown>) => {
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

  const handleSubmit = async (values: Record<string, unknown>) => {
    const name = String(values.name ?? '').trim();
    if (isNewGroupName(name)) {
      await confirm({
        title: '创建新机房组',
        content: `机房组「${name}」不存在，保存将创建新机房组。同一物理机房的房间应使用相同的机房名称。`,
        okText: '继续创建',
        cancelText: '取消',
        onOk: async () => {
          await doSubmit(values);
        }
      });
      return;
    }
    await doSubmit(values);
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
        destroyOnHidden: true
      }}
    />
  );
}

export default RoomForm;
