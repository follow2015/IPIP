import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  useCreateRoomChannel,
  useDeleteRoomChannel,
  useRoomChannels,
  useUpdateRoomChannel
} from '@/services/room';
import { CHANNEL_TYPE_LABEL_KEYS, SUPPLY_LABEL_KEYS, paletteKeyOf } from './palette';
import type { RoomChannel } from '@/types/models';
import type { RoomChannelCreate } from '@/types/api-bridge';

interface ChannelFormValues {
  col_number: number;
  channel_type: RoomChannelCreate['channel_type'];
  enclosed: boolean;
  supply?: RoomChannelCreate['supply'];
  label?: string | null;
  notes?: string | null;
}

export interface ChannelConfigModalProps {
  roomId: number;
  open: boolean;
  onClose: () => void;
}

const CHANNEL_TYPE_VALUES = ['cold', 'hot', 'mixed'] as const;
const SUPPLY_VALUES = ['floor', 'direct', 'none'] as const;

export default function ChannelConfigModal({ roomId, open, onClose }: ChannelConfigModalProps) {
  const { t: ta } = useTranslation('asset');
  const { t: tc } = useTranslation('common');

  const { data: channels = [], isLoading } = useRoomChannels(roomId);
  const createMutation = useCreateRoomChannel(roomId);
  const updateMutation = useUpdateRoomChannel(roomId);
  const deleteMutation = useDeleteRoomChannel(roomId);

  const [form] = Form.useForm<ChannelFormValues>();
  const [editing, setEditing] = useState<RoomChannel | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const channelTypeOptions = useMemo(
    () =>
      CHANNEL_TYPE_VALUES.map((value) => ({
        value,
        label: ta(CHANNEL_TYPE_LABEL_KEYS[value])
      })),
    [ta]
  );

  const supplyOptions = useMemo(
    () => SUPPLY_VALUES.map((value) => ({ value, label: ta(SUPPLY_LABEL_KEYS[value]) })),
    [ta]
  );

  const pendingValuesRef = useRef<ChannelFormValues | null>(null);

  useEffect(() => {
    if (!formOpen || !pendingValuesRef.current) return;
    form.setFieldsValue(pendingValuesRef.current);
    pendingValuesRef.current = null;
  }, [formOpen, form]);

  const openCreate = useCallback(() => {
    const used = new Set(channels.map((c) => c.col_number));
    let candidate = 1;
    while (used.has(candidate)) candidate += 1;
    setEditing(null);
    pendingValuesRef.current = {
      col_number: candidate,
      channel_type: 'cold',
      enclosed: true,
      supply: 'floor',
      label: null,
      notes: null
    };
    setFormOpen(true);
  }, [channels]);

  const openEdit = useCallback((channel: RoomChannel) => {
    setEditing(channel);
    pendingValuesRef.current = {
      col_number: channel.col_number,
      channel_type: channel.channel_type as ChannelFormValues['channel_type'],
      enclosed: channel.enclosed,
      supply: (channel.supply ?? undefined) as ChannelFormValues['supply'],
      label: channel.label ?? null,
      notes: channel.notes ?? null
    };
    setFormOpen(true);
  }, []);

  const handleSubmit = useCallback(async () => {
    let values: ChannelFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return; // 校验未通过：antd 已在表单上标红，无需额外提示
    }
    setSubmitting(true);
    try {
      const payload: RoomChannelCreate = {
        col_number: values.col_number,
        channel_type: values.channel_type,
        enclosed: values.enclosed,
        supply: values.supply ?? null,
        label: values.label ?? null,
        notes: values.notes ?? null
      };
      if (editing) {
        await updateMutation.mutateAsync({ channelId: editing.id, data: payload });
        message.success(ta('roomLayout.channel.message.updated'));
      } else {
        await createMutation.mutateAsync(payload);
        message.success(ta('roomLayout.channel.message.created'));
      }
      setFormOpen(false);
    } catch (err) {
      message.error(err instanceof Error ? err.message : ta('roomLayout.channel.message.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [createMutation, editing, form, ta, updateMutation]);

  const handleDelete = useCallback(
    async (channelId: number) => {
      try {
        await deleteMutation.mutateAsync(channelId);
        message.success(ta('roomLayout.channel.message.deleted'));
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : ta('roomLayout.channel.message.deleteFailed')
        );
      }
    },
    [deleteMutation, ta]
  );

  const columns: ColumnsType<RoomChannel> = useMemo(
    () => [
      {
        title: ta('roomLayout.channel.position'),
        key: 'position',
        render: (_, record) =>
          record.label || record.display_name || ta('roomLayout.channel.colSlot', { col: record.col_number })
      },
      {
        title: tc('field.type'),
        dataIndex: 'channel_type',
        width: 100,
        render: (type: string) => {
          const key = CHANNEL_TYPE_LABEL_KEYS[type];
          return <Tag color={paletteKeyOf(type)}>{key ? ta(key) : type}</Tag>;
        }
      },
      {
        title: ta('roomLayout.channel.enclosed'),
        dataIndex: 'enclosed',
        width: 90,
        render: (enclosed: boolean) =>
          enclosed ? (
            <Tag color="green">{ta('roomLayout.channel.enclosedTag')}</Tag>
          ) : (
            <Tag>{ta('roomLayout.channel.openTag')}</Tag>
          )
      },
      {
        title: ta('roomLayout.channel.supply'),
        dataIndex: 'supply',
        width: 150,
        render: (supply?: string | null) => {
          if (!supply) return '-';
          const key = SUPPLY_LABEL_KEYS[supply];
          return key ? ta(key) : supply;
        }
      },
      {
        title: tc('field.remarks'),
        dataIndex: 'notes',
        ellipsis: true,
        render: (notes?: string | null) => notes || '-'
      },
      {
        title: tc('field.actions'),
        key: 'action',
        width: 110,
        render: (_, record) => (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => openEdit(record)}>
              {tc('action.edit')}
            </Button>
            <Popconfirm
              title={ta('roomLayout.channel.confirmDelete')}
              okText={tc('action.delete')}
              cancelText={tc('action.cancel')}
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" size="small" danger>
                {tc('action.delete')}
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    ],
    [handleDelete, openEdit, ta, tc]
  );

  return (
    <>
      <Modal
        title={ta('roomLayout.channel.title')}
        open={open}
        onCancel={onClose}
        footer={null}
        width={780}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {ta('roomLayout.channel.hint')}
        </Typography.Paragraph>
        <div style={{ marginBottom: 12 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {ta('roomLayout.channel.add')}
          </Button>
        </div>
        <Table<RoomChannel>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={channels}
          columns={columns}
          pagination={false}
          locale={{ emptyText: ta('roomLayout.channel.empty') }}
        />
      </Modal>

      <Modal
        title={editing ? ta('roomLayout.channel.editTitle') : ta('roomLayout.channel.createTitle')}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText={tc('action.save')}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="col_number"
            label={ta('roomLayout.channel.colNumber')}
            extra={ta('roomLayout.channel.colNumberExtra')}
            rules={[
              { required: true, message: ta('roomLayout.channel.colNumberRequired') },
              { type: 'number', min: 0, message: ta('roomLayout.channel.colNumberNegative') }
            ]}
          >
            <InputNumber min={0} max={999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="channel_type"
            label={ta('roomLayout.channel.type')}
            rules={[{ required: true, message: ta('roomLayout.channel.typeRequired') }]}
          >
            <Select options={channelTypeOptions} />
          </Form.Item>

          <Form.Item
            name="enclosed"
            label={ta('roomLayout.channel.enclosedField')}
            valuePropName="checked"
            extra={ta('roomLayout.channel.enclosedExtra')}
          >
            <Switch
              checkedChildren={ta('roomLayout.channel.enclosedTag')}
              unCheckedChildren={ta('roomLayout.channel.openTag')}
            />
          </Form.Item>

          <Form.Item
            name="supply"
            label={ta('roomLayout.channel.supplyField')}
            extra={ta('roomLayout.channel.supplyExtra')}
          >
            <Select
              options={supplyOptions}
              allowClear
              placeholder={ta('roomLayout.channel.supplyUnset')}
            />
          </Form.Item>

          <Form.Item
            name="label"
            label={ta('roomLayout.channel.displayName')}
            extra={ta('roomLayout.channel.displayNameExtra')}
          >
            <Input maxLength={100} placeholder={ta('roomLayout.channel.displayNamePlaceholder')} />
          </Form.Item>

          <Form.Item name="notes" label={tc('field.remarks')}>
            <Input.TextArea maxLength={500} rows={2} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
