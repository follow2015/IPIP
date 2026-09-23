/**
 * 网卡端口标签页
 * - 网卡端口列表 + 编辑 + 批量删除
 * - 模板快速配置（复用 NicConfigFields 共用组件）
 * - 仅 server/other 设备
 */
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useConfirm } from '@/utils/confirm';
import { useTranslation } from 'react-i18next';
import { Table, Button, Space, Modal, Form, Input, InputNumber, Select } from 'antd';
import { AppstoreOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useDeviceNics,
  useUpdateNic,
  useDeleteNic,
  useBatchCreateNics,
  useBatchDeleteNics
} from '@/services/device-nic';
import { useComponentTemplates } from '@/services/component-template';
import NicConfigFields, { expandNicPorts } from '@/components/NicConfigFields';
import StatusTag from '@/components/StatusTag';
import { useMessage } from '@/hooks/useMessage';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import BatchActionBar from '@/components/BatchActionBar';
import { PORT_USAGE_STATUS_MAP } from '@/types/enums';
import type { DeviceNicPort } from '@/types/models';

interface NicTabProps {
  deviceId: number;
}

type NicOptionKey =
  | 'nic.portType.rj45'
  | 'nic.portType.sfp'
  | 'nic.portType.sfpPlus'
  | 'nic.portType.sfp28'
  | 'nic.portType.qsfpPlus'
  | 'nic.portType.qsfp28'
  | 'nic.portType.qsfp56'
  | 'nic.portType.qsfpdd'
  | 'nic.status.free'
  | 'nic.status.occupied'
  | 'nic.status.disabled';

const PORT_TYPE_OPTIONS: { labelKey: NicOptionKey; value: string }[] = [
  { labelKey: 'nic.portType.rj45', value: 'RJ45' },
  { labelKey: 'nic.portType.sfp', value: 'SFP' },
  { labelKey: 'nic.portType.sfpPlus', value: 'SFP+' },
  { labelKey: 'nic.portType.sfp28', value: 'SFP28' },
  { labelKey: 'nic.portType.qsfpPlus', value: 'QSFP+' },
  { labelKey: 'nic.portType.qsfp28', value: 'QSFP28' },
  { labelKey: 'nic.portType.qsfp56', value: 'QSFP56' },
  { labelKey: 'nic.portType.qsfpdd', value: 'QSFP-DD' }
];

const PORT_SPEED_OPTIONS = [
  { label: '100M', value: '100M' },
  { label: '1G', value: '1G' },
  { label: '10G', value: '10G' },
  { label: '25G', value: '25G' },
  { label: '40G', value: '40G' },
  { label: '100G', value: '100G' },
  { label: '400G', value: '400G' }
];

const PORT_STATUS_OPTIONS: { labelKey: NicOptionKey; value: string }[] = [
  { labelKey: 'nic.status.free', value: 'free' },
  { labelKey: 'nic.status.occupied', value: 'occupied' },
  { labelKey: 'nic.status.disabled', value: 'disabled' }
];

