/**
 * 指标模板组管理区块（卡片方式）
 *
 * 复用后端已有的模板组 CRUD / 组内模板勾选接口，提供：
 * - 卡片化展示模板组列表（名称、设备类型、来源、厂商约束、模板数、启停）
 * - 新增 / 编辑 / 删除模板组
 * - 勾选模板入组 / 从组内移除模板
 *
 * 分组校验规则（后端强校验，前端做选项过滤）：仅允许设备类型相同、厂商相同、
 * 协议（source）相同的模板归入同一分组。
 */
import { useMemo, useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Button,
  Space,
  Tag,
  Form,
  Input,
  Select,
  Switch,
  Modal,
  Table,
  Empty,
  InputNumber,
  Divider,
  Typography
} from 'antd';
import { useConfirm } from '@/utils/confirm';
import { PlusOutlined, DeleteOutlined, EditOutlined, FolderOutlined } from '@ant-design/icons';
import { useMessage } from '@/hooks/useMessage';
import {
  useMetricTemplateGroups,
  useMetricTemplateGroupDetail,
  useCreateMetricTemplateGroup,
  useUpdateMetricTemplateGroup,
  useDeleteMetricTemplateGroup,
  useAddTemplatesToGroup,
  useRemoveTemplateFromGroup,
  useMetricTemplates,
  type MetricTemplateGroupItem,
  type MetricTemplateGroupUpsert,
  type MetricTemplateItem,
  useVendorBrands
} from '@/services/monitor';
import { SOURCE_OPTIONS, SOURCE_LABEL, deviceTypeLabel, buildDeviceTypeOptions } from './shared';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface GroupFormValues extends Omit<MetricTemplateGroupUpsert, 'vendor'> {
  vendor?: string;
}

