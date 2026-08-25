/**
 * 批量修改资产信息弹窗
 * - 资产编号仅支持自动生成（开关默认关闭，开启后为每个设备生成不同编号）
 * - 其他资产字段统一设置
 */
import { useState } from 'react';
import { Modal, Form } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useBatchUpdateDeviceAsset, type BatchUpdateAssetRequest } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import AssetInfoFields from '@/components/AssetInfoFields';

const ASSET_DATE_FIELDS = [
  'purchase_date',
  'warranty_start',
  'warranty_end',
  'online_date',
  'offline_date'
] as const;

function serializeAssetDate(value: unknown): unknown {
  if (dayjs.isDayjs(value)) {
    return (value as Dayjs).format('YYYY-MM-DD');
  }
  return value;
}

interface BatchUpdateAssetModalProps {
  open: boolean;
  deviceIds: number[];
  onClose: (refresh?: boolean) => void;
}

function BatchUpdateAssetModal({ open, deviceIds, onClose }: BatchUpdateAssetModalProps) {
  const [form] = Form.useForm();
  const batchUpdateAsset = useBatchUpdateDeviceAsset();
  const message = useMessage();
  const [autoGenerate, setAutoGenerate] = useState(false);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const serialized: Record<string, unknown> = { ...values };
      for (const f of ASSET_DATE_FIELDS) {
        if (f in serialized) serialized[f] = serializeAssetDate(serialized[f]);
      }
      const payload: BatchUpdateAssetRequest = {
        ids: deviceIds,
        auto_generate_asset_number: autoGenerate,
        ...serialized
      };
      const result = await batchUpdateAsset.mutateAsync(payload);
      message.success(`更新 ${result.data.updated} 台，跳过 ${result.data.skipped} 台`);
      onClose(true);
      form.resetFields();
      setAutoGenerate(false);
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setAutoGenerate(false);
    onClose();
  };

  return (
    <Modal
      title={`批量修改资产信息（${deviceIds.length} 台设备）`}
      open={open}
      onOk={handleSubmit}
      onCancel={handleCancel}
      confirmLoading={batchUpdateAsset.isPending}
      width={720}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" preserve={false}>
        <AssetInfoFields
          form={form}
          assetNumberMode="auto-only"
          autoGenerate={autoGenerate}
          onAutoGenerateChange={setAutoGenerate}
        />
      </Form>
    </Modal>
  );
}

export default BatchUpdateAssetModal;
