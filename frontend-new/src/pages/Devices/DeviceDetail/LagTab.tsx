import { confirm } from '@/utils/confirm';

import { useState, useMemo } from 'react';
import { Table, Button, Space, Form, Input, Select, Tag, Modal } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, SyncOutlined } from '@ant-design/icons';
import {
  useLinkAggregationGroups,
  useCreateLinkAggregationGroup,
  useDeleteLinkAggregationGroup,
  useUpdateLAGMembers,
  useUpdateLinkAggregationGroup
} from '@/services/link-aggregation';
import { useNetworkPorts } from '@/services/network-port';
import { useSyncMembers } from '@/services/switch';
import { useMessage } from '@/hooks/useMessage';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/services/query-keys';
import { GroupedMemberPorts, PortLegend } from '@/components/PortMemberBlocks';
import { StatusTag } from '@/components/StatusTag';
import { LAG_STATUS_MAP } from '@/types/enums';
import type { LinkAggregationGroup } from '@/services/link-aggregation';
import type { SwitchPort } from '@/types/models';
import { isPhysicalPort } from '@/utils/portType';

interface LagTabProps {
  deviceId: number;
  
  hasSsh?: boolean;
}


function LagTab({ deviceId, hasSsh = true }: LagTabProps) {
  const { data: lagGroups, isLoading } = useLinkAggregationGroups(deviceId);
  const createLag = useCreateLinkAggregationGroup();
  const deleteLag = useDeleteLinkAggregationGroup();
  
  const updateLAGMembers = useUpdateLAGMembers(deviceId);
  
  const updateLag = useUpdateLinkAggregationGroup(deviceId);
  
  const syncMembers = useSyncMembers();
  const queryClient = useQueryClient();
  
  const { data: ports } = useNetworkPorts(deviceId);
  const message = useMessage();

  
  useDeviceEvents(deviceId, 'lags');

  
  const portMap = useMemo(() => {
    const map = new Map<string, SwitchPort>();
    for (const p of ports ?? []) {
      map.set(p.port_name, p);
    }
    return map;
  }, [ports]);

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addForm] = Form.useForm();
  
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [editingMemberLag, setEditingMemberLag] = useState<LinkAggregationGroup | null>(null);
  const [memberForm] = Form.useForm();
  
  const [purposeModalOpen, setPurposeModalOpen] = useState(false);
  const [editingLag, setEditingLag] = useState<LinkAggregationGroup | null>(null);
  const [purposeForm] = Form.useForm();

  
  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createLag.mutateAsync({ deviceId, data: values });
      message.success('链路聚合组创建成功');
      setAddModalOpen(false);
      addForm.resetFields();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleDelete = (lag: LinkAggregationGroup) => {
    confirm({
      title: '确认删除链路聚合组',
      content: `确定要删除链路聚合组「${lag.lag_name}」吗？`,
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteLag.mutateAsync({ deviceId, lagId: lag.id });
        message.success('链路聚合组已删除');
      }
    });
  };

  
  const handleEditMembers = (lag: LinkAggregationGroup) => {
    setEditingMemberLag(lag);
    
    const initialPortIds = (lag.member_ports ?? [])
      .map((name) => portMap.get(name)?.id)
      .filter((id): id is number => id != null);
    memberForm.setFieldsValue({
      member_port_ids: initialPortIds
    });
    setMemberModalOpen(true);
  };

  
  const handleMemberSubmit = async () => {
    if (!editingMemberLag) return;
    try {
      const values = await memberForm.validateFields();
      await updateLAGMembers.mutateAsync({
        lagId: editingMemberLag.id,
        portIds: values.member_port_ids ?? []
      });
      message.success('成员端口更新成功');
      setMemberModalOpen(false);
      setEditingMemberLag(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleEditPurpose = (lag: LinkAggregationGroup) => {
    setEditingLag(lag);
    purposeForm.setFieldsValue({ purpose: lag.purpose ?? '' });
    setPurposeModalOpen(true);
  };

  
  const handlePurposeSubmit = async () => {
    if (!editingLag) return;
    try {
      const values = await purposeForm.validateFields();
      await updateLag.mutateAsync({
        lagId: editingLag.id,
        data: { purpose: values.purpose ?? '' }
      });
      message.success('用途更新成功');
      setPurposeModalOpen(false);
      setEditingLag(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const portOptions = (ports ?? [])
    .filter((p) => isPhysicalPort(p.port_name))
    .map((p) => ({
      label: p.port_name,
      value: p.id
    }));

  const columns = [
    { title: '聚合组名称', dataIndex: 'lag_name', key: 'lag_name' },
    {
      title: '类型',
      dataIndex: 'lag_type',
      key: 'lag_type',
      render: (v: string) => (v === 'lacp' ? <Tag color="blue">LACP</Tag> : <Tag>静态</Tag>)
    },
    {
      title: '负载算法',
      dataIndex: 'algorithm',
      key: 'algorithm',
      render: (v: string | null) => v || '-'
    },
    { title: '用途', dataIndex: 'purpose', key: 'purpose', render: (v: string) => v || '-' },
    { title: '成员数', dataIndex: 'member_count', key: 'member_count' },
    {
      title: '成员端口',
      dataIndex: 'member_ports',
      key: 'member_ports',
      render: (memberPorts: string[]) => {
        if (!memberPorts?.length) return <span style={{ color: '#bfbfbf' }}>-</span>;
        return <GroupedMemberPorts memberPorts={memberPorts} portMap={portMap} />;
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => <StatusTag status={v} statusMap={LAG_STATUS_MAP} />
    },
    {
      title: '操作',
      key: 'action',
      width: hasSsh ? 80 : 200,
      render: (_: unknown, record: LinkAggregationGroup) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditPurpose(record)}
          >
            用途
          </Button>
          {!hasSsh && (
            <>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEditMembers(record)}
              >
                成员
              </Button>
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record)}
              >
                删除
              </Button>
            </>
          )}
        </Space>
      )
    }
  ];

  return (
    <div>
      {}
      <PortLegend />

      <div style={{ marginBottom: 12, textAlign: 'right' }}>
        {hasSsh && (
          <Button
            icon={<SyncOutlined spin={syncMembers.isPending} />}
            loading={syncMembers.isPending}
            onClick={() => {
              confirm({
                title: '同步链路聚合成员端口',
                content:
                  '将从设备 SSH 获取所有 Eth-Trunk 配置并解析成员端口列表，可能需要较长时间。确定继续？',
                onOk: async () => {
                  try {
                    await syncMembers.mutateAsync(deviceId);
                    message.info('成员端口同步已提交，完成后将通过消息通知您');
                  } catch {
                    
                  }
                }
              });
            }}
            style={{ marginRight: 8 }}
          >
            同步成员
          </Button>
        )}
        {!hasSsh && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>
            创建链路聚合组
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={lagGroups ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
      />

      {}
      <Modal
        title="创建链路聚合组"
        open={addModalOpen}
        onOk={handleAdd}
        onCancel={() => {
          setAddModalOpen(false);
          addForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="lag_name"
            label="聚合组名称"
            rules={[{ required: true, message: '请输入聚合组名称' }]}
          >
            <Input placeholder="如 Eth-Trunk1" />
          </Form.Item>
          <Form.Item name="lag_type" label="类型" initialValue="lacp" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'lacp', label: 'LACP（动态）' },
                { value: 'static', label: '静态' }
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {}
      {!hasSsh && (
        <Modal
          title={`编辑成员端口 - ${editingMemberLag?.lag_name ?? ''}`}
          open={memberModalOpen}
          onOk={handleMemberSubmit}
          onCancel={() => {
            setMemberModalOpen(false);
            setEditingMemberLag(null);
          }}
          destroyOnHidden
        >
          <Form form={memberForm} layout="vertical">
            <Form.Item name="member_port_ids" label="成员端口">
              <Select
                mode="multiple"
                placeholder="选择成员端口"
                options={portOptions}
                showSearch
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </Form>
        </Modal>
      )}

      {}
      <Modal
        title={`编辑用途 - ${editingLag?.lag_name ?? ''}`}
        open={purposeModalOpen}
        onOk={handlePurposeSubmit}
        onCancel={() => {
          setPurposeModalOpen(false);
          setEditingLag(null);
        }}
        destroyOnHidden
      >
        <p style={{ color: '#8c8c8c', marginBottom: 16 }}>
          此处仅记录用途信息，不操作交换机。操作交换机需要在端口列表对应的端口操作。
        </p>
        <Form form={purposeForm} layout="vertical">
          <Form.Item name="purpose" label="用途">
            <Input placeholder="如 上行链路、服务器互联" maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default LagTab;
