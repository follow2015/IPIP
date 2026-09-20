/**
 * 指标模板管理页：运维可在线新增/编辑/启停/删除监控指标与阈值。
 * 阈值按 metric_type 结构化输入与友好展示，避免手敲 JSON。
 *
 * M27：从单文件 805 行拆分为 shared.tsx（常量+工具）+ MetricTemplateModal.tsx（表单）
 * + index.tsx（列表+批量操作），本文件仅做列表与状态管理。
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
  Alert,
  Statistic,
  Row,
  Col,
  Tooltip,
  Typography
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SearchOutlined,
  CheckOutlined,
  StopOutlined
} from '@ant-design/icons';
import { useConfirm } from '@/utils/confirm';
import { useMessage } from '@/hooks/useMessage';
import { useResetPageOnDeps } from '@/hooks/useResetPageOnDeps';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import DataTable from '@/components/DataTable';
import ConfirmButton from '@/components/ConfirmButton';
import { BatchActionBar } from '@/components/BatchActionBar';
import {
  useMetricTemplates,
  useUpsertMetricTemplate,
  useDeleteMetricTemplate,
  useBatchDeleteMetricTemplates,
  useBatchToggleMetricTemplateEnabled,
  useVendorBrands,
  useMetricTemplateOidAudit,
  type MetricTemplateItem,
  type MetricTemplateOidAuditItem
} from '@/services/monitor';
import {
  DEVICE_TYPE_LABEL,
  SOURCE_LABEL,
  METRIC_TYPE_LABEL,
  DEVICE_TYPE_OPTIONS,
  SOURCE_OPTIONS,
  parseThreshold,
  renderThreshold,
  type MetricTemplateFormValues
} from './shared';
import MetricTemplateModal from './MetricTemplateModal';
import MetricTemplateGroupsSection from './MetricTemplateGroupsSection';

const { Text } = Typography;

export default function MetricTemplatesPage() {
  const confirm = useConfirm();
  const { data, isLoading } = useMetricTemplates();
  const upsert = useUpsertMetricTemplate();
  const deleteMutation = useDeleteMetricTemplate();
  const batchDeleteMut = useBatchDeleteMetricTemplates();
  const batchToggleMut = useBatchToggleMetricTemplateEnabled();
  const { data: vendorBrands } = useVendorBrands();
  const message = useMessage();

  const {
    data: oidAudit,
    isFetching: auditFetching,
    refetch: refetchAudit
  } = useMetricTemplateOidAudit();

  const vendorLabelMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const v of vendorBrands?.items ?? []) {
      if (!m.has(v.enterprise_no)) m.set(v.enterprise_no, v.label);
    }
    return m;
  }, [vendorBrands]);
  const getVendorLabel = (vid: string | null | undefined) =>
    vid ? (vendorLabelMap.get(vid) ?? vid) : null;

  const oidAuditMap = useMemo(() => {
    const m = new Map<string, MetricTemplateOidAuditItem>();
    for (const it of oidAudit?.items ?? []) {
      m.set(`${it.device_type ?? ''}::${it.metric_key ?? ''}`, it);
    }
    return m;
  }, [oidAudit]);

  const auditKeyOf = (r: MetricTemplateItem) => `${r.device_type ?? ''}::${r.metric_key ?? ''}`;

  const unresolvedCount = oidAudit?.unresolved ?? 0;

  const uncompiledVendorMibs = oidAudit?.vendor_uncompiled_mibs ?? [];

  const modal = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<MetricTemplateItem | null>(null);
  const [form] = Form.useForm<MetricTemplateFormValues>();
  const table = useTable({ initialPerPage: 20 });

  const [search, setSearch] = useState('');
  const [filterDeviceType, setFilterDeviceType] = useState<string | undefined>(undefined);
  const [filterSource, setFilterSource] = useState<string | undefined>(undefined);
  const [filterEnabled, setFilterEnabled] = useState<string | undefined>(undefined);

  useResetPageOnDeps(table.setPage, [search, filterDeviceType, filterSource, filterEnabled]);

  const allItems: MetricTemplateItem[] = data?.items ?? [];

  const batch = useBatchSelection<MetricTemplateItem>({
    dataSource: allItems,
    getRowKey: (r) => String(r.id ?? '')
  });

  const stats = useMemo(() => {
    const total = allItems.length;
    const enabled = allItems.filter((i) => i.enabled).length;
    const byDeviceType: Record<string, number> = {};
    for (const i of allItems) {
      const k = i.device_type ?? 'unknown';
      byDeviceType[k] = (byDeviceType[k] ?? 0) + 1;
    }
    return { total, enabled, byDeviceType };
  }, [allItems]);

  const filteredItems = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return allItems.filter((i) => {
      if (filterDeviceType && i.device_type !== filterDeviceType) return false;
      if (filterSource && i.source !== filterSource) return false;
      if (filterEnabled === 'enabled' && !i.enabled) return false;
      if (filterEnabled === 'disabled' && i.enabled) return false;
      if (!kw) return true;
      return (
        (i.metric_key ?? '').toLowerCase().includes(kw) ||
        (i.display_name ?? '').toLowerCase().includes(kw) ||
        (i.category ?? '').toLowerCase().includes(kw) ||
        (i.oid_symbol ?? '').toLowerCase().includes(kw) ||
        (i.oid ?? '').toLowerCase().includes(kw) ||
        (i.description ?? '').toLowerCase().includes(kw) ||
        (i.mib ?? '').toLowerCase().includes(kw)
      );
    });
  }, [allItems, search, filterDeviceType, filterSource, filterEnabled]);

  const openCreate = () => {
    setEditingRecord(null);
    form.resetFields();
    form.setFieldsValue({
      source: 'snmp',
      metric_type: 'gauge',
      poll_interval: 60,
      enabled: true
    });
    modal.open();
  };

  const openEdit = (record: MetricTemplateItem) => {
    setEditingRecord(record);
    form.setFieldsValue({
      device_type: record.device_type,
      metric_key: record.metric_key,
      category: record.category ?? undefined,
      display_name: record.display_name ?? undefined,
      vendor: record.vendor ?? undefined,
      source: record.source ?? 'snmp',
      mib: record.mib ?? undefined,
      oid_symbol: record.oid_symbol ?? undefined,
      oid: record.oid ?? undefined,
      zabbix_item_key: record.zabbix_item_key ?? undefined,
      index_kind: record.index_kind ?? undefined,
      metric_type: record.metric_type ?? 'gauge',
      unit: record.unit ?? undefined,
      poll_interval: record.poll_interval ?? 60,
      severity_default: record.severity_default ?? undefined,
      enabled: record.enabled ?? true,
      description: record.description ?? undefined,
      runbook_url: record.runbook_url ?? undefined,
      runbook_title: record.runbook_title ?? undefined,
      ...parseThreshold(record.threshold, record.metric_type ?? 'gauge')
    });
    modal.open();
  };

  const closeModal = () => {
    modal.close();
    setEditingRecord(null);
    form.resetFields();
  };

  const handleToggleEnabled = async (record: MetricTemplateItem, enabled: boolean) => {
    try {
      await upsert.mutateAsync({
        device_type: record.device_type!,
        metric_key: record.metric_key!,
        category: record.category,
        display_name: record.display_name,
        vendor: record.vendor,
        source: record.source,
        mib: record.mib,
        oid_symbol: record.oid_symbol,
        oid: record.oid,
        index_kind: record.index_kind,
        metric_type: record.metric_type,
        unit: record.unit,
        poll_interval: record.poll_interval,
        threshold: record.threshold,
        severity_default: record.severity_default,
        enabled,
        description: record.description
      });
      message.success(enabled ? '已启用' : '已停用');
    } catch {
      message.error('操作失败，请重试');
    }
  };

  const handleDelete = async (templateId: number) => {
    try {
      await deleteMutation.mutateAsync(templateId);
      message.success('指标模板已删除');
    } catch {
      message.error('删除失败，请重试');
    }
  };

  const handleBatchDelete = () => {
    confirm({
      title: `确认删除选中的 ${batch.count} 个指标模板？`,
      content: '删除后不可恢复，关联的指标告警规则将一并失效。',
      okType: 'danger',
      onOk: async () => {
        try {
          const ids = batch.selectedKeys.map((k) => Number(k));
          const res = await batchDeleteMut.mutateAsync(ids);
          message.success(`已删除 ${res.deleted} 个指标模板`);
          batch.clear();
        } catch {
          message.error('批量删除失败，请重试');
        }
      }
    });
  };

  const handleBatchToggleEnabled = (enabled: boolean) => {
    confirm({
      title: `确认${enabled ? '启用' : '停用'}选中的 ${batch.count} 个指标模板？`,
      content: enabled
        ? '启用后对应指标将恢复采集与告警判定。'
        : '停用后对应指标将停止采集，已产生的告警不受影响。',
      onOk: async () => {
        try {
          const ids = batch.selectedKeys.map((k) => Number(k));
          const res = await batchToggleMut.mutateAsync({ ids, enabled });
          message.success(`已${enabled ? '启用' : '停用'} ${res.updated} 个指标模板`);
          batch.clear();
        } catch {
          message.error('批量操作失败，请重试');
        }
      }
    });
  };

  const columns = [
    {
      title: '指标',
      dataIndex: 'metric_key',
      width: 180,
      render: (v: string, r: MetricTemplateItem) => (
        <Space size={4} direction="vertical" style={{ lineHeight: 1.2 }}>
          <Text strong>{r.display_name ?? v}</Text>
          {r.display_name && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {v}
            </Text>
          )}
        </Space>
      )
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (v: string) => (v ? <Tag color="geekblue">{v}</Tag> : '-')
    },
    {
      title: '厂商',
      dataIndex: 'vendor',
      width: 100,
      render: (v: string | null) => {
        const label = getVendorLabel(v);
        return label ? <Tag color="purple">{label}</Tag> : <Text type="secondary">全适用</Text>;
      }
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      width: 110,
      render: (v: string) => <Tag>{DEVICE_TYPE_LABEL[v] ?? v}</Tag>
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 90,
      render: (v: string) => <Tag color="blue">{SOURCE_LABEL[v] ?? v}</Tag>
    },
    {
      title: '类型',
      dataIndex: 'metric_type',
      width: 100,
      render: (v: string) => METRIC_TYPE_LABEL[v] ?? v
    },
    { title: 'MIB', dataIndex: 'mib', width: 110, render: (v: string) => v ?? '-' },
    {
      title: 'OID 符号',
      dataIndex: 'oid_symbol',
      width: 160,
      render: (v: string) =>
        v ? (
          <Text code style={{ fontSize: 12 }}>
            {v}
          </Text>
        ) : (
          '-'
        )
    },
    {
      title: '数字 OID',
      dataIndex: 'oid',
      width: 200,
      render: (v: string, r: MetricTemplateItem) => {
        const audit = oidAuditMap.get(auditKeyOf(r));
        return (
          <Space size={4}>
            {v ? (
              <Text code style={{ fontSize: 11 }}>
                {v}
              </Text>
            ) : (
              <Text type="secondary">-</Text>
            )}
            {/* 只有审计**明确判定**不可解析才标红。审计未返回 / 该行不在结果里
                时保持沉默 —— 猜成"正常"是假绿灯，猜成"坏"是误报，两者都糟。 */}
            {audit && !audit.resolvable && (
              <Tooltip title={audit.reason_label}>
                <Tag color="error">采不到</Tag>
              </Tooltip>
            )}
          </Space>
        );
      }
    },
    {
      title: '阈值',
      key: 'threshold',
      width: 200,
      render: (_: unknown, r: MetricTemplateItem) =>
        renderThreshold(r.threshold, r.metric_type ?? 'gauge')
    },
    {
      title: '采集频率',
      dataIndex: 'poll_interval',
      width: 100,
      render: (v: number) => (v ? `${v}s` : '-')
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 80,
      render: (v: boolean, record: MetricTemplateItem) => (
        <Switch
          checked={v}
          loading={upsert.isPending}
          onChange={(checked) => handleToggleEnabled(record, checked)}
        />
      )
    },
    {
      title: '说明',
      dataIndex: 'description',
      ellipsis: true,
      render: (v: string) => v ?? '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: MetricTemplateItem) => (
        <Space size={4}>
          <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <ConfirmButton
            type="text"
            icon={<DeleteOutlined />}
            title="确认删除该指标模板？"
            content="删除后不可恢复，关联的指标告警规则将一并失效。"
            okType="danger"
            loading={deleteMutation.isPending}
            onConfirm={() => handleDelete(record.id!)}
          >
            {null}
          </ConfirmButton>
        </Space>
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card variant="borderless">
        <Row gutter={16}>
          <Col xs={12} md={4}>
            <Statistic title="模板总数" value={stats.total} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="已启用" value={stats.enabled} />
          </Col>
          <Col xs={24} md={16}>
            <Statistic
              title="设备类型分布"
              valueRender={() => (
                <Space size={4} wrap>
                  {Object.entries(stats.byDeviceType).map(([t, c]) => (
                    <Tag key={t}>
                      {DEVICE_TYPE_LABEL[t] ?? t}: {c}
                    </Tag>
                  ))}
                </Space>
              )}
            />
          </Col>
        </Row>
      </Card>

      <MetricTemplateGroupsSection />

      <Card
        title="监控指标模板"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增指标
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="指标模板与阈值是告警生效的前置条件"
          description="设备需先启用监控并绑定凭据，再在此页面对应指标模板启用并配置阈值后，采集到的异常值才会触发告警。仅创建模板但未启用、或未配置阈值，均不会产生告警。"
        />
        {/* P2-6：OID 解析失败可见化。
            此前这条信息在界面上**根本不存在**：采集侧所有请求都带 lookupMib=False，
            解析不出数字 OID 的模板表现为「采集成功、但少了几项指标、且不报错」，
            运维只能靠"某个指标怎么一直没数据"反推。这里把本地判定结果摆到台面上。

            ⚠️ 审计未返回时**不渲染**（而不是渲染成绿色"正常"）：未知 ≠ 正常，
            把"还没查"显示成"没问题"正是本仓吃过亏的假绿灯。 */}
        {oidAudit && (
          <Alert
            type={unresolvedCount > 0 ? 'warning' : 'success'}
            showIcon
            style={{ marginBottom: 16 }}
            message={
              unresolvedCount > 0
                ? `有 ${unresolvedCount} 条指标模板解析不出 OID，永远不会采到数据`
                : `全部 ${oidAudit.total ?? 0} 条指标模板的 OID 均可解析`
            }
            action={
              <Button size="small" loading={auditFetching} onClick={() => refetchAudit()}>
                重新审计
              </Button>
            }
            description={
              unresolvedCount > 0 ? (
                <Space direction="vertical" size={4} style={{ display: 'flex' }}>
                  <span>
                    这些模板解析不出数字 OID，采集侧不会向设备发出任何请求 ⇒
                    <Text strong>永远采不到数据，且不会报错</Text>。
                  </span>
                  {Object.entries(oidAudit.missing_mibs ?? {}).map(([mib, keys]) => (
                    <span key={mib}>
                      缺少 MIB <Text code>{mib}</Text>，影响 {keys.length} 条：
                      {keys.slice(0, 6).join('、')}
                      {keys.length > 6 ? ` 等 ${keys.length} 条` : ''}
                    </span>
                  ))}
                  {(oidAudit.unresolved_items ?? [])
                    .filter((it) => !it.mib)
                    .map((it) => (
                      <span key={`${it.device_type}-${it.metric_key}`}>
                        <Text code>{it.metric_key}</Text>：{it.reason_label}
                      </span>
                    ))}
                  {uncompiledVendorMibs.length > 0 && (
                    <span>
                      厂商 MIB 目录里已有 {uncompiledVendorMibs.join('、')}
                      （源文件在、但没有 .py 编译产物 ⇒ 需先编译；pysnmp 不会自动编译文本 MIB）。
                    </span>
                  )}
                  <span>
                    处理办法：把厂商 MIB 文件放进 <Text code>{oidAudit.vendor_mib_dir}</Text>
                    （注意厂商再分发许可，请从设备官网自行获取），并编译成 pysnmp 能加载的 .py；
                    或直接给该模板填上数字 OID。
                  </span>
                </Space>
              ) : (
                <Space direction="vertical" size={4} style={{ display: 'flex' }}>
                  <span>本地 MIB 树与内置兜底表已覆盖全部模板；与采集侧用的是同一个解析器。</span>
                  {/* 判定依据分布：让"审计确实逐条看过了"可见，而不是一句空洞的"正常"。
                      没有这一行的话，审计对象为空（比如模板全被删光）也会显示绿色"正常"。
                      文案取自后端回传的 reason_labels，**不在前端自建映射**。 */}
                  {Object.keys(oidAudit.reason_counts ?? {}).length > 0 && (
                    <Space size={4} wrap>
                      {Object.entries(oidAudit.reason_counts ?? {}).map(([reason, count]) => (
                        <Tooltip
                          key={reason}
                          title={(oidAudit.reason_labels ?? {})[reason] ?? reason}
                        >
                          <Tag>
                            {reason}: {count}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  )}
                </Space>
              )
            }
          />
        )}
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            allowClear
            placeholder="搜索指标 / 显示名 / 分类 / OID / 说明"
            prefix={<SearchOutlined />}
            style={{ width: 280 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            allowClear
            placeholder="设备类型"
            style={{ width: 140 }}
            value={filterDeviceType}
            onChange={setFilterDeviceType}
            options={DEVICE_TYPE_OPTIONS}
          />
          <Select
            allowClear
            placeholder="来源"
            style={{ width: 120 }}
            value={filterSource}
            onChange={setFilterSource}
            options={SOURCE_OPTIONS}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            value={filterEnabled}
            onChange={setFilterEnabled}
            options={[
              { label: '已启用', value: 'enabled' },
              { label: '已停用', value: 'disabled' }
            ]}
          />
        </Space>
        <BatchActionBar count={batch.count} unit="个模板" onClear={batch.clear}>
          <Button
            size="small"
            icon={<CheckOutlined />}
            loading={batchToggleMut.isPending}
            onClick={() => handleBatchToggleEnabled(true)}
          >
            批量启用
          </Button>
          <Button
            size="small"
            icon={<StopOutlined />}
            loading={batchToggleMut.isPending}
            onClick={() => handleBatchToggleEnabled(false)}
          >
            批量停用
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            loading={batchDeleteMut.isPending}
            onClick={handleBatchDelete}
          >
            批量删除
          </Button>
        </BatchActionBar>
        <DataTable<MetricTemplateItem>
          columns={columns}
          dataSource={filteredItems}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
          rowSelection={batch.rowSelection}
          total={filteredItems.length}
          emptyText="暂无指标模板"
          searchable={false}
          showCard={false}
          tableProps={table}
        />
      </Card>

      <MetricTemplateModal
        open={modal.isOpen}
        editingRecord={editingRecord}
        form={form}
        onClose={closeModal}
      />
    </div>
  );
}