function NicTab({ deviceId }: NicTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const { data: nics, isLoading } = useDeviceNics(deviceId);
  const updateNic = useUpdateNic(deviceId);
  const deleteNic = useDeleteNic(deviceId);
  const batchCreateNics = useBatchCreateNics(deviceId);
  const message = useMessage();

  const { data: nicTemplates = [] } = useComponentTemplates('nic');

  const formDisclosure = useDisclosure();
  const [editingNic, setEditingNic] = useState<DeviceNicPort | null>(null);
  const [form] = Form.useForm();

  const template = useDisclosure();
  const [templateForm] = Form.useForm();

  const batch = useBatchSelection<DeviceNicPort>({ dataSource: nics ?? [] });

  const batchDeleteNics = useBatchDeleteNics(deviceId);

  const handleEdit = (record: DeviceNicPort) => {
    setEditingNic(record);
    form.setFieldsValue(record);
    formDisclosure.open();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingNic) {
        await updateNic.mutateAsync({ portId: editingNic.id, data: values });
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
      const res = await batchDeleteNics.mutateAsync({ port_ids: batch.selectedKeys.map(Number) });
      const deleted = res.data?.deleted.length ?? 0;
      const skipped = res.data?.skipped.length ?? 0;
      message.success(t('nic.message.deleted', { count: deleted }));
      if (skipped > 0) {
        message.warning(t('nic.message.skipped', { count: skipped }));
      }
      batch.clear();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('nic.message.batchDeleteFailed'));
    }
  };

  const handleTemplateSubmit = async () => {
    try {
      await templateForm.validateFields();
    } catch {
      return;
    }
    const values = templateForm.getFieldsValue();
    const nicPortsFormVal = values.nic_ports as { template_id?: number }[] | undefined;
    const ports = expandNicPorts(nicPortsFormVal, nicTemplates);
    if (ports.length === 0) {
      message.warning(t('nic.message.needTemplate'));
      return;
    }
    try {
      await batchCreateNics.mutateAsync({ ports });
      message.success(t('nic.message.created', { count: ports.length }));
      template.close();
      templateForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('nic.message.createFailed'));
    }
  };

  const columns = [
    { title: t('nic.column.displayName'), dataIndex: 'display_name', key: 'display_name' },
    { title: t('nic.column.nicIndex'), dataIndex: 'nic_number', key: 'nic_number', width: 80 },
    { title: t('nic.column.portIndex'), dataIndex: 'port_number', key: 'port_number', width: 80 },
    {
      title: t('nic.column.portName'),
      dataIndex: 'port_name',
      key: 'port_name',
      width: 120,
      render: (v: string) => v || '-'
    },
    {
      title: t('nic.column.portType'),
      dataIndex: 'port_type',
      key: 'port_type',
      width: 90,
      render: (v: string) => v || '-'
    },
    {
      title: t('nic.column.speed'),
      dataIndex: 'port_speed',
      key: 'port_speed',
      width: 80,
      render: (v: string) => v || '-'
    },
    {
      title: t('nic.column.portStatus'),
      dataIndex: 'port_status',
      key: 'port_status',
      width: 90,
      render: (v: string) => <StatusTag status={v} statusMap={PORT_USAGE_STATUS_MAP} />
    },
    {
      title: t('nic.column.description'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string) => v || '-'
    },
    {
      title: tCommon('field.actions'),
      key: 'action',
      width: 80,
      render: (_: unknown, record: DeviceNicPort) => (
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
                title: t('nic.confirmDelete'),
                okText: tCommon('action.delete'),
                okButtonProps: { danger: true },
                onOk: async () => {
                  try {
                    await deleteNic.mutateAsync(record.id);
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
      {/* 批量操作浮条（勾选后浮出，统一批量删除入口） */}
      <BatchActionBar count={batch.count} unit={t('nic.unit')} onClear={batch.clear}>
        <Button
          danger
          icon={<DeleteOutlined />}
          onClick={() =>
            confirm({
              title: t('nic.confirmBatchDelete', { count: batch.count }),
              okText: tCommon('action.delete'),
              okButtonProps: { danger: true },
              onOk: handleBatchDelete
            })
          }
        >
          {tCommon('action.batchDelete')}
        </Button>
      </BatchActionBar>

      {/* 操作栏 */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button
            icon={<AppstoreOutlined />}
            onClick={() => {
              template.open();
              templateForm.resetFields();
            }}
          >
            {t('nic.templateConfig')}
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={nics ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
        rowSelection={batch.rowSelection}
        scroll={{ x: 'max-content' }}
      />

      {/* ─── 编辑 Modal ─── */}
      <Modal
        title={t('nic.editTitle')}
        open={formDisclosure.isOpen}
        onOk={handleSubmit}
        onCancel={() => formDisclosure.close()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="nic_number"
            label={t('nic.column.nicIndex')}
            rules={[{ required: true, message: t('nic.field.nicIndexPlaceholder') }]}
          >
            <InputNumber min={1} max={8} style={{ width: '100%' }} placeholder={t('nic.field.nicIndexHint')} />
          </Form.Item>
          <Form.Item
            name="port_number"
            label={t('nic.column.portIndex')}
            rules={[{ required: true, message: t('nic.field.portIndexPlaceholder') }]}
          >
            <InputNumber min={1} max={16} style={{ width: '100%' }} placeholder={t('nic.field.portIndexHint')} />
          </Form.Item>
          <Form.Item name="port_name" label={t('nic.column.portName')}>
            <Input placeholder={t('nic.field.portNameHint')} />
          </Form.Item>
          <Form.Item name="port_type" label={t('nic.column.portType')}>
            <Select placeholder={tCommon('message.selectRequired')} options={PORT_TYPE_OPTIONS.map((o) => ({ label: t(o.labelKey), value: o.value }))} allowClear />
          </Form.Item>
          <Form.Item name="port_speed" label={t('nic.column.speed')}>
            <Select placeholder={tCommon('message.selectRequired')} options={PORT_SPEED_OPTIONS} allowClear />
          </Form.Item>
          <Form.Item name="port_status" label={t('nic.column.portStatus')}>
            <Select placeholder={tCommon('message.selectRequired')} options={PORT_STATUS_OPTIONS.map((o) => ({ label: t(o.labelKey), value: o.value }))} allowClear />
          </Form.Item>
          <Form.Item name="description" label={t('nic.column.description')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ─── 模板配置 Modal（复用 NicConfigFields） ─── */}
      <Modal
        title={t('nic.templateConfig')}
        open={template.isOpen}
        onCancel={() => template.close()}
        onOk={handleTemplateSubmit}
        okText={t('nic.confirmCreate')}
        confirmLoading={batchCreateNics.isPending}
        width={700}
        destroyOnHidden
      >
        <Form form={templateForm} layout="vertical" autoComplete="off">
          <NicConfigFields form={templateForm} />
        </Form>
      </Modal>
    </div>
  );
}

export default NicTab;
