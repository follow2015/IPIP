import { useConfirm } from '@/utils/confirm';
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Space, Form, InputNumber, Input, Select, Modal } from 'antd';
import DataTable, { DENSE_PAGINATION } from '@/components/DataTable';
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
import { useTranslation } from 'react-i18next';

interface VlanTabProps {
  deviceId: number;
  hasSsh?: boolean;
}

function VlanTab({ deviceId, hasSsh = true }: VlanTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
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

  const addModal = useDisclosure();
  const editModal = useDisclosure();
  const [editingVlan, setEditingVlan] = useState<VLAN | null>(null);
  const memberModal = useDisclosure();
  const [editingMemberVlan, setEditingMemberVlan] = useState<VLAN | null>(null);
  const [memberForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createVLAN.mutateAsync(values);
      message.success(t('vlan.message.created'));
      addModal.close();
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
    editModal.open();
  };

  const handleEditSubmit = async () => {
    if (!editingVlan) return;
    try {
      const values = await editForm.validateFields();
      await updateVLAN.mutateAsync({
        vlanId: editingVlan.id,
        data: { purpose: values.purpose ?? '', name: values.name }
      });
      message.success(t('vlan.message.updated'));
      editModal.close();
      setEditingVlan(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleDelete = (vlan: VLAN) => {
    confirm({
      title: t('vlan.confirmDelete'),
      content: t('vlan.confirmDeleteContent', { id: vlan.vlan_id, name: vlan.name }),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteVLAN.mutateAsync(vlan.id);
        message.success(t('vlan.message.deleted'));
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
    memberModal.open();
  };

  const handleMemberSubmit = async () => {
    if (!editingMemberVlan) return;
    try {
      const values = await memberForm.validateFields();
      await updateVLANMembers.mutateAsync({
        vlanId: editingMemberVlan.id,
        portIds: values.member_port_ids ?? []
      });
      message.success(t('memberPort.updateSuccess'));
      memberModal.close();
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
    { title: t('vlan.column.vlanId'), dataIndex: 'vlan_id', key: 'vlan_id' },
    { title: tCommon('field.name'), dataIndex: 'name', key: 'name' },
    {
      title: tCommon('field.purpose'),
      dataIndex: 'purpose',
      key: 'purpose',
      render: (v: string | null) => v || '-'
    },
    {
      title: tCommon('field.status'),
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => <StatusTag status={v} statusMap={VLAN_STATUS_MAP} />
    },
    {
      title: t('memberPort.column'),
      dataIndex: 'member_ports',
      key: 'member_ports',
      render: (memberPorts: string[]) => {
        if (!memberPorts?.length) return <span style={{ color: '#bfbfbf' }}>-</span>;
        return <GroupedMemberPorts memberPorts={memberPorts} portMap={portMap} />;
      }
    },
    {
      title: tCommon('field.actions'),
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
            {tCommon('field.purpose')}
          </Button>
          {!hasSsh && (
            <>
              <Button type="link" size="small" onClick={() => handleEditMembers(record)}>
                {t('vlan.action.members')}
              </Button>
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record)}
              >
                {tCommon('action.delete')}
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
                title: t('vlan.confirmSync'),
                content: t('vlan.confirmSyncContent'),
                onOk: async () => {
                  try {
                    await syncMembers.mutateAsync(deviceId);
                    message.info(t('memberPort.syncSubmitted'));
                  } catch {
                  }
                }
              });
            }}
            style={{ marginRight: 8 }}
          >
            {t('vlan.action.syncMembers')}
          </Button>
        )}
        {!hasSsh && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => addModal.open()}>
            {t('vlan.action.add')}
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        dataSource={vlans ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
        showCard={false}
        searchable={false}
        pagination={DENSE_PAGINATION}
      />

      {/* 新增 VLAN 弹窗 */}
      <Modal
        title={t('vlan.action.add')}
        open={addModal.isOpen}
        onOk={handleAdd}
        onCancel={() => {
          addModal.close();
          addForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="vlan_id"
            label={t('vlan.column.vlanId')}
            rules={[{ required: true, message: t('vlan.form.inputVlanId') }]}
          >
            <InputNumber min={1} max={4094} style={{ width: '100%' }} placeholder="1-4094" />
          </Form.Item>
          <Form.Item
            name="name"
            label={tCommon('field.name')}
            rules={[{ required: true, message: t('vlan.form.inputName') }]}
          >
            <Input placeholder={t('vlan.form.namePlaceholder')} />
          </Form.Item>
          <Form.Item name="purpose" label={tCommon('field.purpose')}>
            <Input placeholder={t('vlan.form.purposePlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑 VLAN 弹窗 */}
      <Modal
        title={t('vlan.editTitle')}
        open={editModal.isOpen}
        onOk={handleEditSubmit}
        onCancel={() => {
          editModal.close();
          setEditingVlan(null);
        }}
        destroyOnHidden
      >
        <p style={{ color: '#8c8c8c', marginBottom: 16 }}>{t('memberPort.purposeHint')}</p>
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="vlan_id"
            label={t('vlan.column.vlanId')}
            rules={[{ required: true, message: t('vlan.form.inputVlanId') }]}
          >
            <InputNumber min={1} max={4094} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="name"
            label={tCommon('field.name')}
            rules={[{ required: true, message: t('vlan.form.inputName') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="purpose" label={tCommon('field.purpose')}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* hasSsh=false 模式：成员端口编辑弹窗 */}
      {!hasSsh && (
        <Modal
          title={t('memberPort.editTitle', {
            name: `VLAN ${editingMemberVlan?.vlan_id ?? ''}`
          })}
          open={memberModal.isOpen}
          onOk={handleMemberSubmit}
          onCancel={() => {
            memberModal.close();
            setEditingMemberVlan(null);
          }}
          destroyOnHidden
        >
          <Form form={memberForm} layout="vertical">
            <Form.Item name="member_port_ids" label={t('memberPort.column')}>
              <Select
                mode="multiple"
                placeholder={t('memberPort.selectPlaceholder')}
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
