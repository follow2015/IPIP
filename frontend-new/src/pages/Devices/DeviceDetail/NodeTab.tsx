import { useConfirm } from '@/utils/confirm';
import { useState, useEffect } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import type { DragEvent } from 'react';
import {
  Button,
  Space,
  Form,
  Input,
  InputNumber,
  Select,
  Tag,
  Alert,
  Row,
  Col,
  Card,
  Tooltip,
  Modal
} from 'antd';
import { PlusOutlined, DeleteOutlined, FullscreenOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  useDeviceList,
  useCreateDevice,
  useDeleteDevice,
  useUpdateDevice,
  useDeviceDetail,
  useSwapNodePositions
} from '@/services/device';
import { DeviceStatusCode } from '@/types/enums';
import { getDeviceStatusMeta, getDeviceStatusOptions } from '@/types/statusMeta';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';
import DataTable from '@/components/DataTable';
import type { Device } from '@/types/models';
import HardwareConfigFields, {
  buildStorageSummary,
  buildStorageList,
  type StorageItem
} from '@/components/HardwareConfigFields';
import NicConfigFields, { expandNicPorts } from '@/components/NicConfigFields';
import { useComponentTemplates } from '@/services/component-template';

interface NodeTabProps {
  deviceId: number;
  deviceName?: string;
  totalNodes?: number;
  nodeRows?: number;
  nodeCols?: number;
}