export default function MetricTemplateGroupsSection() {
  const confirm = useConfirm();
  const message = useMessage();
  const { t } = useTranslation('monitor');
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const { data: groups, isLoading } = useMetricTemplateGroups();
  const { data: templates, isLoading: templatesLoading } = useMetricTemplates();
  const { data: vendorBrands } = useVendorBrands();
  const vendorOptions = (vendorBrands?.items ?? [])
    .filter((v) => v.enabled)
    .map((v) => ({ key: v.id, label: v.label, value: v.enterprise_no }));

  const createGroup = useCreateMetricTemplateGroup();
  const updateGroup = useUpdateMetricTemplateGroup();
  const deleteGroup = useDeleteMetricTemplateGroup();
  const addTemplates = useAddTemplatesToGroup();
  const removeTemplate = useRemoveTemplateFromGroup();

  const groupModal = useDisclosure();
  const [editingGroup, setEditingGroup] = useState<MetricTemplateGroupItem | null>(null);
  const [groupForm] = Form.useForm<GroupFormValues>();

  const [manageGroupId, setManageGroupId] = useState<number | null>(null);
  const { data: groupDetail } = useMetricTemplateGroupDetail(
    manageGroupId ?? 0,
    manageGroupId != null
  );
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([]);

  const deviceTypeOptions = buildDeviceTypeOptions(td);
  const allGroups = groups ?? [];

  const openCreateGroup = () => {
    setEditingGroup(null);
    groupForm.resetFields();
    groupForm.setFieldsValue({
      device_type: 'network',
      source: 'snmp',
      display_order: 0,
      enabled: true
    });
    groupModal.open();
  };

  const openEditGroup = (g: MetricTemplateGroupItem) => {
    setEditingGroup(g);
    groupForm.setFieldsValue({
      name: g.name,
      device_type: g.device_type,
      source: g.source,
      vendor: g.vendor ?? undefined,
      display_order: g.display_order ?? 0,
      enabled: g.enabled ?? true,
      description: g.description ?? undefined
    });
    groupModal.open();
  };

  const handleGroupSubmit = async () => {
    const values = await groupForm.validateFields();
    const payload = {
      name: values.name,
      device_type: values.device_type,
      source: values.source,
      vendor: values.vendor ?? null,
      display_order: values.display_order ?? 0,
      enabled: values.enabled ?? true,
      description: values.description ?? null
    };
    try {
      if (editingGroup) {
        await updateGroup.mutateAsync({ id: editingGroup.id, ...payload });
        message.success(t('metricTemplate.group.message.updated'));
      } else {
        await createGroup.mutateAsync(payload);
        message.success(t('metricTemplate.group.message.created'));
      }
      groupModal.close();
      groupForm.resetFields();
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('metricTemplate.group.message.saveFailed'));
    }
  };

  const handleDeleteGroup = async (id: number) => {
    try {
      await deleteGroup.mutateAsync(id);
      message.success(t('metricTemplate.group.message.deleted'));
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('metricTemplate.group.message.deleteFailed'));
    }
  };

  const openManage = (id: number) => {
    setManageGroupId(id);
    setSelectedTemplateIds([]);
  };

  const handleAddTemplates = async () => {
    if (!manageGroupId || selectedTemplateIds.length === 0) return;
    const inGroupIds = new Set((groupDetail?.templates ?? []).map((t) => t.id));
    const newIds = selectedTemplateIds.filter((id) => !inGroupIds.has(id));
    if (newIds.length === 0) {
      message.info(t('metricTemplate.group.message.allAlreadyInGroup'));
      return;
    }
    try {
      await addTemplates.mutateAsync({ groupId: manageGroupId, templateIds: newIds });
      message.success(t('metricTemplate.group.message.added', { count: newIds.length }));
      setSelectedTemplateIds([]);
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('metricTemplate.group.message.addFailed'));
    }
  };

  const handleRemoveTemplate = async (templateId: number) => {
    if (!manageGroupId) return;
    try {
      await removeTemplate.mutateAsync({ groupId: manageGroupId, templateId });
      message.success(t('metricTemplate.group.message.removed'));
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('metricTemplate.group.message.removeFailed'));
    }
  };

  const candidateTemplates = useMemo(() => {
    if (!groupDetail || !templates) return [];
    const inGroupIds = new Set((groupDetail.templates ?? []).map((t) => t.id));
    const groupVendor = groupDetail.vendor ?? null;
    return (templates.items ?? []).filter((t) => {
      if (inGroupIds.has(t.id)) return false;
      if (t.device_type !== groupDetail.device_type) return false;
      if (t.source !== groupDetail.source) return false;
      if (groupVendor && t.vendor !== groupVendor) return false;
      return true;
    });
  }, [groupDetail, templates]);

  const groupColumns = [
    {
      title: tc('field.name'),
      dataIndex: 'name',
      width: 160,
      render: (v: string, r: MetricTemplateGroupItem) => (
        <Space size={4}>
          <FolderOutlined style={{ color: '#1677ff' }} />
          <Text strong>{v}</Text>
          {r.enabled === false && <Tag color="default">{t('metricTemplate.group.status.disabled')}</Tag>}
        </Space>
      )
    },
    {
      title: td('switch.batchField.deviceType'),
      dataIndex: 'device_type',
      width: 100,
      render: (v: string) => <Tag>{deviceTypeLabel(v, td)}</Tag>
    },
    {
      title: tc('field.source'),
      dataIndex: 'source',
      width: 90,
      render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
    },
    {
      title: t('metricTemplate.group.column.vendorConstraint'),
      dataIndex: 'vendor',
      width: 100,
      render: (v: string | null) =>
        v ? (
          <Tag color="geekblue">{v}</Tag>
        ) : (
          <Text type="secondary">{t('metricTemplate.group.vendorUnlimited')}</Text>
        )
    },
    {
      title: t('metricTemplate.group.column.templateCount'),
      dataIndex: 'template_count',
      width: 80,
      render: (v: number) => v ?? 0
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      ellipsis: true,
      render: (v: string) => v ?? '-'
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 220,
      render: (_: unknown, r: MetricTemplateGroupItem) => (
        <Space size={4}>
          <Button size="small" onClick={() => openManage(r.id)}>
            {t('metricTemplate.group.action.manage')}
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditGroup(r)} />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              confirm({
                title: t('metricTemplate.group.confirm.deleteTitle'),
                content: t('metricTemplate.group.confirm.deleteContent'),
                okText: tc('action.delete'),
                cancelText: tc('action.cancel'),
                okButtonProps: { danger: true },
                onOk: () => handleDeleteGroup(r.id)
              })
            }
          />
        </Space>
      )
    }
  ];

  return (
    <Card
      title={t('metricTemplate.group.title')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateGroup}>
          {t('metricTemplate.group.action.create')}
        </Button>
      }
    >
      <Table<MetricTemplateGroupItem>
        columns={groupColumns}
        dataSource={allGroups}
        rowKey={(r) => String(r.id)}
        loading={isLoading}
        pagination={false}
        size="small"
        locale={{
          emptyText: (
            <Empty
              description={t('metricTemplate.group.empty', {
                action: t('metricTemplate.group.action.create')
              })}
            />
          )
        }}
        scroll={{ x: 'max-content' }}
      />

      {/* 组新增/编辑弹窗 */}
      <Modal
        title={
          editingGroup
            ? t('metricTemplate.group.modal.editTitle')
            : t('metricTemplate.group.modal.createTitle')
        }
        open={groupModal.isOpen}
        onOk={handleGroupSubmit}
        onCancel={() => {
          groupModal.close();
          groupForm.resetFields();
        }}
        confirmLoading={createGroup.isPending || updateGroup.isPending}
        destroyOnHidden
      >
        <Form form={groupForm} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label={t('metricTemplate.group.field.name')}
            rules={[{ required: true, message: t('metricTemplate.group.validation.nameRequired') }]}
          >
            <Input placeholder={t('metricTemplate.group.placeholder.name')} />
          </Form.Item>
          <Form.Item
            name="device_type"
            label={td('switch.batchField.deviceType')}
            rules={[{ required: true, message: td('switch.form.deviceTypeRequired') }]}
          >
            <Select options={deviceTypeOptions} />
          </Form.Item>
          <Form.Item
            name="source"
            label={t('metricTemplate.group.field.source')}
            rules={[{ required: true, message: t('metricTemplate.group.validation.sourceRequired') }]}
          >
            <Select options={SOURCE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="vendor"
            label={t('metricTemplate.group.field.vendorConstraintOptional')}
            extra={t('metricTemplate.group.extra.vendorConstraint')}
          >
            <Select
              options={vendorOptions}
              placeholder={t('metricTemplate.group.placeholder.vendor')}
              allowClear
            />
          </Form.Item>
          <Form.Item name="display_order" label={t('metricTemplate.group.field.displayOrder')}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label={tc('action.enable')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="description" label={tc('field.description')}>
            <Input.TextArea rows={2} placeholder={t('metricTemplate.group.placeholder.description')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 组内模板管理弹窗 */}
      <Modal
        title={t('metricTemplate.group.modal.manageTitle', { name: groupDetail?.name ?? '' })}
        open={manageGroupId != null}
        onCancel={() => setManageGroupId(null)}
        footer={
          <Button
            type="primary"
            disabled={selectedTemplateIds.length === 0}
            loading={addTemplates.isPending}
            onClick={handleAddTemplates}
          >
            {t('metricTemplate.group.action.addSelected', { count: selectedTemplateIds.length })}
          </Button>
        }
        width={760}
        destroyOnHidden
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Space wrap>
            <Text strong>{t('metricTemplate.group.candidateTitle')}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('metricTemplate.group.candidateHint')}
            </Text>
          </Space>
          <Table<MetricTemplateItem>
            dataSource={candidateTemplates}
            loading={templatesLoading}
            rowKey={(r) => String(r.id)}
            size="small"
            pagination={{ pageSize: 5, showSizeChanger: false }}
            rowSelection={{
              selectedRowKeys: selectedTemplateIds,
              onChange: (keys) => setSelectedTemplateIds(keys as number[])
            }}
            columns={[
              {
                title: t('metricTemplate.column.metric'),
                dataIndex: 'metric_key',
                width: 160,
                render: (v: string, r) => (
                  <Space direction="vertical" size={0} style={{ lineHeight: 1.2 }}>
                    <Text>{r.display_name ?? v}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {v}
                    </Text>
                  </Space>
                )
              },
              {
                title: t('metricTemplate.column.category'),
                dataIndex: 'category',
                width: 100,
                render: (v: string) => (v ? <Tag color="geekblue">{v}</Tag> : '-')
              },
              {
                title: tc('field.source'),
                dataIndex: 'source',
                width: 80,
                render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
              },
              {
                title: t('metricTemplate.field.vendor'),
                dataIndex: 'vendor',
                width: 90,
                render: (v: string | null) => v ?? <Text type="secondary">—</Text>
              }
            ]}
            locale={{
              emptyText: <Empty description={t('metricTemplate.group.candidateEmpty')} />
            }}
            scroll={{ x: 'max-content' }}
          />

          <Divider />

          <Text strong>
            {t('metricTemplate.group.memberTitle', {
              count: groupDetail?.templates?.length ?? 0
            })}
          </Text>
          {groupDetail && groupDetail.templates.length > 0 ? (
            <Table<MetricTemplateItem>
              dataSource={groupDetail.templates}
              rowKey={(r) => String(r.id)}
              size="small"
              pagination={false}
              columns={[
                {
                  title: t('metricTemplate.column.metric'),
                  dataIndex: 'metric_key',
                  render: (v: string, r) => r.display_name ?? v
                },
                {
                  title: tc('field.source'),
                  dataIndex: 'source',
                  width: 80,
                  render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
                },
                {
                  title: t('metricTemplate.field.vendor'),
                  dataIndex: 'vendor',
                  width: 90,
                  render: (v: string | null) => v ?? <Text type="secondary">—</Text>
                },
                {
                  title: tc('field.actions'),
                  key: 'action',
                  width: 80,
                  render: (_: unknown, r: MetricTemplateItem) => (
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() =>
                        confirm({
                          title: t('metricTemplate.group.confirm.removeTitle'),
                          okText: t('metricTemplate.group.action.remove'),
                          cancelText: tc('action.cancel'),
                          okButtonProps: { danger: true },
                          onOk: () => handleRemoveTemplate(r.id!)
                        })
                      }
                    />
                  )
                }
              ]}
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <Empty
              description={t('metricTemplate.group.memberEmpty')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Space>
      </Modal>
    </Card>
  );
}
