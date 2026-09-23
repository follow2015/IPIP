import { useConfirm } from '@/utils/confirm';

import { useState, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

interface AssetTabProps {
  device: Device;
}

function getWarrantyStatus(device: Device, t: TFunction<'device'>) {
  if (!device.warranty_end)
    return { label: t('asset.warranty.notSet'), color: 'default', icon: <ClockCircleOutlined /> };
  const end = new Date(ensureUtc(device.warranty_end));
  const now = new Date();
  const daysLeft = Math.ceil((end.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (daysLeft < 0)
    return { label: t('asset.warranty.expired'), color: 'red', icon: <ExclamationCircleOutlined /> };
  if (daysLeft <= 90)
    return {
      label: t('asset.warranty.expiring', { count: daysLeft }),
      color: 'orange',
      icon: <ExclamationCircleOutlined />
    };
  return {
    label: t('asset.warranty.active'),
    color: 'green',
    icon: <CheckCircleOutlined />
  };
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
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const warrantyStatus = getWarrantyStatus(device, t);
  const updateDevice = useUpdateDevice();
  const resetAsset = useBatchResetDeviceAsset();
  const message = useMessage();
  const edit = useDisclosure();
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
    edit.open();
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
      message.success(t('asset.message.updated'));
      edit.close();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleReset = useCallback(() => {
    confirm({
      title: t('asset.confirmResetTitle'),
      content: t('asset.confirmResetContent', { name: device.device_name }),
      okText: t('asset.confirmResetOk'),
      cancelText: tCommon('action.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await resetAsset.mutateAsync([device.id]);
          message.success(t('asset.message.resetSuccess'));
        } catch (err) {
          message.error(err instanceof Error ? err.message : t('asset.message.resetFailed'));
        }
      }
    });
  }, [t, tCommon, confirm, device.id, device.device_name, resetAsset]);

  return (
    <>
      {/* 操作按钮 */}
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button icon={<EditOutlined />} onClick={handleOpenEdit}>
          {tCommon('action.edit')}
        </Button>
        <Button danger icon={<UndoOutlined />} onClick={handleReset} loading={resetAsset.isPending}>
          {tCommon('action.reset')}
        </Button>
      </div>

      <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
        {/* 资产编号 */}
        <Descriptions.Item label={t('asset.field.assetNumber')}>
          {device.asset_number ?? '-'}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.warrantyStatus')}>
          <Tag color={warrantyStatus.color} icon={warrantyStatus.icon}>
            {warrantyStatus.label}
          </Tag>
        </Descriptions.Item>

        {/* 采购信息 */}
        <Descriptions.Item label={t('asset.field.supplier')}>{device.supplier ?? '-'}</Descriptions.Item>
        <Descriptions.Item label={t('asset.field.supplierContact')}>
          {device.supplier_contact ?? '-'}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.contractNumber')}>
          {device.contract_number ?? '-'}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.purchaseDate')}>
          {formatDate(device.purchase_date)}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.purchasePrice')}>
          {formatPrice(device.purchase_price)}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.invoiceNumber')}>
          {device.invoice_number ?? '-'}
        </Descriptions.Item>

        {/* 保修信息 */}
        <Descriptions.Item label={t('asset.field.warrantyType')}>
          {device.warranty_type ?? '-'}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.warrantyPeriod')}>
          {device.warranty_start || device.warranty_end
            ? `${formatDate(device.warranty_start)} ~ ${formatDate(device.warranty_end)}`
            : '-'}
        </Descriptions.Item>

        {/* 生命周期 */}
        <Descriptions.Item label={t('asset.field.onlineDate')}>
          {formatDate(device.online_date)}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.offlineDate')}>
          {formatDate(device.offline_date)}
        </Descriptions.Item>
        <Descriptions.Item label={t('asset.field.lifecycleYears')}>
          {device.lifecycle_years ? t('asset.field.years', { count: device.lifecycle_years }) : '-'}
        </Descriptions.Item>
        <Descriptions.Item label={tCommon('field.createdAt')}>
          {formatDateTime(device.created_at)}
        </Descriptions.Item>
      </Descriptions>

      {/* 编辑弹窗 */}
      <Modal
        title={t('asset.editTitle')}
        open={edit.isOpen}
        onOk={handleEditSubmit}
        onCancel={() => edit.close()}
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
