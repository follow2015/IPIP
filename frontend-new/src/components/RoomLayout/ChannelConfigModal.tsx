import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import {
  useCreateRoomChannel,
  useDeleteRoomChannel,
  useRoomChannels,
  useUpdateRoomChannel
} from '@/services/room';
import { CHANNEL_TYPE_LABEL, SUPPLY_LABEL, paletteKeyOf } from './palette';
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

const CHANNEL_TYPE_OPTIONS = (['cold', 'hot', 'mixed'] as const).map((value) => ({
  value,
  label: CHANNEL_TYPE_LABEL[value]
}));

const SUPPLY_OPTIONS = (['floor', 'direct', 'none'] as const).map((value) => ({
  value,
  label: SUPPLY_LABEL[value]
}));

export default function ChannelConfigModal({ roomId, open, onClose }: ChannelConfigModalProps) {
  const { data: channels = [], isLoading } = useRoomChannels(roomId);
  const createMutation = useCreateRoomChannel(roomId);
  const updateMutation = useUpdateRoomChannel(roomId);
  const deleteMutation = useDeleteRoomChannel(roomId);

  const [form] = Form.useForm<ChannelFormValues>();
  const [editing, setEditing] = useState<RoomChannel | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

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
        message.success('通道配置已更新');
      } else {
        await createMutation.mutateAsync(payload);
        message.success('通道配置已新增');
      }
      setFormOpen(false);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存通道配置失败');
    } finally {
      setSubmitting(false);
    }
  }, [createMutation, editing, form, updateMutation]);

  const handleDelete = useCallback(
    async (channelId: number) => {
      try {
        await deleteMutation.mutateAsync(channelId);
        message.success('通道配置已删除');
      } catch (err) {
        message.error(err instanceof Error ? err.message : '删除通道配置失败');
      }
    },
    [deleteMutation]
  );

  const columns: ColumnsType<RoomChannel> = [
    {
      title: '位置',
      key: 'position',
      render: (_, record) => record.label || record.display_name || `第 ${record.col_number} 列位`
    },
    {
      title: '类型',
      dataIndex: 'channel_type',
      width: 100,
      render: (type: string) => (
        <Tag color={paletteKeyOf(type)}>{CHANNEL_TYPE_LABEL[type] ?? type}</Tag>
      )
    },
    {
      title: '是否封闭',
      dataIndex: 'enclosed',
      width: 90,
      render: (enclosed: boolean) => (enclosed ? <Tag color="green">封闭</Tag> : <Tag>开放</Tag>)
    },
    {
      title: '送风',
      dataIndex: 'supply',
      width: 150,
      render: (supply?: string | null) => (supply ? (SUPPLY_LABEL[supply] ?? supply) : '-')
    },
    {
      title: '备注',
      dataIndex: 'notes',
      ellipsis: true,
      render: (notes?: string | null) => notes || '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该通道配置？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <>
      <Modal title="配置通道" open={open} onCancel={onClose} footer={null} width={780}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          通道位于相邻两列之间：填 N 表示「第 N 列与第 N+1 列之间」，填 0 表示「第 1
          列外侧」。是否封闭是图上区分老式机房与模块化机房的主要依据。
        </Typography.Paragraph>
        <div style={{ marginBottom: 12 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增通道
          </Button>
        </div>
        <Table<RoomChannel>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={channels}
          columns={columns}
          pagination={false}
          locale={{ emptyText: '尚未配置通道，平面图上不会渲染色带' }}
        />
      </Modal>

      <Modal
        title={editing ? '编辑通道配置' : '新增通道配置'}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="col_number"
            label="列位"
            extra="N = 第 N 列与第 N+1 列之间；0 = 第 1 列外侧（机柜网格外）"
            rules={[
              { required: true, message: '请填写列位' },
              { type: 'number', min: 0, message: '列位不能为负数' }
            ]}
          >
            <InputNumber min={0} max={999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="channel_type"
            label="通道类型"
            rules={[{ required: true, message: '请选择通道类型' }]}
          >
            <Select options={CHANNEL_TYPE_OPTIONS} />
          </Form.Item>

          <Form.Item
            name="enclosed"
            label="封闭通道"
            valuePropName="checked"
            extra="有端门/顶板的封闭通道；新式模块机房的封闭冷通道即此类"
          >
            <Switch checkedChildren="封闭" unCheckedChildren="开放" />
          </Form.Item>

          <Form.Item
            name="supply"
            label="送风方式"
            extra="「上送风直吹」易气流掺混，标准不推荐，仅适用于低热密度区域"
          >
            <Select options={SUPPLY_OPTIONS} allowClear placeholder="未标注" />
          </Form.Item>

          <Form.Item
            name="label"
            label="展示名"
            extra="留空则按列位自动生成，如「第 1 列与第 2 列之间」"
          >
            <Input maxLength={100} placeholder="如：A-B 冷通道" />
          </Form.Item>

          <Form.Item name="notes" label="备注">
            <Input.TextArea maxLength={500} rows={2} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
