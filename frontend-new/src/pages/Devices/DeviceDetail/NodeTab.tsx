import { confirm } from '@/utils/confirm';

import { useState, useEffect } from 'react';
import type { DragEvent } from 'react';
import {
  Table,
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
import { DEVICE_STATUS_MAP, DeviceStatusCode } from '@/types/enums';
import { useMessage } from '@/hooks/useMessage';
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

  const [formOpen, setFormOpen] = useState(false);
  const [form] = Form.useForm();

  
  const [fillOpen, setFillOpen] = useState(false);
  const [fillForm] = Form.useForm();

  
  const { data: chassisDetail } = useDeviceDetail(deviceId);

  
  const { data: nicComponentTemplates } = useComponentTemplates('nic');

  
  const existingNodeCount = data?.items?.length ?? 0;
  const maxTotal = totalNodes ?? (nodeRows && nodeCols ? nodeRows * nodeCols : 0);
  const vacantCount = Math.max(0, maxTotal - existingNodeCount);

  
  const watchedNodePosition = Form.useWatch('node_position', form);
  useEffect(() => {
    if (!formOpen || !watchedNodePosition || !deviceName) return;
    
    
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
    form.setFieldValue('notes', `${deviceName} 节点 ${watchedNodePosition}`);
  }, [formOpen, watchedNodePosition, deviceName, chassisDetail, form]);

  
  const handleAdd = () => {
    
    if (vacantCount === 0) {
      message.info('当前机箱节点位置已满，无法继续添加子节点');
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
    setFormOpen(true);
  };

  
  const handleDelete = (record: Device) => {
    confirm({
      title: '确认删除',
      content: `确定要删除节点「${record.device_name}」吗？`,
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(record.id);
          message.success('删除成功');
        } catch (err) {
          message.error(err instanceof Error ? err.message : '删除失败');
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
      message.success('节点创建成功');
      setFormOpen(false);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleFillOpen = () => {
    if (vacantCount === 0) {
      message.info('当前没有空余节点位置');
      return;
    }
    fillForm.resetFields();
    fillForm.setFieldsValue({
      fill_count: vacantCount
    });
    setFillOpen(true);
  };

  
  const handleFillSubmit = async () => {
    try {
      const values = await fillForm.validateFields();
      const fillCount = values.fill_count as number;

      if (fillCount <= 0) {
        message.warning('生成数量必须大于0');
        return;
      }
      if (fillCount > vacantCount) {
        message.warning(`生成数量不能超过剩余空余位置（${vacantCount}个）`);
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

      message.success(`已生成 ${fillCount} 个子节点`);
      setFillOpen(false);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const columns = [
    {
      title: '节点位置',
      dataIndex: 'node_position',
      key: 'node_position',
      width: 90,
      render: (v: number | null) => v ?? '-'
    },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record: Device) => (
        <Button type="link" size="small" onClick={() => navigate(`/devices/${record.id}#basic`)}>
          {name}
        </Button>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: number) => {
        const info = DEVICE_STATUS_MAP[v as DeviceStatusCode];
        return <Tag color={info?.color}>{info?.label ?? '未知'}</Tag>;
      }
    },
    {
      title: '主机名',
      dataIndex: 'hostname',
      key: 'hostname',
      render: (v: string | null) => v ?? '-'
    },
    { title: 'CPU', dataIndex: 'cpu', key: 'cpu', render: (v: string | null) => v ?? '-' },
    {
      title: '内存',
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
                {single ? `单条 ${single}GB × ${count} = ` : ''}
                {total}GB
              </div>
            ) : null}
          </div>
        );
      }
    },
    {
      title: '操作系统',
      dataIndex: 'os_version',
      key: 'os_version',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: Device) => (
        <Button
          type="link"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDelete(record)}
        />
      )
    }
  ];

  
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
        '节点位置交换失败';
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
          节点布局：{nodeRows}行 × {nodeCols}列 = {total}节点（已占用 {existingNodeCount}，空余{' '}
          {vacantCount}）— 拖拽节点可更换位置
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
                    ? `拖拽更换位置 · 点击查看 ${node.device_name}`
                    : `空位 R${row}C${col}（可拖入节点）`
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
      {}
      <Alert
        type="info"
        message="如需重新生成所有节点（覆盖已有），请在编辑机箱时勾选「生成子节点」"
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
            <Tooltip title={`填满所有空余节点位置（当前空余 ${vacantCount} 个）`}>
              <Button icon={<FullscreenOutlined />} onClick={handleFillOpen}>
                填满空余节点
              </Button>
            </Tooltip>
          )}
        </Space>
        <Tooltip
          title={vacantCount === 0 ? '机箱节点位置已满，无法继续添加' : '新增一个子节点到空余位置'}
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAdd}
            disabled={vacantCount === 0}
          >
            新增节点
          </Button>
        </Tooltip>
      </div>
      {renderNodeGrid()}
      <Table
        columns={columns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
      />

      {}
      <Modal
        title="新增节点"
        open={formOpen}
        onOk={handleSubmit}
        onCancel={() => setFormOpen(false)}
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
            label="节点名称"
            rules={[{ required: true, message: '请输入节点名称' }]}
          >
            <Input placeholder="如 Chassis-01-Node1" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="node_position"
                label="节点位置"
                rules={[{ required: true, message: '请输入节点位置' }]}
              >
                <InputNumber
                  min={1}
                  max={totalNodes ?? 128}
                  style={{ width: '100%' }}
                  placeholder="位置编号"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="status" label="状态">
                <Select
                  placeholder="请选择"
                  options={Object.entries(DEVICE_STATUS_MAP).map(([k, v]) => ({
                    label: v.label,
                    value: Number(k)
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="hostname" label="主机名">
                <Input placeholder="主机名" />
              </Form.Item>
            </Col>
          </Row>

          <Card
            title="硬件配置"
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <HardwareConfigFields form={form} showIpmi />
          </Card>
          <Card
            title="网卡配置"
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <NicConfigFields form={form} />
          </Card>
        </Form>
      </Modal>

      {}
      <Modal
        title="填满空余节点位置"
        open={fillOpen}
        onOk={handleFillSubmit}
        onCancel={() => setFillOpen(false)}
        confirmLoading={updateDevice.isPending}
        width={780}
        destroyOnHidden
      >
        <Form form={fillForm} layout="vertical">
          <Alert
            type="info"
            message={`当前机箱共 ${maxTotal} 个节点位置，已有 ${existingNodeCount} 个子节点，空余 ${vacantCount} 个位置。将按顺序填充空余位置，已有子节点不受影响。`}
            style={{ marginBottom: 16 }}
            showIcon
          />
          <Form.Item
            name="fill_count"
            label="生成节点数量"
            rules={[
              { required: true, message: '请输入生成数量' },
              { type: 'number', min: 1, message: '至少生成1个节点' },
              {
                type: 'number',
                max: vacantCount,
                message: `不能超过剩余空余位置（${vacantCount}个）`
              }
            ]}
          >
            <InputNumber
              min={1}
              max={vacantCount}
              style={{ width: '100%' }}
              placeholder={`最多 ${vacantCount} 个`}
            />
          </Form.Item>

          <Card
            title="硬件配置"
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <HardwareConfigFields form={fillForm} showIpmi />
          </Card>
          <Card
            title="网卡配置"
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
