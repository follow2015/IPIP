import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Card,
  Table,
  Tag,
  Switch,
  Button,
  Space,
  Drawer,
  Descriptions,
  Tooltip,
  Typography,
  Modal,
  Popconfirm
} from 'antd';
import {
  ReloadOutlined,
  EyeOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  listSkills,
  getSkill,
  toggleSkill,
  reloadSkills,
  createSkill,
  updateSkillContent,
  deleteSkill,
  type SkillSummary,
  type SkillDetail,
  type SkillWritePayload
} from '@/services/ai';
import { usePermission } from '@/hooks/usePermission';
import { useMessage } from '@/hooks/useMessage';
import SkillEditForm from './SkillEditForm';

const { Text, Paragraph } = Typography;

const SOURCE_COLOR: Record<string, string> = { builtin: 'blue', custom: 'green' };
const SOURCE_LABEL: Record<string, string> = { builtin: '内置', custom: '自定义' };

export default function Skills() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const message = useMessage();

  const { hasPermission } = usePermission();
  const canManage = hasPermission('ai:admin');

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSkills();
      if (mountedRef.current) setSkills(data);
    } catch (err) {
      if (mountedRef.current) {
        message.error(err instanceof Error ? err.message : '加载技能列表失败');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleToggle = async (name: string, enabled: boolean, source: string) => {
    if (source === 'builtin') {
      message.warning('内置技能不可禁用');
      return;
    }
    try {
      await toggleSkill(name, enabled);
      setSkills((prev) => prev.map((s) => (s.name === name ? { ...s, enabled } : s)));
      message.success(enabled ? '已启用' : '已禁用');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const handleViewDetail = async (name: string) => {
    setDrawerOpen(true);
    setDetailLoading(true);
    try {
      const data = await getSkill(name);
      if (mountedRef.current) setDetail(data);
    } catch (err) {
      if (mountedRef.current) {
        message.error(err instanceof Error ? err.message : '加载详情失败');
      }
    } finally {
      if (mountedRef.current) setDetailLoading(false);
    }
  };

  const handleReload = async () => {
    try {
      const count = await reloadSkills();
      message.success(`已重新加载 ${count} 个技能`);
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '热加载失败');
    }
  };

  const [editOpen, setEditOpen] = useState(false);
  const [editInitial, setEditInitial] = useState<SkillWritePayload | undefined>();
  const [editMode, setEditMode] = useState<'create' | 'update'>('create');
  const [submitting, setSubmitting] = useState(false);

  const handleCreate = () => {
    setEditMode('create');
    setEditInitial(undefined);
    setEditOpen(true);
  };

  const handleEdit = async (name: string) => {
    try {
      const detail = await getSkill(name);
      const { source: _s, enabled: _e, _path: _p, ...payload } = detail;
      setEditMode('update');
      setEditInitial(payload as SkillWritePayload);
      setEditOpen(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载技能详情失败');
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteSkill(name);
      message.success('已删除');
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleSubmit = async (payload: SkillWritePayload) => {
    setSubmitting(true);
    try {
      if (editMode === 'create') {
        await createSkill(payload);
        message.success('已创建');
      } else {
        await updateSkillContent(payload.name, payload);
        message.success('已保存');
      }
      setEditOpen(false);
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const columns: ColumnsType<SkillSummary> = [
    {
      title: '技能名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (name: string, record) => (
        <Space>
          <RobotOutlined />
          <Text strong>{record.title || name}</Text>
        </Space>
      )
    },
    {
      title: '标识',
      dataIndex: 'name',
      key: 'nameKey',
      width: 180,
      render: (name: string) => <Text code>{name}</Text>
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (cat: string) => <Tag>{cat}</Tag>
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (source: string) => (
        <Tag color={SOURCE_COLOR[source]}>{SOURCE_LABEL[source] || source}</Tag>
      )
    },
    {
      title: '触发词',
      dataIndex: 'triggers',
      key: 'triggers',
      width: 200,
      render: (triggers: string[]) =>
        triggers.length ? (
          <Space size={[4, 4]} wrap>
            {triggers.map((t) => (
              <Tag key={t} color="purple">
                {t}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">-</Text>
        )
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record) => (
        <Tooltip
          title={
            !canManage
              ? '需要 ai:admin 权限'
              : record.source === 'builtin'
                ? '内置技能不可禁用'
                : ''
          }
        >
          <Switch
            checked={enabled}
            disabled={record.source === 'builtin' || !canManage}
            onChange={(checked) => handleToggle(record.name, checked, record.source)}
          />
        </Tooltip>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewDetail(record.name)}>
            详情
          </Button>
          {canManage && record.source === 'custom' && (
            <>
              <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record.name)}>
                编辑
              </Button>
              <Popconfirm
                title="确认删除该技能？"
                description={`将永久删除 ${record.name}，此操作不可恢复。`}
                onConfirm={() => handleDelete(record.name)}
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
              >
                <Button type="link" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
      )
    }
  ];

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined />
          <span>AI 技能管理</span>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchSkills} loading={loading}>
            刷新
          </Button>
          {/* 回归复查 F1 修复：热加载为 ai:admin 写操作，无权限者不展示 */}
          {canManage && (
            <>
              <Button icon={<PlusOutlined />} onClick={handleCreate}>
                新建技能
              </Button>
              <Button type="primary" icon={<ReloadOutlined />} onClick={handleReload}>
                热加载
              </Button>
            </>
          )}
        </Space>
      }
    >
      {/* F10 修复：8 列合计约 950px 固定宽，移动端（375px）列被强行压缩、
          内容换行错乱。加横向滚动，配合"描述"列的 ellipsis 生效。 */}
      <Table
        rowKey="name"
        columns={columns}
        dataSource={skills}
        loading={loading}
        pagination={false}
        size="middle"
        scroll={{ x: 'max-content' }}
      />

      <Drawer
        title="技能详情"
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setDetail(null);
        }}
        width="90%"
        style={{ maxWidth: 640 }}
        loading={detailLoading}
      >
        {detail && (
          <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
            {/* F12 修复：原固定 2 列在移动端过窄，改为按断点自适应 */}
            <Descriptions column={{ xs: 1, sm: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label="名称" span={2}>
                {detail.title || detail.name}
              </Descriptions.Item>
              <Descriptions.Item label="标识">
                <Text code>{detail.name}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="版本">{detail.version}</Descriptions.Item>
              <Descriptions.Item label="分类">
                <Tag>{detail.category}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                <Tag color={SOURCE_COLOR[detail.source]}>
                  {SOURCE_LABEL[detail.source] || detail.source}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {detail.description}
              </Descriptions.Item>
              <Descriptions.Item label="触发词" span={2}>
                {(detail.triggers ?? []).length ? (
                  <Space size={[4, 4]} wrap>
                    {(detail.triggers ?? []).map((t) => (
                      <Tag key={t} color="purple">
                        {t}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">-</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="参数" span={2}>
                {(detail.params ?? []).length ? (
                  <Space direction="vertical" size="small">
                    {(detail.params ?? []).map((p) => (
                      <Text key={p.name} code>
                        {p.name}
                        {p.required ? ' *' : ''}: {p.type}
                        {p.description ? ` — ${p.description}` : ''}
                      </Text>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">无</Text>
                )}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="执行步骤" type="inner">
              <Space direction="vertical" size="small" style={{ display: 'flex' }}>
                {(detail.steps ?? []).map((step, idx) => (
                  <div key={step.id}>
                    <Text strong>
                      {idx + 1}. {step.id}
                    </Text>{' '}
                    <Tag color="cyan">{step.call}</Tag>
                    {step.output && (
                      <Tooltip title="输出变量">
                        <Tag color="gold">→ {step.output}</Tag>
                      </Tooltip>
                    )}
                    {step.when && (
                      <Tooltip title="条件">
                        <Tag color="orange">when: {step.when}</Tag>
                      </Tooltip>
                    )}
                  </div>
                ))}
              </Space>
            </Card>

            {detail._path && (
              <Card size="small" title="文件路径" type="inner">
                <Paragraph code copyable>
                  {detail._path}
                </Paragraph>
              </Card>
            )}
          </Space>
        )}
      </Drawer>

      {/* 创建/编辑技能 Modal（方案 §4.3） */}
      <Modal
        title={editMode === 'create' ? '新建技能' : '编辑技能'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        footer={null}
        width="90%"
        style={{ maxWidth: 720 }}
        destroyOnClose
      >
        <SkillEditForm
          initial={editInitial}
          onSubmit={handleSubmit}
          onCancel={() => setEditOpen(false)}
          submitting={submitting}
        />
      </Modal>
    </Card>
  );
}
