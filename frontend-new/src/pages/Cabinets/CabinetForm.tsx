/**
 * 机柜表单（新增/编辑 Modal）
 * - 支持单条和批量创建模式
 * - 批量模式支持机柜编号智能解析：
 *   - 逗号分隔：m11,m13,n10
 *   - 范围展开：h1-10 → h1,h2,...,h10
 *   - 混合：m11,m13,h1-3,n10
 *   - 保持前导零：h01-03 → h01,h02,h03
 */
import { useEffect, useState } from 'react';
import { Modal, Form, Input, InputNumber, Select, Switch, Alert, Tag, Space } from 'antd';
import { useCreateCabinet, useUpdateCabinet, useBatchCreateCabinet } from '@/services/cabinet';
import { useMessage } from '@/hooks/useMessage';
import { useRoomOptions } from '@/services/room';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { CABINET_STATUS_OPTIONS } from '@/types/enums';
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
        message.success('更新成功');
        onClose();
        return;
      }

      if (batchMode) {
        const numbers = parseCabinetNumbers(values.cabinet_number);
        if (numbers.length === 0) {
          message.warning('请输入有效的机柜编号');
          return;
        }
        if (numbers.length > 100) {
          message.warning('单次最多创建 100 个机柜');
          return;
        }
        const res = await batchCreateCabinet.mutateAsync(values);
        const data = res.data;
        if (data?.created_count && data.created_count > 0) {
          message.success(`成功创建 ${data.created_count} 个机柜`);
        }
        if (data?.failed_count && data.failed_count > 0) {
          const failedList = data.failed.slice(0, 5).join(', ');
          const more = data.failed_count > 5 ? ` 等共 ${data.failed_count} 个` : '';
          message.warning(`以下机柜创建失败：${failedList}${more}`);
        }
        onClose();
      } else {
        await createCabinet.mutateAsync(values);
        message.success('创建成功');
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
      title={isEdit ? '编辑机柜' : batchMode ? '批量新增机柜' : '新增机柜'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={confirmLoading}
      destroyOnHidden
      width={batchMode ? 560 : 480}
    >
      <Form form={form} layout="vertical" autoComplete="off">
        {}
        {!isEdit && (
          <Form.Item>
            <Space>
              <Switch
                checked={batchMode}
                onChange={handleBatchModeChange}
                checkedChildren="批量"
                unCheckedChildren="单条"
              />
              <span style={{ color: '#8c8c8c', fontSize: 13 }}>
                {batchMode ? '支持逗号分隔和范围展开' : '逐个添加机柜'}
              </span>
            </Space>
          </Form.Item>
        )}

        {}
        <Form.Item
          name="cabinet_number"
          label={batchMode ? '机柜编号表达式' : '机柜名称'}
          rules={[
            { required: true, message: batchMode ? '请输入机柜编号表达式' : '请输入机柜名称' }
          ]}
        >
          <Input
            placeholder={batchMode ? '如：m11,m13,n10 或 h1-10 或 m01-05' : '请输入机柜名称/编号'}
            onChange={handleCabinetNumberChange}
          />
        </Form.Item>

        {}
        {batchMode && previewNumbers.length > 0 && (
          <Form.Item>
            <Alert
              type="info"
              showIcon={false}
              message={
                <div>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>
                    将创建 {previewNumbers.length} 个机柜：
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
          label="所属机房"
          rules={[{ required: true, message: '请选择所属机房' }]}
        >
          <Select placeholder="请选择机房" options={roomOptions} allowClear />
        </Form.Item>

        <Form.Item
          name="total_u"
          label="U位容量"
          rules={[{ required: true, message: '请输入U位容量' }]}
          initialValue={42}
        >
          <InputNumber min={1} max={50} style={{ width: '100%' }} placeholder="U位容量" />
        </Form.Item>

        {}
        {!batchMode && (
          <>
            <Form.Item name="location" label="机柜位置">
              <Input placeholder="机柜位置（可选）" />
            </Form.Item>

            <div style={{ display: 'flex', gap: 16 }}>
              <Form.Item
                name="row"
                label="行号"
                style={{ flex: 1 }}
                tooltip="机房平面图中的行坐标，从1开始。如：1、2、3"
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="如：1" />
              </Form.Item>
              <Form.Item
                name="col"
                label="列号"
                style={{ flex: 1 }}
                tooltip="机房平面图中的列坐标，从1开始。如：1、2、3"
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="如：1" />
              </Form.Item>
            </div>
          </>
        )}

        <Form.Item name="status" label="状态" initialValue={1}>
          <Select options={CABINET_STATUS_OPTIONS} placeholder="请选择状态" />
        </Form.Item>

        <Form.Item name="customer_id" label="租赁客户">
          <Select options={customerOptions} placeholder="整柜租赁客户（可选）" allowClear />
        </Form.Item>

        <Form.Item name="total_power" label="额定功率(W)">
          <InputNumber min={0} style={{ width: '100%' }} placeholder="额定功率" />
        </Form.Item>

        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} placeholder="机柜备注（可选）" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default CabinetForm;
