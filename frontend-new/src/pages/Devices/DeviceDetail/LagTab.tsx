import { useConfirm } from '@/utils/confirm';
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Space, Form, Input, Select, Tag, Modal } from 'antd';
import DataTable, { DENSE_PAGINATION } from '@/components/DataTable';
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
import { useTranslation } from 'react-i18next';

interface LagTabProps {
  deviceId: number;
  hasSsh?: boolean;
}

function LagTab({ deviceId, hasSsh = true }: LagTabProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const confirm = useConfirm();
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

  const addModal = useDisclosure();
  const [addForm] = Form.useForm();
  const memberModal = useDisclosure();
  const [editingMemberLag, setEditingMemberLag] = useState<LinkAggregationGroup | null>(null);
  const [memberForm] = Form.useForm();
  const purposeModal = useDisclosure();
  const [editingLag, setEditingLag] = useState<LinkAggregationGroup | null>(null);
  const [purposeForm] = Form.useForm();

  const handleAdd = async () => {
    try {
      const values = await addForm.validateFields();
      await createLag.mutateAsync({ deviceId, data: values });
      message.success(t('lag.message.created'));
      addModal.close();
      addForm.resetFields();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleDelete = (lag: LinkAggregationGroup) => {
    confirm({
      title: t('lag.confirmDelete'),
      content: t('lag.confirmDeleteContent', { name: lag.lag_name }),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteLag.mutateAsync({ deviceId, lagId: lag.id });
        message.success(t('lag.message.deleted'));
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
    memberModal.open();
  };

  const handleMemberSubmit = async () => {
    if (!editingMemberLag) return;
    try {
      const values = await memberForm.validateFields();
      await updateLAGMembers.mutateAsync({
        lagId: editingMemberLag.id,
        portIds: values.member_port_ids ?? []
      });
      message.success(t('memberPort.updateSuccess'));
      memberModal.close();
      setEditingMemberLag(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleEditPurpose = (lag: LinkAggregationGroup) => {
    setEditingLag(lag);
    purposeForm.setFieldsValue({ purpose: lag.purpose ?? '' });
    purposeModal.open();
  };

  const handlePurposeSubmit = async () => {
    if (!editingLag) return;
    try {
      const values = await purposeForm.validateFields();
      await updateLag.mutateAsync({
        lagId: editingLag.id,
        data: { purpose: values.purpose ?? '' }
      });
      message.success(t('lag.message.purposeUpdated'));
      purposeModal.close();
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
    { title: t('lag.column.lagName'), dataIndex: 'lag_name', key: 'lag_name' },
    {
      title: tCommon('field.type'),
      dataIndex: 'lag_type',
      key: 'lag_type',
      render: (v: string) =>
        v === 'lacp' ? <Tag color="blue">{t('lag.type.lacp')}</Tag> : <Tag>{t('lag.type.static')}</Tag>
    },
    {
      title: t('lag.column.algorithm'),
      dataIndex: 'algorithm',
      key: 'algorithm',
      render: (v: string | null) => v || '-'
    },
    {
      title: tCommon('field.purpose'),
      dataIndex: 'purpose',
      key: 'purpose',
      render: (v: string) => v || '-'
    },
    { title: t('lag.column.memberCount'), dataIndex: 'member_count', key: 'member_count' },
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
      title: tCommon('field.status'),
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => <StatusTag status={v} statusMap={LAG_STATUS_MAP} />
    },
    {
      title: tCommon('field.actions'),
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
            {tCommon('field.purpose')}
          </Button>
          {!hasSsh && (
            <>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEditMembers(record)}
              >
                {t('lag.action.members')}
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
                title: t('lag.confirmSync'),
                content: t('lag.confirmSyncContent'),
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
            {t('lag.action.syncMembers')}
          </Button>
        )}
        {!hasSsh && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => addModal.open()}>
            {t('lag.action.create')}
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        dataSource={lagGroups ?? []}
        rowKey="id"
        loading={isLoading}
        size="small"
        showCard={false}
        searchable={false}
        pagination={DENSE_PAGINATION}
      />

      {/* 创建链路聚合组弹窗 */}
      <Modal
        title={t('lag.action.create')}
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
            name="lag_name"
            label={t('lag.column.lagName')}
            rules={[{ required: true, message: t('lag.form.inputLagName') }]}
          >
            <Input placeholder={t('lag.form.lagNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="lag_type"
            label={tCommon('field.type')}
            initialValue="lacp"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'lacp', label: t('lag.type.lacpDynamic') },
                { value: 'static', label: t('lag.type.static') }
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* hasSsh=false 模式：成员端口编辑弹窗 */}
      {!hasSsh && (
        <Modal
          title={t('memberPort.editTitle', { name: editingMemberLag?.lag_name ?? '' })}
          open={memberModal.isOpen}
          onOk={handleMemberSubmit}
          onCancel={() => {
            memberModal.close();
            setEditingMemberLag(null);
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

      {/* 用途编辑弹窗（所有交换机可用） */}
      <Modal
        title={t('lag.editPurposeTitle', { name: editingLag?.lag_name ?? '' })}
        open={purposeModal.isOpen}
        onOk={handlePurposeSubmit}
        onCancel={() => {
          purposeModal.close();
          setEditingLag(null);
        }}
        destroyOnHidden
      >
        <p style={{ color: '#8c8c8c', marginBottom: 16 }}>{t('memberPort.purposeHint')}</p>
        <Form form={purposeForm} layout="vertical">
          <Form.Item name="purpose" label={tCommon('field.purpose')}>
            <Input placeholder={t('lag.form.purposePlaceholder')} maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default LagTab;
