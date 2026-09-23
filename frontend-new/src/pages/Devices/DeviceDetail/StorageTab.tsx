/**
 * 存储标签页
 * - 存储列表 + 编辑 + 批量删除
 * - 模板快速配置（复用 HardwareConfigFields 存储配置部分）
 * - 按存储类型容量汇总
 */
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Space, Modal, Form, Input, InputNumber, Select, Tag, Divider } from 'antd';
import DataTable, { DENSE_PAGINATION } from '@/components/DataTable';
import { useConfirm } from '@/utils/confirm';
import { AppstoreOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useDeviceStorageDetail,
  useCreateStorage,
  useUpdateStorage,
  useDeleteStorage,
  useBatchDeleteStorage
} from '@/services/device-storage';
import HardwareConfigFields, {
  buildStorageList,
  type StorageItem
} from '@/components/HardwareConfigFields';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import type { DeviceStorageDetail } from '@/types/models';

interface StorageTabProps {
  deviceId: number;
}

type StorageStatusKey = 'storage.status.normal' | 'storage.status.fault' | 'storage.status.warning';

function formatGb(gb: number): string {
  if (gb >= 1024) return `${(gb / 1024).toFixed(1)}TB`;
  return `${Math.round(gb)}GB`;
}

function StorageTab({ deviceId }: StorageTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const { data: storageList, isLoading } = useDeviceStorageDetail(deviceId);
  const createStorage = useCreateStorage(deviceId);
  const updateStorage = useUpdateStorage(deviceId);
  const deleteStorage = useDeleteStorage(deviceId);
  const message = useMessage();

  const formDisclosure = useDisclosure();
  const [editingStorage, setEditingStorage] = useState<DeviceStorageDetail | null>(null);
  const [form] = Form.useForm();

  const template = useDisclosure();
  const [templateForm] = Form.useForm();

  const details: DeviceStorageDetail[] = useMemo(() => storageList ?? [], [storageList]);

  const batch = useBatchSelection<DeviceStorageDetail>({ dataSource: details });

  const batchDeleteStorage = useBatchDeleteStorage(deviceId);

  const handleEdit = (record: DeviceStorageDetail) => {
    setEditingStorage(record);
    form.setFieldsValue(record);
    formDisclosure.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingStorage) {
        await updateStorage.mutateAsync({ storageId: editingStorage.id, data: values });
        message.success(tCommon('message.updateSuccess'));
      }
      formDisclosure.close();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleBatchDelete = async () => {
    if (batch.count === 0) return;
    try {
      const res = await batchDeleteStorage.mutateAsync({
        storage_ids: batch.selectedKeys.map(Number)
      });
      const deleted = res.data?.deleted.length ?? 0;
      message.success(t('storage.message.deleted', { count: deleted }));
      batch.clear();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('storage.message.batchDeleteFailed'));
    }
  };

  const handleTemplateSubmit = async () => {
    try {
      await templateForm.validateFields();
    } catch {
      return;
    }
    const values = templateForm.getFieldsValue();
    const storageItems = values.storage_items as StorageItem[] | undefined;
    const list = buildStorageList(storageItems);
    if (list.length === 0) {
      message.warning(t('storage.message.needOneConfig'));
      return;
    }
    try {
      for (const item of list) {
        await createStorage.mutateAsync(item);
      }
      message.success(t('storage.message.created', { count: list.length }));
      template.close();
      templateForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('storage.message.createFailed'));
    }
  };

  const storageSummary = useMemo(() => {
    if (details.length === 0) return null;
    let totalGb = 0;
    const byType: Record<string, { count: number; totalGb: number }> = {};
    for (const item of details) {
      const gb = item.capacity_gb ?? 0;
      totalGb += gb;
      const type = item.storage_type || tCommon('field.unknown');
      if (!byType[type]) byType[type] = { count: 0, totalGb: 0 };
      byType[type].count += 1;
      byType[type].totalGb += gb;
    }
    return { totalGb, byType };
  }, [details, tCommon]);

  const columns = [
    {
      title: tCommon('field.type'),
      dataIndex: 'storage_type',
      key: 'storage_type',
      width: 80,
      render: (v: string) => (
        <Tag color={v === 'SSD' ? 'blue' : v === 'NVMe' ? 'green' : 'orange'}>{v}</Tag>
      )
    },
    { title: t('storage.column.capacity'), dataIndex: 'capacity', key: 'capacity', width: 80 },
    {
      title: t('storage.column.interface'),
      dataIndex: 'interface_type',
      key: 'interface_type',
      width: 80,
      render: (v: string) => v || '-'
    },
    {
      title: t('storage.column.slot'),
      dataIndex: 'slot_number',
      key: 'slot_number',
      width: 70,
      render: (v: number) => v ?? '-'
    },
    {
      title: t('storage.column.vendor'),
      dataIndex: 'manufacturer',
      key: 'manufacturer',
      width: 100,
      render: (v: string) => v || '-'
    },
    {
      title: t('storage.column.model'),
      dataIndex: 'model',
      key: 'model',
      width: 100,
      render: (v: string) => v || '-'
    },
    {
      title: t('storage.column.serial'),
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 120,
      render: (v: string) => v || '-'
    },
    {
      title: tCommon('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 70,
      render: (v: string) => {
        const map: Record<string, { color: string; labelKey: StorageStatusKey }> = {
          normal: { color: 'green', labelKey: 'storage.status.normal' },
          fault: { color: 'red', labelKey: 'storage.status.fault' },
          warning: { color: 'orange', labelKey: 'storage.status.warning' }
        };
        const info = map[v];
        return info ? <Tag color={info.color}>{t(info.labelKey)}</Tag> : v || '-';
      }
    },
    {
      title: tCommon('field.actions'),
      key: 'action',
      width: 80,
      render: (_: unknown, record: DeviceStorageDetail) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              confirm({
                title: t('storage.confirmDelete'),
                okText: tCommon('action.delete'),
                okButtonProps: { danger: true },
                onOk: async () => {
                  try {
                    await deleteStorage.mutateAsync(record.id);
                    message.success(tCommon('message.deleteSuccess'));
                  } catch (err) {
                    message.error(err instanceof Error ? err.message : tCommon('message.deleteFailed'));
                  }
                }
              })
            }
          />
        </Space>
      )
    }
  ];

  return (
    <div>
      {/* 存储容量汇总 */}
      {storageSummary && storageSummary.totalGb > 0 && (
        <div
          style={{
            marginBottom: 16,
            padding: '10px 16px',
            background: '#fafafa',
            borderRadius: 6,
            border: '1px solid #f0f0f0'
          }}
        >
          <span style={{ fontWeight: 500, fontSize: 14 }}>
            {t('storage.totalCapacity', { capacity: formatGb(storageSummary.totalGb) })}
          </span>
          <Divider orientation="vertical" />
          {Object.entries(storageSummary.byType).map(([type, info]) => (
            <span key={type} style={{ marginRight: 20 }}>
              <Tag
                color={
                  type === 'SSD' ? 'blue' : type === 'NVME' || type === 'NVMe' ? 'green' : 'orange'
                }
              >
                {type}
              </Tag>
              {t('storage.blockCount', { count: info.count, capacity: formatGb(info.totalGb) })}
            </span>
          ))}
        </div>
      )}

      <BatchActionBar count={batch.count} unit={t('storage.unit')} onClear={batch.clear}>
        <Button
          danger
          icon={<DeleteOutlined />}
          onClick={() =>
            confirm({
              title: t('storage.confirmBatchDelete', { count: batch.count }),
              okText: tCommon('action.delete'),
              okButtonProps: { danger: true },
              onOk: handleBatchDelete
            })
          }
        >
          {tCommon('action.batchDelete')}
        </Button>
      </BatchActionBar>

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button
            icon={<AppstoreOutlined />}
            onClick={() => {
              template.open();
              templateForm.resetFields();
            }}
          >
            {t('storage.templateConfig')}
          </Button>
        </Space>
      </div>

      <DataTable
        columns={columns}
        dataSource={details}
        rowKey="id"
        loading={isLoading}
        size="small"
        scroll={{ x: 900 }}
        rowSelection={batch.rowSelection}
        searchable={false}
        showCard={false}
        pagination={false}
      />

      {/* ─── 编辑 Modal ─── */}
      <Modal
        title={t('storage.editTitle')}
        open={formDisclosure.isOpen}
        onOk={handleSubmit}
        onCancel={() => formDisclosure.close()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="storage_type"
            label={t('storage.field.type')}
            rules={[{ required: true, message: t('storage.selectType') }]}
          >
            <Select
              placeholder={tCommon('message.selectRequired')}
              options={[
                { label: 'SSD', value: 'SSD' },
                { label: 'HDD', value: 'HDD' },
                { label: 'NVMe', value: 'NVMe' }
              ]}
            />
          </Form.Item>
          <Form.Item
            name="capacity"
            label={t('storage.column.capacity')}
            rules={[{ required: true, message: t('storage.field.capacityPlaceholder') }]}
          >
            <Input placeholder={t('storage.field.capacityHint')} />
          </Form.Item>
          <Form.Item name="capacity_gb" label={t('storage.field.capacityGb')} extra={t('storage.field.capacityGbHint')}>
            <InputNumber min={1} style={{ width: '100%' }} placeholder={t('storage.field.capacityGbConvertHint')} />
          </Form.Item>
          <Form.Item name="interface_type" label={t('storage.column.interface')}>
            <Select
              placeholder={tCommon('message.selectRequired')}
              options={[
                { label: 'SATA', value: 'SATA' },
                { label: 'SAS', value: 'SAS' },
                { label: 'NVMe', value: 'NVMe' }
              ]}
              allowClear
            />
          </Form.Item>
          <Form.Item name="slot_number" label={t('storage.column.slot')}>
            <InputNumber min={0} style={{ width: '100%' }} placeholder={t('storage.column.slot')} />
          </Form.Item>
          <Form.Item name="manufacturer" label={t('storage.column.vendor')}>
            <Input placeholder={t('storage.field.vendorHint')} />
          </Form.Item>
          <Form.Item name="model" label={t('storage.column.model')}>
            <Input placeholder={t('storage.field.modelHint')} />
          </Form.Item>
          <Form.Item name="serial_number" label={t('storage.column.serial')}>
            <Input placeholder={t('storage.column.serial')} />
          </Form.Item>
          <Form.Item name="status" label={tCommon('field.status')}>
            <Select
              placeholder={tCommon('message.selectRequired')}
              options={[
                { label: t('storage.status.normal'), value: 'normal' },
                { label: t('storage.status.fault'), value: 'fault' },
                { label: t('storage.status.warning'), value: 'warning' }
              ]}
              allowClear
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* ─── 模板配置 Modal（复用 HardwareConfigFields 存储部分） ─── */}
      <Modal
        title={t('storage.templateTitle')}
        open={template.isOpen}
        onCancel={() => template.close()}
        onOk={handleTemplateSubmit}
        okText={t('storage.confirmCreate')}
        confirmLoading={createStorage.isPending}
        width={700}
        destroyOnHidden
      >
        <Form form={templateForm} layout="vertical" autoComplete="off">
          <HardwareConfigFields form={templateForm} storageOnly />
        </Form>
      </Modal>
    </div>
  );
}

export default StorageTab;
