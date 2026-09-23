/**
 * 监控中心 - 凭据管理页（增强版）
 *
 * 布局：顶部统计概览 + 左右分栏
 * 1. 顶部：协议分类卡片 + 汇总信息，点击协议卡片快速筛选
 * 2. 左栏：搜索框 + 协议筛选 + 凭据列表（多选支持批量删除）
 * 3. 右栏：选中凭据详情卡片 + 关联设备表（含搜索）
 * 4. 新建/编辑密文弹窗复用 MonitorCredentialForm
 *
 * 安全约束：密文永不回显；编辑时密码字段留空表示「保持不变」。
 *
 * M26：从单文件 903 行拆分为 3 个 Modal（Create/Edit/Link）+ CredentialDetail
 * + index.tsx（列表+统计+状态管理），本文件仅做列表与状态编排。
 */
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Card,
  Col,
  Row,
  Tag,
  Button,
  Space,
  Form,
  Input,
  Switch,
  Typography,
  Tooltip,
  Alert,
  Statistic
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EditOutlined,
  WarningOutlined,
  SearchOutlined,
  KeyOutlined,
  ApiOutlined,
  SafetyCertificateOutlined,
  DashboardOutlined
} from '@ant-design/icons';
import { MONITOR_PROTOCOL_OPTIONS, MONITOR_PROTOCOL_COLOR_MAP } from '@/types/enums';
import {
  useMonitorCredentials,
  usePatchCredential,
  useDeleteCredential,
  useBatchDeleteCredentials,
  type MonitorCredentialListItem
} from '@/services/monitor';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import CreateCredentialModal from './CreateCredentialModal';
import EditCredentialModal from './EditCredentialModal';
import LinkDeviceModal from './LinkDeviceModal';
import CredentialDetail from './CredentialDetail';
import { useTranslation } from 'react-i18next';

const { Text, Paragraph } = Typography;

const PROTOCOL_ICONS: Record<string, React.ReactNode> = {
  snmp: <DashboardOutlined />,
  ipmi: <SafetyCertificateOutlined />,
  zabbix: <KeyOutlined />,
  ping: <ApiOutlined />
};

