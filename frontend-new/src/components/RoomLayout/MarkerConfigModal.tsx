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
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  useCreateRoomLayoutMarker,
  useDeleteRoomLayoutMarker,
  useRoomCabinets,
  useRoomLayoutMarkers,
  useUpdateRoomLayoutMarker
} from '@/services/room';
import { MARKER_TYPE_LABEL_KEYS, positionLabel } from './palette';
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

export default function MarkerConfigModal({ roomId, open, onClose }: MarkerConfigModalProps) {
  const { t: ta } = useTranslation('asset');
  const { t: tc } = useTranslation('common');

  const { data: markers = [], isLoading } = useRoomLayoutMarkers(roomId);
  const { data: cabinets = [] } = useRoomCabinets(roomId);
  const createMutation = useCreateRoomLayoutMarker(roomId);
  const updateMutation = useUpdateRoomLayoutMarker(roomId);
  const deleteMutation = useDeleteRoomLayoutMarker(roomId);

  const [form] = Form.useForm<MarkerFormValues>();
  const [editing, setEditing] = useState<RoomLayoutMarker | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const markerTypeOptions = useMemo(
    () =>
      Object.keys(MARKER_TYPE_LABEL_KEYS).map((value) => ({
        value,
        label: ta(MARKER_TYPE_LABEL_KEYS[value])
      })),
    [ta]
  );

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
          message.success(ta('roomLayout.marker.message.updated'));
        } else {
          await createMutation.mutateAsync(payload);
          message.success(ta('roomLayout.marker.message.created'));
        }
        setFormOpen(false);
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : ta('roomLayout.marker.message.saveFailed')
        );
      } finally {
        setSubmitting(false);
      }
    },
    [createMutation, editing, ta, updateMutation]
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
        title: ta('roomLayout.marker.occupiedTitle'),
        content: ta('roomLayout.marker.occupiedContent', {
          position: positionLabel(values.row_number, values.col_number, ta),
          cabinet: occupied.cabinet_number
        }),
        okText: ta('roomLayout.marker.stillAdd'),
        cancelText: tc('action.cancel'),
        onOk: () => doSubmit(values)
      });
      return;
    }

    await doSubmit(values);
  }, [cabinets, doSubmit, form, ta, tc]);

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
        message.success(ta('roomLayout.marker.message.deleted'));
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : ta('roomLayout.marker.message.deleteFailed')
        );
      }
    },
    [deleteMutation, ta]
  );

  const columns: ColumnsType<RoomLayoutMarker> = useMemo(
    () => [
      {
        title: tc('field.type'),
        dataIndex: 'marker_type',
        width: 100,
        render: (type: string) => {
          const key = MARKER_TYPE_LABEL_KEYS[type];
          return <Tag>{key ? ta(key) : type}</Tag>;
        }
      },
      {
        title: ta('roomLayout.marker.position'),
        key: 'position',
        width: 160,
        render: (_, record) => positionLabel(record.row_number, record.col_number, ta)
      },
      {
        title: ta('roomLayout.marker.label'),
        dataIndex: 'label',
        ellipsis: true,
        render: (label?: string | null) => label || '-'
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
              title={ta('roomLayout.marker.confirmDelete')}
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
        title={ta('roomLayout.marker.title')}
        open={open}
        onCancel={onClose}
        footer={null}
        width={780}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {ta('roomLayout.marker.hint')}
        </Typography.Paragraph>
        <div style={{ marginBottom: 12 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {ta('roomLayout.marker.add')}
          </Button>
        </div>
        <Table<RoomLayoutMarker>
          rowKey="id"
          size="small"
          loading={isLoading}
          dataSource={markers}
          columns={columns}
          pagination={false}
          locale={{ emptyText: ta('roomLayout.marker.empty') }}
        />
      </Modal>

      <Modal
        title={editing ? ta('roomLayout.marker.editTitle') : ta('roomLayout.marker.createTitle')}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText={tc('action.save')}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="marker_type"
            label={ta('roomLayout.marker.facilityType')}
            rules={[{ required: true, message: ta('roomLayout.marker.facilityTypeRequired') }]}
          >
            <Select options={markerTypeOptions} />
          </Form.Item>

          <Form.Item
            name="row_number"
            label={ta('roomLayout.marker.rowNumber')}
            extra={ta('roomLayout.marker.rowExtra')}
            rules={[
              { required: true, message: ta('roomLayout.marker.rowRequired') },
              { type: 'number', min: 0, message: ta('roomLayout.marker.rowNegative') }
            ]}
          >
            <InputNumber min={0} max={9999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="col_number"
            label={ta('roomLayout.marker.colNumber')}
            extra={ta('roomLayout.marker.colExtra')}
            rules={[
              { required: true, message: ta('roomLayout.marker.colRequired') },
              { type: 'number', min: 0, message: ta('roomLayout.marker.colNegative') }
            ]}
          >
            <InputNumber min={0} max={9999} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="label"
            label={ta('roomLayout.marker.label')}
            extra={ta('roomLayout.marker.labelExtra')}
          >
            <Input maxLength={100} placeholder={ta('roomLayout.marker.labelPlaceholder')} />
          </Form.Item>

          <Form.Item name="notes" label={tc('field.remarks')}>
            <Input.TextArea maxLength={500} rows={2} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
