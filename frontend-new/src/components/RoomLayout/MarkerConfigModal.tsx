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
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import {
  useCreateRoomLayoutMarker,
  useDeleteRoomLayoutMarker,
  useRoomCabinets,
  useRoomLayoutMarkers,
  useUpdateRoomLayoutMarker
} from '@/services/room';
import { MARKER_TYPE_LABEL, positionLabel } from './palette';
import type { RoomLayoutMarker } from '@/types/models';
import type { RoomLayoutMarkerCreate } from '@/types/api-bridge';

interface MarkerFormValues {
  marker_type: RoomLayoutMarkerCreate['marker_type'];
  row_number: number;
  col_number: number;
  label?: string | null;
  notes?: string | null;
}

export interface MarkerConfigModalProps {
  roomId: number;
  open: boolean;
  onClose: () => void;
}

const MARKER_TYPE_OPTIONS = Object.keys(MARKER_TYPE_LABEL).map((value) => ({
  value,
  label: MARKER_TYPE_LABEL[value]
}));

export default function MarkerConfigModal({ roomId, open, onClose }: MarkerConfigModalProps) {
  const { data: markers = [], isLoading } = useRoomLayoutMarkers(roomId);
  const { data: cabinets = [] } = useRoomCabinets(roomId);
  const createMutation = useCreateRoomLayoutMarker(roomId);
  const updateMutation = useUpdateRoomLayoutMarker(roomId);
  const deleteMutation = useDeleteRoomLayoutMarker(roomId);

  const [form] = Form.useForm<MarkerFormValues>();
  const [editing, setEditing] = useState<RoomLayoutMarker | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const pendingValuesRef = useRef<MarkerFormValues | null>(null);

  useEffect(() => {
    if (!formOpen || !pendingValuesRef.current) return;
    form.setFieldsValue(pendingValuesRef.current);
    pendingValuesRef.current = null;
  }, [formOpen, form]);

  const doSubmit = useCallback(
    async (values: MarkerFormValues) => {
      setSubmitting(true);
      try {
        const payload: RoomLayoutMarkerCreate = {
          marker_type: values.marker_type,
          row_number: values.row_number,
          col_number: values.col_number,
          label: values.label ?? null,
          notes: values.notes ?? null
        };
        if (editing) {
          await updateMutation.mutateAsync({ markerId: editing.id, data: payload });
          message.success('占位标记已更新');
        } else {
          await createMutation.mutateAsync(payload);
          message.success('占位标记已新增');
        }
        setFormOpen(false);
      } catch (err) {
        message.error(err instanceof Error ? err.message : '保存占位标记失败');
      } finally {
        setSubmitting(false);
      }
    },
    [createMutation, editing, updateMutation]
  );

  const handleSubmit = useCallback(async () => {
    let values: MarkerFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return; // 校验未通过：antd 已在表单上标红
    }

    const occupied = cabinets.find(
      (c) => c.row === values.row_number && c.col === values.col_number
    );
    if (occupied) {
      Modal.confirm({
        title: '该位置已有机柜',
        content: `${positionLabel(values.row_number, values.col_number)} 已放置机柜 ${
          occupied.cabinet_number
        }。继续添加标记会与该机柜占用同一格，平面图上将以冲突角标提示。确认继续？`,
        okText: '仍要添加',
        cancelText: '取消',
        onOk: () => doSubmit(values)
      });
      return;
    }

    await doSubmit(values);
  }, [cabinets, doSubmit, form]);

  const openCreate = useCallback(() => {
    const maxRow = cabinets.reduce((acc, c) => Math.max(acc, c.row ?? 0), 0);
    setEditing(null);
    pendingValuesRef.current = {
      marker_type: 'ac',
      row_number: maxRow > 0 ? maxRow + 1 : 1,
      col_number: 1,
      label: null,
      notes: null
    };
    setFormOpen(true);
  }, [cabinets]);

  const openEdit = useCallback((marker: RoomLayoutMarker) => {
    setEditing(marker);
    pendingValuesRef.current = {
      marker_type: marker.marker_type as MarkerFormValues['marker_type'],
      row_number: marker.row_number,
      col_number: marker.col_number,
      label: marker.label ?? null,
      notes: marker.notes ?? null
    };
    setFormOpen(true);
  }, []);

  const handleDelete = useCallback(
    async (markerId: number) => {
      try {
        await deleteMutation.mutateAsync(markerId);
        message.success('占位标记已删除');
      } catch (err) {
        message.error(err instanceof Error ? err.message : '删除占位标记失败');
      }
    },
    [deleteMutation]
  );

  const columns: ColumnsType<RoomLayoutMarker> = [
    {
      title: '类型',
      dataIndex: 'marker_type',
      width: 100,
      render: (type: string) => <Tag>{MARKER_TYPE_LABEL[type] ?? type}</Tag>
    },
    {
      title: '位置',
      key: 'position',
      width: 160,
      render: (_, record) => positionLabel(record.row_number, record.col_number)
    },
    {
      title: '标签',
      dataIndex: 'label',
      ellipsis: true,
      render: (label?: string | null) => label || '-'
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
            title="确认删除该占位标记？"
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
      <Modal title="管理占位标记" open={open} onCancel={onClose} footer={null} width={780}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          标记用于表达「这个格子不能放机柜」——门、精密空调、PDU、立柱等。行列号填 0
          表示机柜网格外侧（如第 1 列外侧的门）。本功能只做位置提示，**不是设施资产台账**，
          不记录型号与维保信息。
        </Typography.Paragraph>
        <div style={{ marginBottom: 12 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增标记
          </Button>
        </div>
        <Table<RoomLayoutMarker>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={markers}
          columns={columns}
          pagination={false}
          locale={{ emptyText: '尚未添加占位标记' }}
        />
      </Modal>

      <Modal
        title={editing ? '编辑占位标记' : '新增占位标记'}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="marker_type"
            label="设施类型"
            rules={[{ required: true, message: '请选择设施类型' }]}
          >
            <Select options={MARKER_TYPE_OPTIONS} />
          </Form.Item>

          <Form.Item
            name="row_number"
            label="行号"
            extra="0 表示机柜网格外侧（如端头空调）"
            rules={[
              { required: true, message: '请填写行号' },
              { type: 'number', min: 0, message: '行号不能为负数' }
            ]}
          >
            <InputNumber min={0} max={9999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="col_number"
            label="列号"
            extra="0 表示机柜网格外侧（如端头空调、门）"
            rules={[
              { required: true, message: '请填写列号' },
              { type: 'number', min: 0, message: '列号不能为负数' }
            ]}
          >
            <InputNumber min={0} max={9999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="label" label="标签" extra="留空则按类型显示，如「空调」">
            <Input maxLength={100} placeholder="如：空调-01" />
          </Form.Item>

          <Form.Item name="notes" label="备注">
            <Input.TextArea maxLength={500} rows={2} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