export default function MonitorCredentials() {
  const msg = useMessage();
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');

  const { data: creds = [], isLoading: credsLoading, refetch } = useMonitorCredentials();
  const [selectedCredId, setSelectedCredId] = useState<number | null>(null);

  const patchCred = usePatchCredential();
  const deleteCred = useDeleteCredential();
  const batchDeleteCred = useBatchDeleteCredentials();

  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const formDisclosure = useDisclosure();
  const link = useDisclosure();
  const edit = useDisclosure();
  const [editCred, setEditCred] = useState<MonitorCredentialListItem | null>(null);

  const [searchKeyword, setSearchKeyword] = useState('');
  const [protocolFilter, setProtocolFilter] = useState<string[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const credTable = useTable({ initialPerPage: 15 });

  const selectedCred = (creds as MonitorCredentialListItem[]).find((c) => c.id === selectedCredId);

  const stats = useMemo(() => {
    const list = creds as MonitorCredentialListItem[];
    const total = list.length;
    const totalLinked = list.reduce((sum, c) => sum + (c.linked_count ?? 0), 0);
    const disabledCount = list.filter((c) => !c.enabled).length;
    const byProtocol: Record<string, number> = {};
    for (const c of list) {
      const p = c.protocol || 'unknown';
      byProtocol[p] = (byProtocol[p] || 0) + 1;
    }
    return { total, totalLinked, disabledCount, byProtocol };
  }, [creds]);

  const filteredCreds = useMemo(() => {
    const list = creds as MonitorCredentialListItem[];
    return list.filter((c) => {
      if (searchKeyword) {
        const name = (c.name || `${c.protocol} #${c.id}`).toLowerCase();
        if (!name.includes(searchKeyword.toLowerCase())) return false;
      }
      if (protocolFilter.length > 0 && !protocolFilter.includes(c.protocol || '')) {
        return false;
      }
      return true;
    });
  }, [creds, searchKeyword, protocolFilter]);

  const handleToggleEnabled = async (credId: number, enabled: boolean) => {
    try {
      await patchCred.mutateAsync({ credentialId: credId, enabled });
      msg.success(enabled ? t('settings.enabled') : t('settings.disabled'));
    } catch (err) {
      msg.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const handleRename = async (credId: number, newName: string) => {
    try {
      await patchCred.mutateAsync({ credentialId: credId, name: newName || undefined });
      msg.success(t('credential.message.renamed'));
    } catch (err) {
      msg.error(err instanceof Error ? err.message : t('credential.message.renameFailed'));
    }
  };

  const handleDeleteCred = async (credId: number) => {
    try {
      await deleteCred.mutateAsync(credId);
      msg.success(t('credential.message.deleted'));
      if (selectedCredId === credId) setSelectedCredId(null);
      setSelectedRowKeys((prev) => prev.filter((k) => k !== credId));
    } catch (err) {
      msg.error(err instanceof Error ? err.message : tc('message.deleteFailed'));
    }
  };

  const handleBatchDelete = async () => {
    const list = creds as MonitorCredentialListItem[];
    const toDelete = selectedRowKeys
      .map((k) => list.find((c) => c.id === k))
      .filter((c): c is MonitorCredentialListItem => !!c && (c.linked_count ?? 0) === 0);
    const skipped = selectedRowKeys.length - toDelete.length;

    if (toDelete.length === 0) {
      msg.warning(t('credential.message.allLinked'));
      return;
    }

    try {
      const result = await batchDeleteCred.mutateAsync(toDelete.map((c) => c.id!));
      const failedCount = result.failed.length;
      if (failedCount > 0) {
        result.failed.forEach((f) => {
          msg.error(t('credential.message.deleteItemFailed', { id: f.id, reason: f.reason }));
        });
        if (result.deleted > 0) {
          msg.success(
            skipped > 0
              ? t('credential.message.batchDeletedSkippedFailed', {
                  count: result.deleted,
                  skipped,
                  failed: failedCount
                })
              : t('credential.message.batchDeletedFailed', {
                  count: result.deleted,
                  failed: failedCount
                })
          );
        }
      } else {
        msg.success(
          skipped > 0
            ? t('credential.message.batchDeletedSkipped', { count: result.deleted, skipped })
            : t('credential.message.batchDeleted', { count: result.deleted })
        );
      }
    } catch {
      msg.error(t('credential.message.batchDeleteFailed'));
    }
    setSelectedRowKeys([]);
  };

  const handleOpenEdit = (cred: MonitorCredentialListItem) => {
    setEditCred(cred);
    edit.open();
  };

  const credColumns = [
    {
      title: tc('field.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string | null, record: MonitorCredentialListItem) => (
        <Paragraph
          editable={{
            onChange: (newName) => handleRename(record.id!, newName),
            triggerType: ['icon', 'text']
          }}
          style={{
            margin: 0,
            color: record.enabled ? undefined : 'rgba(0,0,0,0.45)'
          }}
        >
          {name || `${record.protocol} #${record.id}`}
        </Paragraph>
      )
    },
    {
      title: t('column.protocol'),
      dataIndex: 'protocol',
      key: 'protocol',
      width: 90,
      render: (p: string) => (
        <Tag color={MONITOR_PROTOCOL_COLOR_MAP[p] || 'default'}>{p?.toUpperCase()}</Tag>
      )
    },
    {
      title: t('credential.column.linkedDevices'),
      dataIndex: 'linked_count',
      key: 'linked_count',
      width: 90,
      align: 'center' as const,
      render: (count: number) => (
        <span
          style={{ fontWeight: count > 0 ? 500 : 400, color: count > 0 ? undefined : '#fa8c16' }}
        >
          {count || 0}
        </span>
      )
    },
    {
      title: tc('field.status'),
      key: 'status',
      width: 110,
      render: (_: unknown, record: MonitorCredentialListItem) => (
        <Space size={4}>
          {!record.enabled && <Tag>{t('credential.status.disabled')}</Tag>}
          {(record.linked_count ?? 0) === 0 && (
            <Tag color="orange">{t('credential.status.unlinked')}</Tag>
          )}
          {record.enabled && (record.linked_count ?? 0) > 0 && (
            <Tag color="green">{t('alertPopover.normal')}</Tag>
          )}
        </Space>
      )
    },
    {
      title: tc('action.enable'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 60,
      render: (enabled: boolean, record: MonitorCredentialListItem) => (
        <Switch
          size="small"
          checked={enabled}
          loading={patchCred.isPending}
          onChange={(checked) => handleToggleEnabled(record.id!, checked)}
        />
      )
    },
    {
      title: tc('field.actions'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: MonitorCredentialListItem) => (
        <Space size="small">
          <Tooltip title={t('credential.tooltip.editSecret')}>
            <Button size="small" icon={<EditOutlined />} onClick={() => handleOpenEdit(record)} />
          </Tooltip>
          <Tooltip
            title={
              record.linked_count
                ? t('credential.tooltip.deleteLinked')
                : t('credential.tooltip.deleteShared')
            }
          >
            <ConfirmButton
              size="small"
              icon={<DeleteOutlined />}
              title={t('credential.confirm.deleteTitle')}
              content={
                record.linked_count
                  ? t('credential.confirm.deleteLinkedContent', { count: record.linked_count })
                  : undefined
              }
              okType="danger"
              disabled={!!record.linked_count}
              onConfirm={() => handleDeleteCred(record.id!)}
            />
          </Tooltip>
        </Space>
      )
    }
  ];

  return (
    <div>
      {/* ── 顶部统计概览 ─────────────────────────────────────── */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {MONITOR_PROTOCOL_OPTIONS.map((opt) => {
          const count = stats.byProtocol[opt.value] || 0;
          const isActive = protocolFilter.includes(opt.value);
          return (
            <Col key={opt.value} xs={12} sm={6}>
              <Card
                hoverable
                size="small"
                style={{
                  cursor: 'pointer',
                  borderColor: isActive ? MONITOR_PROTOCOL_COLOR_MAP[opt.value] : undefined,
                  borderWidth: isActive ? 2 : 1
                }}
                onClick={() => {
                  setProtocolFilter((prev) =>
                    prev.includes(opt.value)
                      ? prev.filter((p) => p !== opt.value)
                      : [...prev, opt.value]
                  );
                }}
              >
                <Statistic
                  title={opt.label}
                  value={count}
                  prefix={
                    <span style={{ color: MONITOR_PROTOCOL_COLOR_MAP[opt.value] || '#999' }}>
                      {PROTOCOL_ICONS[opt.value]}
                    </span>
                  }
                  styles={{ content: { fontSize: 24, fontWeight: 600 } }}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* ── 汇总信息 ────────────────────────────────────────── */}
      <div style={{ marginBottom: 16, padding: '8px 0' }}>
        <Space size="large">
          <Text type="secondary">{t('credential.summary.total', { count: stats.total })}</Text>
          <Text type="secondary">
            {t('credential.summary.linked', { count: stats.totalLinked })}
          </Text>
          {stats.disabledCount > 0 && (
            <Text type="warning">
              <WarningOutlined style={{ marginRight: 4 }} />
              {t('credential.summary.disabled', { count: stats.disabledCount })}
            </Text>
          )}
        </Space>
      </div>

      <Row gutter={16}>
        {/* ── 左栏：凭据列表 ─────────────────────────────────── */}
        <Col xs={24} lg={10}>
          <Card
            title={t('credential.title')}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
                  {tc('action.refresh')}
                </Button>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => formDisclosure.open()}
                >
                  {t('credential.action.create')}
                </Button>
              </Space>
            }
          >
            {/* 搜索框 */}
            <Input
              placeholder={t('credential.searchPlaceholder')}
              prefix={<SearchOutlined />}
              allowClear
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              style={{ marginBottom: 12 }}
            />

            {/* 协议筛选 Tags */}
            <Space size={[4, 8]} wrap style={{ marginBottom: 12 }}>
              <Tag
                style={{ cursor: 'pointer', padding: '2px 8px' }}
                color={protocolFilter.length === 0 ? 'blue' : 'default'}
                onClick={() => setProtocolFilter([])}
              >
                {t('filter.all')}
              </Tag>
              {MONITOR_PROTOCOL_OPTIONS.map((opt) => (
                <Tag
                  key={opt.value}
                  style={{ cursor: 'pointer', padding: '2px 8px' }}
                  color={protocolFilter.includes(opt.value) ? opt.value : 'default'}
                  onClick={() => {
                    setProtocolFilter((prev) =>
                      prev.includes(opt.value)
                        ? prev.filter((p) => p !== opt.value)
                        : [...prev, opt.value]
                    );
                  }}
                >
                  {opt.label}
                </Tag>
              ))}
            </Space>

            {/* 批量操作栏 */}
            {selectedRowKeys.length > 0 && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message={
                  <Space>
                    <Text>{t('credential.batch.selected', { count: selectedRowKeys.length })}</Text>
                    <ConfirmButton
                      size="small"
                      icon={<DeleteOutlined />}
                      title={t('credential.confirm.batchDeleteTitle')}
                      content={t('credential.confirm.batchDeleteContent')}
                      okType="danger"
                      onConfirm={handleBatchDelete}
                    >
                      {tc('action.batchDelete')}
                    </ConfirmButton>
                    <Button size="small" type="link" onClick={() => setSelectedRowKeys([])}>
                      {tc('batch.clear')}
                    </Button>
                  </Space>
                }
              />
            )}

            <DataTable<MonitorCredentialListItem>
              columns={credColumns}
              dataSource={filteredCreds}
              loading={credsLoading}
              rowKey={(r) => String(r.id)}
              total={filteredCreds.length}
              emptyText={t('credential.empty')}
              searchable={false}
              showCard={false}
              tableProps={credTable}
              rowSelection={{
                type: 'checkbox',
                selectedRowKeys: selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys as number[])
              }}
              onRow={(record) => ({
                onClick: () => setSelectedCredId(record.id ?? null),
                style: { cursor: 'pointer' }
              })}
            />
          </Card>
        </Col>

        {/* ── 右栏：凭据详情 + 关联设备 ────────────────────── */}
        <Col xs={24} lg={14}>
          <CredentialDetail selectedCred={selectedCred} onOpenLink={() => link.open()} />
        </Col>
      </Row>

      {/* ── 新建凭据弹窗 ────────────────────────────────────── */}
      <CreateCredentialModal
        open={formDisclosure.isOpen}
        form={form}
        onClose={() => {
          formDisclosure.close();
          form.resetFields();
        }}
      />

      {/* ── 编辑密文弹窗 ────────────────────────────────────── */}
      <EditCredentialModal
        open={edit.isOpen}
        editCred={editCred}
        editForm={editForm}
        onClose={() => {
          edit.close();
          editForm.resetFields!();
        }}
      />

      {/* ── 关联设备弹窗 ────────────────────────────────────── */}
      <LinkDeviceModal
        open={link.isOpen}
        selectedCredId={selectedCredId}
        selectedCredName={selectedCred?.name ?? undefined}
        selectedCredProtocol={selectedCred?.protocol}
        onClose={() => link.close()}
      />
    </div>
  );
}
