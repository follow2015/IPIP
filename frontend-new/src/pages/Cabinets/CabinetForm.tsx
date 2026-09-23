import { useEffect, useMemo, useState } from 'react';
import { Modal, Form, Input, InputNumber, Select, Switch, Alert, Tag, Space } from 'antd';
import { useCreateCabinet, useUpdateCabinet, useBatchCreateCabinet } from '@/services/cabinet';
import { useMessage } from '@/hooks/useMessage';
import { useRoomCabinets, useRoomLayoutMarkers, useRoomOptions } from '@/services/room';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { MARKER_TYPE_LABEL_KEYS } from '@/components/RoomLayout/palette';
import { getCabinetStatusOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Cabinet } from '@/types/models';

interface CabinetFormProps {
  open: boolean;
  editRecord: Cabinet | null;
  onClose: () => void;
}

function parseCabinetNumbers(input: string): string[] {
  if (!input.trim()) return [];
  const parts = input.split(/[,，\s]+/).filter(Boolean);
  const result: string[] = [];

  for (const part of parts) {
    const rangeMatch = part.match(/^([a-zA-Z]+)(\d+)-(\d+)$/);
    if (rangeMatch) {
      const prefix = rangeMatch[1];
      const start = parseInt(rangeMatch[2], 10);
      const end = parseInt(rangeMatch[3], 10);
      const width = rangeMatch[2].length;
      for (let i = start; i <= end; i++) {
        result.push(`${prefix}${String(i).padStart(width, '0')}`);
      }
    } else {
      result.push(part);
    }
  }
  return result;
}

