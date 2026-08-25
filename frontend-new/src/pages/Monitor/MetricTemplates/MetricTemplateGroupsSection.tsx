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
  Popconfirm,
  Empty,
  InputNumber,
  Divider,
  Typography
} from 'antd';
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
import { DEVICE_TYPE_OPTIONS, SOURCE_OPTIONS, DEVICE_TYPE_LABEL, SOURCE_LABEL } from './shared';

const { Text } = Typography;


interface GroupFormValues extends Omit<MetricTemplateGroupUpsert, 'vendor'> {
  vendor?: string;
}

export default function MetricTemplateGroupsSection() {
  const message = useMessage();
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

  
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<MetricTemplateGroupItem | null>(null);
  const [groupForm] = Form.useForm<GroupFormValues>();

  
  const [manageGroupId, setManageGroupId] = useState<number | null>(null);
  const { data: groupDetail } = useMetricTemplateGroupDetail(
    manageGroupId ?? 0,
    manageGroupId != null
  );
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([]);

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
    setGroupModalOpen(true);
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
    setGroupModalOpen(true);
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
        message.success('模板组已更新');
      } else {
        await createGroup.mutateAsync(payload);
        message.success('模板组已创建');
      }
      setGroupModalOpen(false);
      groupForm.resetFields();
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存模板组失败');
    }
  };

  
  const handleDeleteGroup = async (id: number) => {
    try {
      await deleteGroup.mutateAsync(id);
      message.success('模板组已删除');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除模板组失败');
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
      message.info('所选模板均已在组内');
      return;
    }
    try {
      await addTemplates.mutateAsync({ groupId: manageGroupId, templateIds: newIds });
      message.success(`已将 ${newIds.length} 个模板加入分组`);
      setSelectedTemplateIds([]);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加入分组失败');
    }
  };

  
  const handleRemoveTemplate = async (templateId: number) => {
    if (!manageGroupId) return;
    try {
      await removeTemplate.mutateAsync({ groupId: manageGroupId, templateId });
      message.success('已从分组移除');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '移除失败');
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
      title: '名称',
      dataIndex: 'name',
      width: 160,
      render: (v: string, r: MetricTemplateGroupItem) => (
        <Space size={4}>
          <FolderOutlined style={{ color: '#1677ff' }} />
          <Text strong>{v}</Text>
          {r.enabled === false && <Tag color="default">停用</Tag>}
        </Space>
      )
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      width: 100,
      render: (v: string) => <Tag>{DEVICE_TYPE_LABEL[v] ?? v}</Tag>
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 90,
      render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
    },
    {
      title: '厂商约束',
      dataIndex: 'vendor',
      width: 100,
      render: (v: string | null) =>
        v ? <Tag color="geekblue">{v}</Tag> : <Text type="secondary">不限</Text>
    },
    {
      title: '模板数',
      dataIndex: 'template_count',
      width: 80,
      render: (v: number) => v ?? 0
    },
    { title: '说明', dataIndex: 'description', ellipsis: true, render: (v: string) => v ?? '-' },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_: unknown, r: MetricTemplateGroupItem) => (
        <Space size={4}>
          <Button size="small" onClick={() => openManage(r.id)}>
            管理模板
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditGroup(r)} />
          <Popconfirm
            title="确认删除该模板组？"
            description="删除后设备将回到自动匹配模板组。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDeleteGroup(r.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <Card
      title="指标模板组"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateGroup}>
          新增模板组
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
        locale={{ emptyText: <Empty description="暂无指标模板组，点击右上角「新增模板组」创建" /> }}
      />

      {}
      <Modal
        title={editingGroup ? '编辑指标模板组' : '新增指标模板组'}
        open={groupModalOpen}
        onOk={handleGroupSubmit}
        onCancel={() => {
          setGroupModalOpen(false);
          groupForm.resetFields();
        }}
        confirmLoading={createGroup.isPending || updateGroup.isPending}
        destroyOnHidden
      >
        <Form form={groupForm} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="组名称"
            rules={[{ required: true, message: '请输入组名称' }]}
          >
            <Input placeholder="如：H3C 网络设备标准指标集" />
          </Form.Item>
          <Form.Item
            name="device_type"
            label="设备类型"
            rules={[{ required: true, message: '请选择设备类型' }]}
          >
            <Select options={DEVICE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="source"
            label="采集协议"
            rules={[{ required: true, message: '请选择采集协议' }]}
          >
            <Select options={SOURCE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="vendor"
            label="厂商约束（可选）"
            extra="声明厂商后，仅允许同厂商的模板加入本组；留空表示不限厂商"
          >
            <Select options={vendorOptions} placeholder="选择厂商（留空表示不限）" allowClear />
          </Form.Item>
          <Form.Item name="display_order" label="排序权重（越小越靠前）">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      {}
      <Modal
        title={`管理模板组「${groupDetail?.name ?? ''}」`}
        open={manageGroupId != null}
        onCancel={() => setManageGroupId(null)}
        footer={
          <Button
            type="primary"
            disabled={selectedTemplateIds.length === 0}
            loading={addTemplates.isPending}
            onClick={handleAddTemplates}
          >
            将选中模板加入分组（{selectedTemplateIds.length}）
          </Button>
        }
        width={760}
        destroyOnHidden
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Space wrap>
            <Text strong>可加入的模板（已过滤兼容性）</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              仅设备类型、协议、厂商（组声明时）一致的可加入
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
                title: '指标',
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
                title: '分类',
                dataIndex: 'category',
                width: 100,
                render: (v: string) => (v ? <Tag color="geekblue">{v}</Tag> : '-')
              },
              {
                title: '来源',
                dataIndex: 'source',
                width: 80,
                render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
              },
              {
                title: '厂商',
                dataIndex: 'vendor',
                width: 90,
                render: (v: string | null) => v ?? <Text type="secondary">—</Text>
              }
            ]}
            locale={{ emptyText: <Empty description="没有符合兼容性校验的模板可供加入" /> }}
          />

          <Divider />

          <Text strong>组内已有模板（{groupDetail?.templates?.length ?? 0}）</Text>
          {groupDetail && groupDetail.templates.length > 0 ? (
            <Table<MetricTemplateItem>
              dataSource={groupDetail.templates}
              rowKey={(r) => String(r.id)}
              size="small"
              pagination={false}
              columns={[
                {
                  title: '指标',
                  dataIndex: 'metric_key',
                  render: (v: string, r) => r.display_name ?? v
                },
                {
                  title: '来源',
                  dataIndex: 'source',
                  width: 80,
                  render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
                },
                {
                  title: '厂商',
                  dataIndex: 'vendor',
                  width: 90,
                  render: (v: string | null) => v ?? <Text type="secondary">—</Text>
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 80,
                  render: (_: unknown, r: MetricTemplateItem) => (
                    <Popconfirm
                      title="确认从分组移除该模板？"
                      okText="移除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => handleRemoveTemplate(r.id!)}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  )
                }
              ]}
            />
          ) : (
            <Empty
              description="该组暂无模板，请在上方选择模板加入"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Space>
      </Modal>
    </Card>
  );
}
