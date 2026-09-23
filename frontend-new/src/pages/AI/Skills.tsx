import { useState, useCallback, useEffect, useRef } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Tag,
  Switch,
  Button,
  Space,
  Drawer,
  Descriptions,
  Tooltip,
  Typography,
  Modal
} from 'antd';
import DataTable from '@/components/DataTable';
import { useConfirm } from '@/utils/confirm';
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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const { Text, Paragraph } = Typography;

const SOURCE_COLOR: Record<string, string> = { builtin: 'blue', custom: 'green' };

type SkillSourceLabelKey = 'skills.source.builtin' | 'skills.source.custom';

const SOURCE_LABEL_KEYS: Record<string, SkillSourceLabelKey> = {
  builtin: 'skills.source.builtin',
  custom: 'skills.source.custom'
};

const sourceLabel = (source: string, t: TFunction<'ai'>) => {
  const key = SOURCE_LABEL_KEYS[source];
  return key ? t(key) : source;
};

export default function Skills() {
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const drawer = useDisclosure();
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
        message.error(err instanceof Error ? err.message : t('skills.message.loadFailed'));
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleToggle = async (name: string, enabled: boolean, source: string) => {
    if (source === 'builtin') {
      message.warning(t('skills.message.builtinCannotDisable'));
      return;
    }
    try {
      await toggleSkill(name, enabled);
      setSkills((prev) => prev.map((s) => (s.name === name ? { ...s, enabled } : s)));
      message.success(enabled ? t('skills.message.enabled') : t('skills.message.disabled'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const handleViewDetail = async (name: string) => {
    drawer.open();
    setDetailLoading(true);
    try {
      const data = await getSkill(name);
      if (mountedRef.current) setDetail(data);
    } catch (err) {
      if (mountedRef.current) {
        message.error(err instanceof Error ? err.message : t('skills.message.loadDetailFailed'));
      }
    } finally {
      if (mountedRef.current) setDetailLoading(false);
    }
  };

  const handleReload = async () => {
    try {
      const count = await reloadSkills();
      message.success(t('skills.message.reloaded', { count }));
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('skills.message.reloadFailed'));
    }
  };

  const edit = useDisclosure();
  const [editInitial, setEditInitial] = useState<SkillWritePayload | undefined>();
  const [editMode, setEditMode] = useState<'create' | 'update'>('create');
  const [submitting, setSubmitting] = useState(false);

  const handleCreate = () => {
    setEditMode('create');
    setEditInitial(undefined);
    edit.open();
  };

  const handleEdit = async (name: string) => {
    try {
      const detail = await getSkill(name);
      const { source: _s, enabled: _e, _path: _p, ...payload } = detail;
      setEditMode('update');
      setEditInitial(payload as SkillWritePayload);
      edit.open();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('skills.message.loadSkillDetailFailed'));
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteSkill(name);
      message.success(tc('message.deleteSuccess'));
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const handleSubmit = async (payload: SkillWritePayload) => {
    setSubmitting(true);
    try {
      if (editMode === 'create') {
        await createSkill(payload);
        message.success(tc('message.createSuccess'));
      } else {
        await updateSkillContent(payload.name, payload);
        message.success(t('skills.message.saved'));
      }
      edit.close();
      fetchSkills();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('skills.message.saveFailed'));
    } finally {
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const columns: ColumnsType<SkillSummary> = [
    {
      title: t('skills.column.name'),
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
      title: t('skills.field.identifier'),
      dataIndex: 'name',
      key: 'nameKey',
      width: 180,
      render: (name: string) => <Text code>{name}</Text>
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true
    },
    {
      title: t('skills.field.category'),
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (cat: string) => <Tag>{cat}</Tag>
    },
    {
      title: tc('field.source'),
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (source: string) => (
        <Tag color={SOURCE_COLOR[source]}>{sourceLabel(source, t)}</Tag>
      )
    },
    {
      title: t('skills.field.triggers'),
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
      title: tc('action.enable'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record) => (
        <Tooltip
          title={
            !canManage
              ? t('skills.tooltip.needAdmin')
              : record.source === 'builtin'
                ? t('skills.tooltip.builtinCannotDisable')
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
      title: tc('field.actions'),
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewDetail(record.name)}>
            {tc('action.detail')}
          </Button>
          {canManage && record.source === 'custom' && (
            <>
              <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record.name)}>
                {tc('action.edit')}
              </Button>
              <Button
                type="link"
                danger
                icon={<DeleteOutlined />}
                onClick={() =>
                  confirm({
                    title: t('skills.deleteConfirm.title'),
                    content: t('skills.deleteConfirm.content', { name: record.name }),
                    okText: tc('action.delete'),
                    cancelText: tc('action.cancel'),
                    okButtonProps: { danger: true },
                    onOk: () => handleDelete(record.name)
                  })
                }
              >
                {tc('action.delete')}
              </Button>
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
          <span>{t('skills.title')}</span>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchSkills} loading={loading}>
            {tc('action.refresh')}
          </Button>
          {/* 回归复查 F1 修复：热加载为 ai:admin 写操作，无权限者不展示 */}
          {canManage && (
            <>
              <Button icon={<PlusOutlined />} onClick={handleCreate}>
                {t('skills.action.create')}
              </Button>
              <Button type="primary" icon={<ReloadOutlined />} onClick={handleReload}>
                {t('skills.action.reload')}
              </Button>
            </>
          )}
        </Space>
      }
    >
      {/* F10 修复：8 列合计约 950px 固定宽，移动端（375px）列被强行压缩、
          内容换行错乱。加横向滚动，配合"描述"列的 ellipsis 生效。 */}
      <DataTable
        rowKey="name"
        columns={columns}
        dataSource={skills}
        loading={loading}
        pagination={false}
        size="middle"
        scroll={{ x: 'max-content' }}
        showCard={false}
        searchable={false}
      />

      <Drawer
        title={t('skills.detail.title')}
        open={drawer.isOpen}
        onClose={() => {
          drawer.close();
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
              <Descriptions.Item label={tc('field.name')} span={2}>
                {detail.title || detail.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('skills.field.identifier')}>
                <Text code>{detail.name}</Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('skills.field.version')}>
                {detail.version}
              </Descriptions.Item>
              <Descriptions.Item label={t('skills.field.category')}>
                <Tag>{detail.category}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.source')}>
                <Tag color={SOURCE_COLOR[detail.source]}>{sourceLabel(detail.source, t)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={tc('field.description')} span={2}>
                {detail.description}
              </Descriptions.Item>
              <Descriptions.Item label={t('skills.field.triggers')} span={2}>
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
              <Descriptions.Item label={t('skills.field.params')} span={2}>
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
                  <Text type="secondary">{t('skills.field.none')}</Text>
                )}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title={t('skills.detail.steps')} type="inner">
              <Space direction="vertical" size="small" style={{ display: 'flex' }}>
                {(detail.steps ?? []).map((step, idx) => (
                  <div key={step.id}>
                    <Text strong>
                      {idx + 1}. {step.id}
                    </Text>{' '}
                    <Tag color="cyan">{step.call}</Tag>
                    {step.output && (
                      <Tooltip title={t('skills.detail.outputVar')}>
                        <Tag color="gold">→ {step.output}</Tag>
                      </Tooltip>
                    )}
                    {step.when && (
                      <Tooltip title={t('skills.detail.condition')}>
                        <Tag color="orange">when: {step.when}</Tag>
                      </Tooltip>
                    )}
                  </div>
                ))}
              </Space>
            </Card>

            {detail._path && (
              <Card size="small" title={t('skills.detail.filePath')} type="inner">
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
        title={editMode === 'create' ? t('skills.action.create') : t('skills.detail.editTitle')}
        open={edit.isOpen}
        onCancel={() => edit.close()}
        footer={null}
        width="90%"
        style={{ maxWidth: 720 }}
        destroyOnClose
      >
        <SkillEditForm
          initial={editInitial}
          onSubmit={handleSubmit}
          onCancel={() => edit.close()}
          submitting={submitting}
        />
      </Modal>
    </Card>
  );
}