function CabinetForm({ open, editRecord, onClose }: CabinetFormProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { t: ta } = useTranslation('asset');
  const [form] = Form.useForm();
  const message = useMessage();
  const createCabinet = useCreateCabinet();
  const updateCabinet = useUpdateCabinet();
  const batchCreateCabinet = useBatchCreateCabinet();
  const { data: roomOptions } = useRoomOptions();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const isEdit = !!editRecord;

  const [batchMode, setBatchMode] = useState(false);
  const [previewNumbers, setPreviewNumbers] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      if (editRecord) {
        setBatchMode(false);
        form.setFieldsValue({ ...editRecord });
      } else {
        form.resetFields();
        form.setFieldValue('total_u', 42);
        form.setFieldValue('status', 1);
        setBatchMode(false);
        setPreviewNumbers([]);
      }
    }
  }, [open, editRecord, form]);


  const watchedRoomId = Form.useWatch('room_id', form) as number | undefined;
  const watchedRow = Form.useWatch('row', form) as number | null | undefined;
  const watchedCol = Form.useWatch('col', form) as number | null | undefined;

  const { data: roomCabinets } = useRoomCabinets(watchedRoomId ?? 0);
  const { data: roomMarkers } = useRoomLayoutMarkers(watchedRoomId ?? 0);

  const occupiedBy = useMemo(() => {
    if (!watchedRow || !watchedCol) return null;
    return (
      (roomCabinets ?? []).find(
        (c) => c.row === watchedRow && c.col === watchedCol && c.id !== editRecord?.id
      ) ?? null
    );
  }, [roomCabinets, watchedRow, watchedCol, editRecord]);

  const markerAtCell = useMemo(() => {
    if (!watchedRow || !watchedCol) return null;
    return (
      (roomMarkers ?? []).find((m) => m.row_number === watchedRow && m.col_number === watchedCol) ??
      null
    );
  }, [roomMarkers, watchedRow, watchedCol]);

  const handleCabinetNumberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!batchMode) return;
    const numbers = parseCabinetNumbers(e.target.value);
    setPreviewNumbers(numbers);
  };

  const handleBatchModeChange = (checked: boolean) => {
    setBatchMode(checked);
    setPreviewNumbers([]);
    form.setFieldValue('cabinet_number', '');
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const nullableFields = ['customer_id', 'row', 'col', 'total_power', 'location'] as const;
      for (const field of nullableFields) {
        if (values[field] === undefined) {
          values[field] = null;
        }
      }
      if (isEdit) {
        await updateCabinet.mutateAsync({ id: editRecord.id, ...values });
        message.success(tc('message.updateSuccess'));
        onClose();
        return;
      }

      if (batchMode) {
        const numbers = parseCabinetNumbers(values.cabinet_number);
        if (numbers.length === 0) {
          message.warning(td('cabinet.batch.invalidNumber'));
          return;
        }
        if (numbers.length > 100) {
          message.warning(td('cabinet.batch.maxLimit'));
          return;
        }
        const res = await batchCreateCabinet.mutateAsync(values);
        const data = res.data;
        if (data?.created_count && data.created_count > 0) {
          message.success(td('cabinet.batch.created', { count: data.created_count }));
        }
        if (data?.failed_count && data.failed_count > 0) {
          const failedList = data.failed.slice(0, 5).join(', ');
          const more =
            data.failed_count > 5
              ? td('cabinet.batch.moreCount', { count: data.failed_count })
              : '';
          message.warning(td('cabinet.batch.createFailed', { list: failedList, more }));
        }
        onClose();
      } else {
        await createCabinet.mutateAsync(values);
        message.success(tc('message.createSuccess'));
        onClose();
      }
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  const confirmLoading = isEdit
    ? updateCabinet.isPending
    : batchMode
      ? batchCreateCabinet.isPending
      : createCabinet.isPending;

  return (
    <Modal
      title={isEdit ? td('cabinet.edit') : batchMode ? td('cabinet.batchAdd') : td('cabinet.add')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={confirmLoading}
      destroyOnHidden
      width={batchMode ? 560 : 480}
    >
      <Form form={form} layout="vertical" autoComplete="off">
        {/* 批量模式开关（仅新增时显示） */}
        {!isEdit && (
          <Form.Item>
            <Space>
              <Switch
                checked={batchMode}
                onChange={handleBatchModeChange}
                checkedChildren={td('cabinet.batch.modeBatch')}
                unCheckedChildren={td('cabinet.batch.modeSingle')}
              />
              <span style={{ color: '#8c8c8c', fontSize: 13 }}>
                {batchMode ? td('cabinet.batch.hintRange') : td('cabinet.batch.hintSingle')}
              </span>
            </Space>
          </Form.Item>
        )}

        {/* 机柜编号输入 */}
        <Form.Item
          name="cabinet_number"
          label={batchMode ? td('cabinet.form.numberExpression') : td('cabinet.form.name')}
          rules={[
            {
              required: true,
              message: batchMode
                ? td('cabinet.form.numberExpressionRequired')
                : td('cabinet.form.nameRequired')
            }
          ]}
        >
          <Input
            placeholder={
              batchMode
                ? td('cabinet.form.numberExpressionPlaceholder')
                : td('cabinet.form.namePlaceholder')
            }
            onChange={handleCabinetNumberChange}
          />
        </Form.Item>

        {/* 批量模式预览 */}
        {batchMode && previewNumbers.length > 0 && (
          <Form.Item>
            <Alert
              type="info"
              showIcon={false}
              message={
                <div>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>
                    {td('cabinet.batch.preview', { count: previewNumbers.length })}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {previewNumbers.map((num) => (
                      <Tag key={num} color="blue">
                        {num}
                      </Tag>
                    ))}
                  </div>
                </div>
              }
            />
          </Form.Item>
        )}

        <Form.Item
          name="room_id"
          label={td('basic.field.room')}
          rules={[{ required: true, message: td('cabinet.form.roomRequired') }]}
        >
          <Select placeholder={td('form.select.room')} options={roomOptions} allowClear />
        </Form.Item>

        <Form.Item
          name="total_u"
          label={td('cabinet.field.totalU')}
          rules={[{ required: true, message: td('cabinet.form.totalURequired') }]}
          initialValue={42}
        >
          <InputNumber
            min={1}
            max={50}
            style={{ width: '100%' }}
            placeholder={td('cabinet.field.totalU')}
          />
        </Form.Item>

        {/* 批量模式下隐藏位置相关字段，因为所有机柜共享同一值无意义，可在创建后逐个编辑 */}
        {!batchMode && (
          <>
            <Form.Item name="location" label={td('cabinet.form.location')}>
              <Input placeholder={td('cabinet.form.locationPlaceholder')} />
            </Form.Item>

            <div style={{ display: 'flex', gap: 16 }}>
              <Form.Item
                name="row"
                label={td('cabinet.form.row')}
                style={{ flex: 1 }}
                tooltip={td('cabinet.form.rowTooltip')}
              >
                <InputNumber
                  min={1}
                  style={{ width: '100%' }}
                  placeholder={td('cabinet.form.rowColPlaceholder')}
                />
              </Form.Item>
              <Form.Item
                name="col"
                label={td('cabinet.form.col')}
                style={{ flex: 1 }}
                tooltip={td('cabinet.form.colTooltip')}
              >
                <InputNumber
                  min={1}
                  style={{ width: '100%' }}
                  placeholder={td('cabinet.form.rowColPlaceholder')}
                />
              </Form.Item>
            </div>

            {/* 占用提示：机柜冲突是硬的（后端唯一约束会拒），标记冲突是软的（允许重叠） */}
            {occupiedBy ? (
              <Alert
                type="error"
                showIcon
                style={{ marginBottom: 16 }}
                message={ta('roomLayout.cabinetForm.occupied', {
                  row: watchedRow,
                  col: watchedCol,
                  cabinet: occupiedBy.cabinet_number
                })}
                description={ta('roomLayout.cabinetForm.occupiedHint')}
              />
            ) : markerAtCell ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message={ta('roomLayout.cabinetForm.markerOccupied', {
                  type: MARKER_TYPE_LABEL_KEYS[markerAtCell.marker_type]
                    ? ta(MARKER_TYPE_LABEL_KEYS[markerAtCell.marker_type])
                    : markerAtCell.marker_type
                })}
                description={ta('roomLayout.cabinetForm.markerOccupiedHint')}
              />
            ) : null}
          </>
        )}

        <Form.Item name="status" label={tc('field.status')} initialValue={1}>
          <Select options={getCabinetStatusOptions(td)} placeholder={td('cabinet.form.statusPlaceholder')} />
        </Form.Item>

        <Form.Item name="customer_id" label={td('cabinet.field.leaseCustomer')}>
          <Select
            options={customerOptions}
            placeholder={td('cabinet.form.leaseCustomerPlaceholder')}
            allowClear
          />
        </Form.Item>

        <Form.Item name="total_power" label={td('cabinet.field.ratedPowerUnit')}>
          <InputNumber
            min={0}
            style={{ width: '100%' }}
            placeholder={td('cabinet.field.ratedPower')}
          />
        </Form.Item>

        <Form.Item name="notes" label={tc('field.remarks')}>
          <Input.TextArea rows={2} placeholder={td('cabinet.form.notesPlaceholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default CabinetForm;
