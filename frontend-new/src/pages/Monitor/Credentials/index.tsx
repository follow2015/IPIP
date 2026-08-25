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

const { Text, Paragraph } = Typography;

const PROTOCOL_ICONS: Record<string, React.ReactNode> = {
  snmp: <DashboardOutlined />,
  ipmi: <SafetyCertificateOutlined />,
  zabbix: <KeyOutlined />,
  ping: <ApiOutlined />
};

export default function MonitorCredentials() {
  const msg = useMessage();

  const { data: creds = [], isLoading: credsLoading, refetch } = useMonitorCredentials();
  const [selectedCredId, setSelectedCredId] = useState<number | null>(null);

  const patchCred = usePatchCredential();
  const deleteCred = useDeleteCredential();
  const batchDeleteCred = useBatchDeleteCredentials();

  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [formOpen, setFormOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
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
      msg.success(enabled ? '已启用' : '已禁用');
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const handleRename = async (credId: number, newName: string) => {
    try {
      await patchCred.mutateAsync({ credentialId: credId, name: newName || undefined });
      msg.success('已更新名称');
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '改名失败');
    }
  };

  const handleDeleteCred = async (credId: number) => {
    try {
      await deleteCred.mutateAsync(credId);
      msg.success('凭据已删除');
      if (selectedCredId === credId) setSelectedCredId(null);
      setSelectedRowKeys((prev) => prev.filter((k) => k !== credId));
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleBatchDelete = async () => {
    const list = creds as MonitorCredentialListItem[];
    const toDelete = selectedRowKeys
      .map((k) => list.find((c) => c.id === k))
      .filter((c): c is MonitorCredentialListItem => !!c && (c.linked_count ?? 0) === 0);
    const skipped = selectedRowKeys.length - toDelete.length;

    if (toDelete.length === 0) {
      msg.warning('所选凭据均有关联设备，无法删除');
      return;
    }

    try {
      const result = await batchDeleteCred.mutateAsync(toDelete.map((c) => c.id!));
      if (result.failed.length > 0) {
        result.failed.forEach((f) => {
          msg.error(`凭据 #${f.id} 删除失败：${f.reason}`);
        });
        if (result.deleted > 0) {
          msg.success(
            `已删除 ${result.deleted} 条凭据${skipped > 0 ? `，跳过 ${skipped} 条（有关联设备）` : ''}，${result.failed.length} 条失败`
          );
        }
      } else {
        msg.success(
          `已删除 ${result.deleted} 条凭据${skipped > 0 ? `，跳过 ${skipped} 条（有关联设备）` : ''}`
        );
      }
    } catch {
      msg.error('批量删除失败');
    }
    setSelectedRowKeys([]);
  };

  const handleOpenEdit = (cred: MonitorCredentialListItem) => {
    setEditCred(cred);
    setEditOpen(true);
  };

  const credColumns = [
    {
      title: '名称',
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
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 90,
      render: (p: string) => (
        <Tag color={MONITOR_PROTOCOL_COLOR_MAP[p] || 'default'}>{p?.toUpperCase()}</Tag>
      )
    },
    {
      title: '关联设备',
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
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: unknown, record: MonitorCredentialListItem) => (
        <Space size={4}>
          {!record.enabled && <Tag>已停用</Tag>}
          {(record.linked_count ?? 0) === 0 && <Tag color="orange">无关联</Tag>}
          {record.enabled && (record.linked_count ?? 0) > 0 && <Tag color="green">正常</Tag>}
        </Space>
      )
    },
    {
      title: '启用',
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
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: MonitorCredentialListItem) => (
        <Space size="small">
          <Tooltip title="编辑密文（影响全部关联设备）">
            <Button size="small" icon={<EditOutlined />} onClick={() => handleOpenEdit(record)} />
          </Tooltip>
          <Tooltip title={record.linked_count ? '请先取消所有设备关联' : '删除共享凭据'}>
            <ConfirmButton
              size="small"
              icon={<DeleteOutlined />}
              title="确认删除此共享凭据？"
              content={
                record.linked_count ? `仍关联 ${record.linked_count} 台设备，无法删除` : undefined
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
          <Text type="secondary">
            共 <Text strong>{stats.total}</Text> 条凭据
          </Text>
          <Text type="secondary">
            关联 <Text strong>{stats.totalLinked}</Text> 台设备
          </Text>
          {stats.disabledCount > 0 && (
            <Text type="warning">
              <WarningOutlined style={{ marginRight: 4 }} />
              {stats.disabledCount} 条已停用
            </Text>
          )}
        </Space>
      </div>

      <Row gutter={16}>
        {/* ── 左栏：凭据列表 ─────────────────────────────────── */}
        <Col xs={24} lg={10}>
          <Card
            title="共享凭据"
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
                  刷新
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>
                  新建凭据
                </Button>
              </Space>
            }
          >
            {/* 搜索框 */}
            <Input
              placeholder="搜索凭据名称"
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
                全部
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
                    <Text>已选 {selectedRowKeys.length} 项</Text>
                    <ConfirmButton
                      size="small"
                      icon={<DeleteOutlined />}
                      title="确认批量删除？"
                      content="仅删除无关联设备的凭据，有关联的将跳过。"
                      okType="danger"
                      onConfirm={handleBatchDelete}
                    >
                      批量删除
                    </ConfirmButton>
                    <Button size="small" type="link" onClick={() => setSelectedRowKeys([])}>
                      取消选择
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
              emptyText="暂无共享凭据"
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
          <CredentialDetail selectedCred={selectedCred} onOpenLink={() => setLinkOpen(true)} />
        </Col>
      </Row>

      {/* ── 新建凭据弹窗 ────────────────────────────────────── */}
      <CreateCredentialModal
        open={formOpen}
        form={form}
        onClose={() => {
          setFormOpen(false);
          form.resetFields();
        }}
      />

      {/* ── 编辑密文弹窗 ────────────────────────────────────── */}
      <EditCredentialModal
        open={editOpen}
        editCred={editCred}
        editForm={editForm}
        onClose={() => {
          setEditOpen(false);
          editForm.resetFields!();
        }}
      />

      {/* ── 关联设备弹窗 ────────────────────────────────────── */}
      <LinkDeviceModal
        open={linkOpen}
        selectedCredId={selectedCredId}
        selectedCredName={selectedCred?.name ?? undefined}
        selectedCredProtocol={selectedCred?.protocol}
        onClose={() => setLinkOpen(false)}
      />
    </div>
  );
}