function NodeTab({ deviceId, deviceName, totalNodes, nodeRows, nodeCols }: NodeTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
  const navigate = useNavigate();
  const message = useMessage();

  const { data, isLoading } = useDeviceList({ parent_device_id: deviceId, per_page: 999 });
  const createDevice = useCreateDevice();
  const deleteDevice = useDeleteDevice();
  const updateDevice = useUpdateDevice();
  const swapNodePositions = useSwapNodePositions(deviceId);

  const [dragSource, setDragSource] = useState<number | null>(null);
  const [dragOverTarget, setDragOverTarget] = useState<number | null>(null);
  const [swapping, setSwapping] = useState(false);

  const formDisclosure = useDisclosure();
  const [form] = Form.useForm();

  const fill = useDisclosure();
  const [fillForm] = Form.useForm();

  const { data: chassisDetail } = useDeviceDetail(deviceId);

  const { data: nicComponentTemplates } = useComponentTemplates('nic');

  const existingNodeCount = data?.items?.length ?? 0;
  const maxTotal = totalNodes ?? (nodeRows && nodeCols ? nodeRows * nodeCols : 0);
  const vacantCount = Math.max(0, maxTotal - existingNodeCount);

  const watchedNodePosition = Form.useWatch('node_position', form);
  useEffect(() => {
    if (!formDisclosure.isOpen || !watchedNodePosition || !deviceName) return;
    const pattern = chassisDetail?.node_naming_pattern || '{chassis}-Node{pos}';
    const nodeCols = chassisDetail?.node_cols || 1;
    const row = Math.ceil(watchedNodePosition / nodeCols);
    const col = ((watchedNodePosition - 1) % nodeCols) + 1;
    const newName = pattern
      .replace('{chassis}', deviceName)
      .replace('{NAME}', deviceName)
      .replace('{pos}', String(watchedNodePosition))
      .replace('{POS}', String(watchedNodePosition))
      .replace('{row}', String(row))
      .replace('{ROW}', String(row))
      .replace('{col}', String(col))
      .replace('{COL}', String(col));
    form.setFieldValue('device_name', newName);
    form.setFieldValue('notes', t('node.notesTemplate', { name: deviceName, position: watchedNodePosition }));
  }, [formDisclosure.isOpen, watchedNodePosition, deviceName, chassisDetail, form, t]);

  const handleAdd = () => {
    if (vacantCount === 0) {
      message.info(t('node.positionFull'));
      return;
    }
    form.resetFields();
    const currentCount = data?.items?.length ?? 0;
    form.setFieldsValue({
      device_type: 'server',
      device_subtype: 'node',
      parent_device_id: deviceId,
      node_position: currentCount + 1,
      device_name: deviceName ? `${deviceName}-Node${currentCount + 1}` : '',
      status: DeviceStatusCode.AVAILABLE
    });
    formDisclosure.open();
  };

  const handleDelete = (record: Device) => {
    confirm({
      title: tCommon('confirm.deleteTitle'),
      content: t('node.deleteContent', { name: record.device_name }),
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(record.id);
          message.success(tCommon('message.deleteSuccess'));
        } catch (err) {
          message.error(err instanceof Error ? err.message : tCommon('message.deleteFailed'));
        }
      }
    });
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      const storageItems: StorageItem[] = values.storage_items ?? [];
      const storageSummary = buildStorageSummary(storageItems);
      const storageList = buildStorageList(storageItems);
      const nicPorts = expandNicPorts(values.nic_ports, nicComponentTemplates ?? []);

      await createDevice.mutateAsync({
        ...values,
        storage_summary: storageSummary || values.storage_summary,
        storage_items: storageList.length > 0 ? storageList : undefined,
        nic_ports: nicPorts.length > 0 ? nicPorts : undefined
      });
      message.success(t('node.createSuccess'));
      formDisclosure.close();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleFillOpen = () => {
    if (vacantCount === 0) {
      message.info(t('node.noVacant'));
      return;
    }
    fillForm.resetFields();
    fillForm.setFieldsValue({
      fill_count: vacantCount
    });
    fill.open();
  };

  const handleFillSubmit = async () => {
    try {
      const values = await fillForm.validateFields();
      const fillCount = values.fill_count as number;

      if (fillCount <= 0) {
        message.warning(t('node.countMustPositive'));
        return;
      }
      if (fillCount > vacantCount) {
        message.warning(t('node.countExceed', { count: vacantCount }));
        return;
      }

      const storageItems: StorageItem[] = values.storage_items ?? [];
      const storageSummary = buildStorageSummary(storageItems);
      const storageList = buildStorageList(storageItems);
      const nicPorts = expandNicPorts(values.nic_ports, nicComponentTemplates ?? []);

      const nodeHardware = {
        cpu: values.cpu || undefined,
        cpu_way: values.cpu_way || undefined,
        cpu_cores: values.cpu_cores || undefined,
        cpu_template_id: values.cpu_template_id || undefined,
        memory: values.memory || undefined,
        memory_size_gb: values.memory_size_gb || undefined,
        memory_template_id: values.memory_template_id || undefined,
        memory_dimm_count: values.memory_dimm_count || undefined,
        storage_summary: storageSummary || undefined
      };

      await updateDevice.mutateAsync({
        id: deviceId,
        auto_create_nodes: true,
        node_hardware: nodeHardware,
        storage_items: storageList.length > 0 ? storageList : undefined,
        nic_ports: nicPorts.length > 0 ? nicPorts : undefined
      });

      message.success(t('node.generated', { count: fillCount }));
      fill.close();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const columns = [
    {
      title: t('node.column.position'),
      dataIndex: 'node_position',
      key: 'node_position',
      width: 90,
      render: (v: number | null) => v ?? '-'
    },
    {
      title: t('node.column.name'),
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: Device) => (
        <Button type="link" size="small" onClick={() => navigate(`/devices/${record.id}#basic`)}>
          {name}
        </Button>
      )
    },
    {
      title: tCommon('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: number) => {
        const info = getDeviceStatusMeta(v, t);
        return <Tag color={info?.color}>{info?.label ?? tCommon('field.unknown')}</Tag>;
      }
    },
    {
      title: t('node.column.hostname'),
      dataIndex: 'hostname',
      key: 'hostname',
      render: (v: string | null) => v ?? '-'
    },
    { title: 'CPU', dataIndex: 'cpu', key: 'cpu', render: (v: string | null) => v ?? '-' },
    {
      title: t('node.column.memory'),
      key: 'memory',
      render: (_: unknown, r: Device) => {
        const total = r.memory_size_gb;
        const count = r.memory_dimm_count;
        const single = total && count ? Math.round(total / count) : undefined;
        return (
          <div>
            <div>{r.memory ? `${r.memory}${count ? ` ×${count}` : ''}` : '-'}</div>
            {total ? (
              <div style={{ fontSize: 12, color: '#888', lineHeight: 1.6 }}>
                {single ? t('node.memorySummary', { single, count }) : ''}
                {total}GB
              </div>
            ) : null}
          </div>
        );
      }
    },
    {
      title: t('node.column.os'),
      dataIndex: 'os_version',
      key: 'os_version',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: tCommon('field.actions'),
      key: 'action',
      width: 80,
      render: (_: unknown, record: Device) => renderNodeActions(record)
    }
  ];

  const renderNodeActions = (record: Device) => (
    <Button
      type="link"
      size="small"
      danger
      icon={<DeleteOutlined />}
      onClick={() => handleDelete(record)}
    />
  );

  const renderNodeCard = (r: Device) => {
    const statusInfo = getDeviceStatusMeta(r.status, t);
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <Space size={8} wrap>
          <Button
            type="link"
            size="small"
            style={{ padding: 0 }}
            onClick={() => navigate(`/devices/${r.id}#basic`)}
          >
            {r.device_name}
          </Button>
          <Tag color={statusInfo?.color}>{statusInfo?.label ?? tCommon('field.unknown')}</Tag>
        </Space>
        <div style={{ fontSize: 12, color: '#666' }}>
          {t('node.column.position')}: {r.node_position ?? '-'}
        </div>
        <div style={{ fontSize: 12, color: '#666' }}>
          {r.hostname ?? '-'} · CPU: {r.cpu ?? '-'}
        </div>
        <div style={{ fontSize: 12, color: '#666' }}>{r.os_version ?? '-'}</div>
        {renderNodeActions(r)}
      </div>
    );
  };

  const handleSwapDrop = async (sourcePos: number, targetPos: number) => {
    if (sourcePos === targetPos) return;
    setSwapping(true);
    try {
      await swapNodePositions.mutateAsync({
        source_position: sourcePos,
        target_position: targetPos
      });
    } catch (err) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        t('node.message.swapFailed');
      message.error(msg);
    } finally {
      setSwapping(false);
      setDragSource(null);
      setDragOverTarget(null);
    }
  };

  const renderNodeGrid = () => {
    if (!nodeRows || !nodeCols) return null;
    const nodes = data?.items ?? [];
    const total = nodeRows * nodeCols;
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 8, color: '#8c8c8c', fontSize: 12 }}>
          {t('node.layout', {
            rows: nodeRows,
            cols: nodeCols,
            total,
            used: existingNodeCount,
            vacant: vacantCount
          })}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${nodeCols}, 1fr)`, gap: 4 }}>
          {Array.from({ length: total }, (_, idx) => {
            const row = Math.floor(idx / nodeCols) + 1;
            const col = (idx % nodeCols) + 1;
            const pos = idx + 1;
            const node = nodes.find((n) => n.node_position === pos);
            const isSource = dragSource === pos;
            const isTarget = dragOverTarget === pos && dragSource !== null && dragSource !== pos;
            return (
              <div
                key={idx}
                draggable={!!node}
                onDragStart={(e: DragEvent<HTMLDivElement>) => {
                  if (!node) return;
                  setDragSource(pos);
                  e.dataTransfer.effectAllowed = 'move';
                  e.dataTransfer.setData('text/plain', String(pos));
                }}
                onDragOver={(e: DragEvent<HTMLDivElement>) => {
                  if (dragSource === null || dragSource === pos) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = 'move';
                  if (dragOverTarget !== pos) setDragOverTarget(pos);
                }}
                onDragLeave={(_e: DragEvent<HTMLDivElement>) => {
                  if (dragOverTarget === pos) setDragOverTarget(null);
                }}
                onDrop={(e: DragEvent<HTMLDivElement>) => {
                  e.preventDefault();
                  const src = dragSource ?? Number(e.dataTransfer.getData('text/plain'));
                  if (src && src !== pos) {
                    void handleSwapDrop(src, pos);
                  } else {
                    setDragSource(null);
                    setDragOverTarget(null);
                  }
                }}
                onDragEnd={() => {
                  setDragSource(null);
                  setDragOverTarget(null);
                }}
                style={{
                  border: '1px solid #d9d9d9',
                  borderRadius: 4,
                  padding: '4px 8px',
                  textAlign: 'center',
                  fontSize: 12,
                  cursor: node ? (swapping ? 'wait' : 'grab') : 'default',
                  background: isTarget ? '#e6f4ff' : node ? '#f6ffed' : '#fafafa',
                  borderColor: isTarget ? '#1677ff' : node ? '#b7eb8f' : '#d9d9d9',
                  opacity: isSource ? 0.4 : 1,
                  transition: 'background 0.15s, border-color 0.15s, opacity 0.15s',
                  userSelect: 'none'
                }}
                onClick={() => node && !dragSource && navigate(`/devices/${node.id}#basic`)}
                title={
                  node
                    ? t('node.dragTooltip', { name: node.device_name })
                    : t('node.vacantSlot', { row, col })
                }
              >
                {node ? node.device_name : `R${row}C${col}`}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div>
      {/* 提示 banner：始终显示，引导用户到编辑机箱处操作 */}
      <Alert
        type="info"
        message={t('node.regenerateHint')}
        style={{ marginBottom: 12 }}
        showIcon
        banner
      />

      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}
      >
        <Space>
          {vacantCount > 0 && (
            <Tooltip title={t('node.fillTooltip', { count: vacantCount })}>
              <Button icon={<FullscreenOutlined />} onClick={handleFillOpen}>
                {t('node.fillButton')}
              </Button>
            </Tooltip>
          )}
        </Space>
        <Tooltip
          title={vacantCount === 0 ? t('node.chassisFull') : t('node.addChildTooltip')}
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAdd}
            disabled={vacantCount === 0}
          >
            {t('node.addButton')}
          </Button>
        </Tooltip>
      </div>
      {renderNodeGrid()}
      <DataTable
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
        searchable={false}
        showCard={false}
        mobileCardMode
        cardRender={renderNodeCard}
        scroll={{ x: 'max-content' }}
      />

      {/* 新增节点弹窗 */}
      <Modal
        title={t('node.addButton')}
        open={formDisclosure.isOpen}
        onOk={handleSubmit}
        onCancel={() => formDisclosure.close()}
        confirmLoading={createDevice.isPending}
        width={780}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="device_type" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="device_subtype" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="parent_device_id" hidden>
            <InputNumber />
          </Form.Item>

          <Form.Item
            name="device_name"
            label={t('node.field.name')}
            rules={[{ required: true, message: t('node.field.namePlaceholder') }]}
          >
            <Input placeholder={t('node.field.nameHint')} />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                name="node_position"
                label={t('node.field.position')}
                rules={[{ required: true, message: t('node.field.positionPlaceholder') }]}
              >
                <InputNumber
                  min={1}
                  max={totalNodes ?? 128}
                  style={{ width: '100%' }}
                  placeholder={t('node.field.positionHint')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="status" label={tCommon('field.status')}>
                <Select
                  placeholder={tCommon('message.selectRequired')}
                  options={getDeviceStatusOptions(t)}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="hostname" label={t('node.field.hostname')}>
                <Input placeholder={t('node.field.hostname')} />
              </Form.Item>
            </Col>
          </Row>

          <Card
            title={t('node.field.hardware')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <HardwareConfigFields form={form} showIpmi />
          </Card>
          <Card
            title={t('node.field.nic')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <NicConfigFields form={form} />
          </Card>
        </Form>
      </Modal>

      {/* 填满空余节点弹窗 */}
      <Modal
        title={t('node.generateTitle')}
        open={fill.isOpen}
        onOk={handleFillSubmit}
        onCancel={() => fill.close()}
        confirmLoading={updateDevice.isPending}
        width={780}
        destroyOnHidden
      >
        <Form form={fillForm} layout="vertical">
          <Alert
            type="info"
            message={t('node.generateDesc', {
          total: maxTotal,
          existing: existingNodeCount,
          vacant: vacantCount
        })}
            style={{ marginBottom: 16 }}
            showIcon
          />
          <Form.Item
            name="fill_count"
            label={t('node.generateCount')}
            rules={[
              { required: true, message: t('node.generateCountPlaceholder') },
              { type: 'number', min: 1, message: t('node.generateCountMin') },
              {
                type: 'number',
                max: vacantCount,
                message: t('node.generateCountMax', { count: vacantCount })
              }
            ]}
          >
            <InputNumber
              min={1}
              max={vacantCount}
              style={{ width: '100%' }}
              placeholder={t('node.generateCountMaxShort', { count: vacantCount })}
            />
          </Form.Item>

          <Card
            title={t('node.field.hardware')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <HardwareConfigFields form={fillForm} showIpmi />
          </Card>
          <Card
            title={t('node.field.nic')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <NicConfigFields form={fillForm} />
          </Card>
        </Form>
      </Modal>
    </div>
  );
}

export default NodeTab;
