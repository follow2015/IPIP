import { confirm } from '@/utils/confirm';

import { useState, useCallback } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { Descriptions, Tag, Button, Space, Form, Modal } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  EditOutlined,
  UndoOutlined
} from '@ant-design/icons';
import type { Device } from '@/types/models';
import { formatDateTime, formatDate, ensureUtc } from '@/utils/format';
import {
  useUpdateDevice,
  useBatchResetDeviceAsset,
  type UpdateDeviceRequest
} from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import AssetInfoFields, { generateAssetNumber } from '@/components/AssetInfoFields';

interface AssetTabProps {
  device: Device;
}

function getWarrantyStatus(device: Device) {
  if (!device.warranty_end)
    return { label: '未设置', color: 'default', icon: <ClockCircleOutlined /> };
  const end = new Date(ensureUtc(device.warranty_end));
  const now = new Date();
  const daysLeft = Math.ceil((end.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (daysLeft < 0) return { label: '已过期', color: 'red', icon: <ExclamationCircleOutlined /> };
  if (daysLeft <= 90)
    return {
      label: `即将到期(${daysLeft}天)`,
      color: 'orange',
      icon: <ExclamationCircleOutlined />
    };
  return { label: '保修中', color: 'green', icon: <CheckCircleOutlined /> };
}

function formatPrice(price: number | null | undefined): string {
  if (price == null) return '-';
  return `¥${Number(price).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const ASSET_DATE_KEYS = new Set([
  'purchase_date',
  'warranty_start',
  'warranty_end',
  'online_date',
  'offline_date'
]);

function serializeAssetDate(value: unknown): unknown {
  if (dayjs.isDayjs(value)) {
    return (value as Dayjs).format('YYYY-MM-DD');
  }
  return value;
}

function AssetTab({ device }: AssetTabProps) {
  const warrantyStatus = getWarrantyStatus(device);
  const updateDevice = useUpdateDevice();
  const resetAsset = useBatchResetDeviceAsset();
  const message = useMessage();
  const [editOpen, setEditOpen] = useState(false);
  const [editForm] = Form.useForm();
  const [autoGenerate, setAutoGenerate] = useState(false);

  const handleOpenEdit = useCallback(() => {
    editForm.setFieldsValue({
      asset_number: device.asset_number ?? undefined,
      supplier: device.supplier ?? undefined,
      supplier_contact: device.supplier_contact ?? undefined,
      contract_number: device.contract_number ?? undefined,
      purchase_date: device.purchase_date ? dayjs(ensureUtc(device.purchase_date)) : undefined,
      purchase_price: device.purchase_price ?? undefined,
      invoice_number: device.invoice_number ?? undefined,
      warranty_type: device.warranty_type ?? undefined,
      warranty_start: device.warranty_start ? dayjs(ensureUtc(device.warranty_start)) : undefined,
      warranty_end: device.warranty_end ? dayjs(ensureUtc(device.warranty_end)) : undefined,
      online_date: device.online_date ? dayjs(ensureUtc(device.online_date)) : undefined,
      offline_date: device.offline_date ? dayjs(ensureUtc(device.offline_date)) : undefined,
      lifecycle_years: device.lifecycle_years ?? undefined
    });
    setAutoGenerate(false);
    setEditOpen(true);
  }, [device, editForm]);

  const handleEditSubmit = async () => {
    try {
      const values = await editForm.validateFields();
      const payload: UpdateDeviceRequest = { id: device.id };

      if (autoGenerate) {
        payload.asset_number = generateAssetNumber();
      } else if (values.asset_number !== undefined) {
        payload.asset_number = values.asset_number || null;
      }

      const assetKeys = [
        'supplier',
        'supplier_contact',
        'contract_number',
        'purchase_date',
        'purchase_price',
        'invoice_number',
        'warranty_start',
        'warranty_end',
        'warranty_type',
        'online_date',
        'offline_date',
        'lifecycle_years'
      ] as const;
      for (const key of assetKeys) {
        if (values[key] !== undefined) {
          const v = values[key];
          (payload as unknown as Record<string, unknown>)[key] = ASSET_DATE_KEYS.has(key)
            ? (serializeAssetDate(v) ?? null)
            : (v ?? null);
        }
      }

      await updateDevice.mutateAsync(payload);
      message.success('资产信息已更新');
      setEditOpen(false);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleReset = useCallback(() => {
    confirm({
      title: '重置资产信息',
      content: `确定要清空设备「${device.device_name}」的所有资产信息吗？此操作不可恢复。`,
      okText: '确定重置',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await resetAsset.mutateAsync([device.id]);
          message.success('资产信息已重置');
        } catch (err) {
          message.error(err instanceof Error ? err.message : '重置失败');
        }
      }
    });
  }, [device.id, device.device_name, resetAsset]);

  return (
    <>
      {/* 操作按钮 */}
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button icon={<EditOutlined />} onClick={handleOpenEdit}>
          编辑
        </Button>
        <Button danger icon={<UndoOutlined />} onClick={handleReset} loading={resetAsset.isPending}>
          重置
        </Button>
      </div>

      <Descriptions column={2} bordered size="small">
        {/* 资产编号 */}
        <Descriptions.Item label="资产编号">{device.asset_number ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="保修状态">
          <Tag color={warrantyStatus.color} icon={warrantyStatus.icon}>
            {warrantyStatus.label}
          </Tag>
        </Descriptions.Item>

        {/* 采购信息 */}
        <Descriptions.Item label="供应商">{device.supplier ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="供应商联系人">{device.supplier_contact ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="合同编号">{device.contract_number ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="采购日期">{formatDate(device.purchase_date)}</Descriptions.Item>
        <Descriptions.Item label="采购价格">{formatPrice(device.purchase_price)}</Descriptions.Item>
        <Descriptions.Item label="发票号码">{device.invoice_number ?? '-'}</Descriptions.Item>

        {/* 保修信息 */}
        <Descriptions.Item label="保修类型">{device.warranty_type ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="保修期限">
          {device.warranty_start || device.warranty_end
            ? `${formatDate(device.warranty_start)} ~ ${formatDate(device.warranty_end)}`
            : '-'}
        </Descriptions.Item>

        {/* 生命周期 */}
        <Descriptions.Item label="上线日期">{formatDate(device.online_date)}</Descriptions.Item>
        <Descriptions.Item label="下线日期">{formatDate(device.offline_date)}</Descriptions.Item>
        <Descriptions.Item label="预计使用年限">
          {device.lifecycle_years ? `${device.lifecycle_years}年` : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatDateTime(device.created_at)}</Descriptions.Item>
      </Descriptions>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑资产信息"
        open={editOpen}
        onOk={handleEditSubmit}
        onCancel={() => setEditOpen(false)}
        confirmLoading={updateDevice.isPending}
        width={680}
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <AssetInfoFields
            form={editForm}
            assetNumberMode="manual-with-switch"
            autoGenerate={autoGenerate}
            onAutoGenerateChange={setAutoGenerate}
          />
        </Form>
      </Modal>
    </>
  );
}

export default AssetTab;
