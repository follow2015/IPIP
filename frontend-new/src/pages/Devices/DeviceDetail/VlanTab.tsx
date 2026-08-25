import { confirm } from '@/utils/confirm';
import { useState, useMemo } from 'react';
import { Table, Button, Space, Form, InputNumber, Input, Select, Modal } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons';
import {
  useVLANsByDevice,
  useCreateDeviceVLAN,
  useUpdateDeviceVLAN,
  useDeleteVLAN,
  useUpdateVLANMembers
} from '@/services/vlan';
import { useNetworkPorts } from '@/services/network-port';
import { useSyncMembers } from '@/services/switch';
import { useMessage } from '@/hooks/useMessage';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/services/query-keys';
import { GroupedMemberPorts, PortLegend } from '@/components/PortMemberBlocks';
import { StatusTag } from '@/components/StatusTag';
import { VLAN_STATUS_MAP } from '@/types/enums';
import type { VLAN, SwitchPort } from '@/types/models';

interface VlanTabProps {
  deviceId: number;
  hasSsh?: boolean;
}

function VlanTab({ deviceId, hasSsh = true }: VlanTabProps) {
  const { data: vlans, isLoading } = useVLANsByDevice(deviceId);
  const createVLAN = useCreateDeviceVLAN(deviceId);
  const updateVLAN = useUpdateDeviceVLAN(deviceId);
  const deleteVLAN = useDeleteVLAN();
  const updateVLANMembers = useUpdateVLANMembers(deviceId);
  const syncMembers = useSyncMembers();
  const queryClient = useQueryClient();
  const { data: ports } = useNetworkPorts(deviceId);
  const message = useMessage();

  useDeviceEvents(
    deviceId,
    'vlans',
    (event) => {
      if (event.op_type === 'vlan_member_set') {
        queryClient.invalidateQueries({ queryKey: queryKeys.vlans.byDevice(deviceId) });
      }
    },
    hasSsh
  );

  const portMap = useMemo(() => {
    const map = new Map<string, SwitchPort>();
    for (const p of ports ?? []) {
      map.set(p.port_name, p);
    }
    return map;
  }, [ports]);

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingVlan, setEditingVlan] = useState<VLAN | null>(null);
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [editingMemberVlan, setEditingMemberVlan] = useState<VLAN | null>(null);
  const [memberForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createVLAN.mutateAsync(values);
      message.success('VLAN 创建成功');
      setAddModalOpen(false);
      addForm.resetFields();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleEdit = (vlan: VLAN) => {
    setEditingVlan(vlan);
    editForm.setFieldsValue({
      vlan_id: vlan.vlan_id,
      name: vlan.name,
      purpose: vlan.purpose ?? '',
      status: vlan.status
    });
    setEditModalOpen(true);
  };

  const handleEditSubmit = async () => {
    if (!editingVlan) return;
    try {
      const values = await editForm.validateFields();
      await updateVLAN.mutateAsync({
        vlanId: editingVlan.id,
        data: { purpose: values.purpose ?? '', name: values.name }
      });
      message.success('VLAN 更新成功');
      setEditModalOpen(false);
      setEditingVlan(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleDelete = (vlan: VLAN) => {
    confirm({
      title: '确认删除 VLAN',
      content: `确定要删除 VLAN ${vlan.vlan_id}（${vlan.name}）吗？`,
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteVLAN.mutateAsync(vlan.id);
        message.success('VLAN 已删除');
      }
    });
  };

  const handleEditMembers = (vlan: VLAN) => {
    setEditingMemberVlan(vlan);
    const initialPortIds = (vlan.member_ports ?? [])
      .map((name) => portMap.get(name)?.id)
      .filter((id): id is number => id != null);
    memberForm.setFieldsValue({
      member_port_ids: initialPortIds
    });
    setMemberModalOpen(true);
  };

  const handleMemberSubmit = async () => {
    if (!editingMemberVlan) return;
    try {
      const values = await memberForm.validateFields();
      await updateVLANMembers.mutateAsync({
        vlanId: editingMemberVlan.id,
        portIds: values.member_port_ids ?? []
      });
      message.success('成员端口更新成功');
      setMemberModalOpen(false);
      setEditingMemberVlan(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const portOptions = (ports ?? []).map((p) => ({
    label: p.port_name,
    value: p.id
  }));

  const columns = [
    { title: 'VLAN ID', dataIndex: 'vlan_id', key: 'vlan_id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '用途', dataIndex: 'purpose', key: 'purpose', render: (v: string | null) => v || '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => <StatusTag status={v} statusMap={VLAN_STATUS_MAP} />
    },
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
      title: '操作',
      key: 'action',
      width: hasSsh ? 80 : 220,
      render: (_: unknown, record: VLAN) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            用途
          </Button>
          {!hasSsh && (
            <>
              <Button type="link" size="small" onClick={() => handleEditMembers(record)}>
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
      {/* 图例 */}
      <PortLegend />

      <div style={{ marginBottom: 12, textAlign: 'right' }}>
        {hasSsh && (
          <Button
            icon={<SyncOutlined spin={syncMembers.isPending} />}
            loading={syncMembers.isPending}
            onClick={() => {
              confirm({
                title: '同步 VLAN 成员端口',
                content:
                  '将从设备 SSH 获取所有 VLANIF 配置并解析成员端口列表，可能需要较长时间。确定继续？',
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
            新增 VLAN
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={vlans ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
      />

      {/* 新增 VLAN 弹窗 */}
      <Modal
        title="新增 VLAN"
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
            name="vlan_id"
            label="VLAN ID"
            rules={[{ required: true, message: '请输入 VLAN ID' }]}
          >
            <InputNumber min={1} max={4094} style={{ width: '100%' }} placeholder="1-4094" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 VLAN100" />
          </Form.Item>
          <Form.Item name="purpose" label="用途">
            <Input placeholder="如 办公网络" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑 VLAN 弹窗 */}
      <Modal
        title="编辑 VLAN"
        open={editModalOpen}
        onOk={handleEditSubmit}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingVlan(null);
        }}
        destroyOnHidden
      >
        <p style={{ color: '#8c8c8c', marginBottom: 16 }}>
          此处仅记录用途信息，不操作交换机。操作交换机需要在端口列表对应的端口操作。
        </p>
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="vlan_id"
            label="VLAN ID"
            rules={[{ required: true, message: '请输入 VLAN ID' }]}
          >
            <InputNumber min={1} max={4094} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="purpose" label="用途">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* hasSsh=false 模式：成员端口编辑弹窗 */}
      {!hasSsh && (
        <Modal
          title={`编辑成员端口 - VLAN ${editingMemberVlan?.vlan_id ?? ''}`}
          open={memberModalOpen}
          onOk={handleMemberSubmit}
          onCancel={() => {
            setMemberModalOpen(false);
            setEditingMemberVlan(null);
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
    </div>
  );
}

export default VlanTab;
