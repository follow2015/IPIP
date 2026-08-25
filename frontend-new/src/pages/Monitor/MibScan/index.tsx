/**
 * MIB 自动探测页：对设备做 MIB walk，自动发现 OID 清单，
 * 运维勾选感兴趣的 OID + 填 metric_key 即可一键导入指标模板，无需手敲 OID。
 *
 * 流程：选设备 → 触发探测 → 表格展示 OID（OID/类型/采样值）→ 勾选 + 填 metric_key → 导入
 */
import { useState } from 'react';
import {
  Card,
  Button,
  Space,
  Select,
  Input,
  Tag,
  Typography,
  Alert,
  Statistic,
  Row,
  Col,
  Tooltip
} from 'antd';
import { SearchOutlined, ImportOutlined, ReloadOutlined, StarOutlined } from '@ant-design/icons';
import { useDeviceList } from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import { useTable } from '@/hooks/useTable';
import DataTable from '@/components/DataTable';
import {
  useMibScan,
  useImportOids,
  useRecommendConfig,
  usePersistHeuristicRule,
  type MibScanOid,
  type MibImportItem
} from '@/services/monitor';

const { Text, Paragraph } = Typography;

const DEVICE_TYPE_OPTIONS = [
  { label: 'network（网络设备）', value: 'network' },
  { label: 'server（服务器）', value: 'server' },
  { label: 'other（其他）', value: 'other' }
];

const METRIC_TYPE_OPTIONS = [
  { label: 'gauge（瞬时值）', value: 'gauge' },
  { label: 'counter（累加计数）', value: 'counter' },
  { label: 'state（状态）', value: 'state' },
  { label: 'event（事件）', value: 'event' }
];

export default function MibScanPage() {
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [deviceType, setDeviceType] = useState<string>('network');
  const [selectedOids, setSelectedOids] = useState<MibScanOid[]>([]);
  const [metricKeys, setMetricKeys] = useState<Record<string, string>>({});
  const [search, setSearch] = useState('');
  const [oidKeyword, setOidKeyword] = useState('');
  const [oidTypeFilter, setOidTypeFilter] = useState<string | undefined>(undefined);

  const deviceList = useDeviceList({ page: 1, per_page: 50, search: search || undefined });
  const scanMut = useMibScan();
  const importMut = useImportOids();
  const persistRuleMut = usePersistHeuristicRule();
  const message = useMessage();
  const { data: recommendCategories } = useRecommendConfig(deviceType);

  const devices = deviceList.data?.items ?? [];
  const scanResult = scanMut.data;

  const rawDetected = scanResult?.detected ?? [];
  const kw = oidKeyword.trim().toLowerCase();
  const filteredDetected = rawDetected.filter((r) => {
    if (oidTypeFilter && r.type !== oidTypeFilter) return false;
    if (!kw) return true;
    return r.oid.toLowerCase().includes(kw) || (r.value ?? '').toLowerCase().includes(kw);
  });

  const recommendCatSet = new Set(recommendCategories ?? []);

  const isRecommended = (r: MibScanOid): boolean => {
    return !!r.category && recommendCatSet.has(r.category);
  };

  const [recommendSort, setRecommendSort] = useState(false);
  const table = useTable({ initialPerPage: 50 });

  const displayDetected = recommendSort
    ? [...filteredDetected].sort((a, b) => {
        const aHit = isRecommended(a) ? 0 : 1;
        const bHit = isRecommended(b) ? 0 : 1;
        return aHit - bHit;
      })
    : filteredDetected;

  const handleRecommend = () => {
    const hits = rawDetected.filter((r) => isRecommended(r));
    if (hits.length === 0) {
      message.info('当前探测结果无匹配的推荐指标');
      return;
    }
    setSelectedOids(hits);
    setRecommendSort(true);
    message.success(`已勾选 ${hits.length} 个推荐指标并置顶`);
  };

  const handlePersistRule = async (r: MibScanOid) => {
    if (!r.category) return;
    try {
      await persistRuleMut.mutateAsync({
        oid: r.oid,
        device_type: deviceType,
        vendor_id: scanResult?.vendor_id ?? null
      });
      message.success(`已将「${r.category_label ?? r.category}」保存为该设备的分类规则`);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存规则失败');
    }
  };

  const handleScan = async () => {
    if (!deviceId) {
      message.warning('请先选择设备');
      return;
    }
    setSelectedOids([]);
    setMetricKeys({});
    const t0 = Date.now();
    const elapsedHint = message.loading('探测中，MIB walk 预计 10-40s，请稍候...', 0);
    try {
      await scanMut.mutateAsync({ device_id: deviceId, timeout: 15 });
      elapsedHint();
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      message.success(`探测完成，耗时 ${elapsed}s`);
    } catch (err: unknown) {
      elapsedHint();
      message.error(err instanceof Error ? err.message : '探测失败');
    }
  };

  const suggestMetricKey = (oid: string): string => {
    const parts = oid.split('.');
    return `oid_${parts.slice(-2).join('_')}`;
  };

  const handleImport = async () => {
    if (selectedOids.length === 0) {
      message.warning('请先勾选要导入的 OID');
      return;
    }
    const selectedDevice = devices.find((d) => d.id === deviceId);
    const vendor = selectedDevice?.brand ?? undefined;
    const items: MibImportItem[] = [];
    const autoFilled: string[] = [];
    for (const oid of selectedOids) {
      const key = metricKeys[oid.oid]?.trim() || suggestMetricKey(oid.oid);
      if (!metricKeys[oid.oid]?.trim()) {
        autoFilled.push(oid.oid);
      }
      items.push({
        oid: oid.oid,
        metric_key: key,
        device_type: deviceType,
        category: oid.category ?? undefined,
        display_name: oid.category_label ?? undefined,
        vendor,
        metric_type: 'gauge'
      });
    }
    try {
      const res = await importMut.mutateAsync(items);
      const autoNote =
        autoFilled.length > 0 ? `（其中 ${autoFilled.length} 个自动推断 metric_key）` : '';
      message.success(`已导入 ${res.count} 个指标模板${autoNote}`);
      setSelectedOids([]);
      setMetricKeys({});
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '导入失败');
    }
  };

  const columns = [
    {
      title: 'OID',
      dataIndex: 'oid',
      key: 'oid',
      width: 320,
      render: (v: string) => (
        <Text code style={{ fontSize: 12 }}>
          {v}
        </Text>
      )
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 180,
      render: (_: unknown, r: MibScanOid) => {
        if (!r.category) return <Text type="secondary">-</Text>;
        return (
          <Space size={4} wrap>
            <Tag color={isRecommended(r) ? 'gold' : 'default'}>
              {r.category_label ?? r.category}
            </Tag>
            {r.category_source === 'heuristic' && (
              <Button
                type="link"
                size="small"
                loading={persistRuleMut.isPending}
                onClick={() => handlePersistRule(r)}
                style={{ padding: 0, fontSize: 12 }}
              >
                存为规则
              </Button>
            )}
          </Space>
        );
      }
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 160,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: '采样值',
      dataIndex: 'value',
      key: 'value',
      ellipsis: true,
      render: (v: string) => <Text type="secondary">{v}</Text>
    },
    {
      title: 'metric_key',
      key: 'metric_key',
      width: 200,
      render: (_: unknown, r: MibScanOid) => (
        <Input
          placeholder={suggestMetricKey(r.oid)}
          value={metricKeys[r.oid] ?? ''}
          onChange={(e) => setMetricKeys((prev) => ({ ...prev, [r.oid]: e.target.value }))}
          size="small"
        />
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="MIB 自动探测" variant="borderless">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="对设备做 MIB walk，自动发现可采集的 OID 清单"
          description="勾选感兴趣的 OID + 填写 metric_key，一键导入指标模板。无需手敲 OID，无需 MIB 文件。"
        />
        <Space wrap size="middle">
          <Input
            placeholder="搜索设备名称/IP"
            prefix={<SearchOutlined />}
            style={{ width: 200 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
          <Select
            style={{ width: 280 }}
            placeholder="选择设备"
            value={deviceId}
            onChange={(v) => setDeviceId(v)}
            showSearch
            optionFilterProp="label"
            options={devices.map((d) => ({
              label: `${d.device_name}（${d.management_ip || d.ipmi_address || '-'}）`,
              value: d.id
            }))}
          />
          <Select
            style={{ width: 180 }}
            value={deviceType}
            onChange={setDeviceType}
            options={DEVICE_TYPE_OPTIONS}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={handleScan}
            loading={scanMut.isPending}
            disabled={!deviceId}
          >
            开始探测
          </Button>
        </Space>
      </Card>

      {scanResult && (
        <>
          <Card variant="borderless">
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="设备 IP" value={scanResult.device_ip} />
              </Col>
              <Col span={6}>
                <Statistic title="发现 OID 数" value={scanResult.oid_count} />
              </Col>
              <Col span={12}>
                <Statistic
                  title="类型分布"
                  valueRender={() => (
                    <Space size={4} wrap>
                      {Object.entries(scanResult.type_summary).map(([t, c]) => (
                        <Tag key={t}>
                          {t}: {c}
                        </Tag>
                      ))}
                    </Space>
                  )}
                />
              </Col>
            </Row>
          </Card>

          <Card
            title={
              <Space>
                <Text strong>OID 清单</Text>
                <Tag color="processing">{selectedOids.length} 已选</Tag>
                <Tag>
                  {filteredDetected.length}/{rawDetected.length}
                </Tag>
                {recommendCatSet.size > 0 && (
                  <Tag color="gold" icon={<StarOutlined />}>
                    {recommendCatSet.size} 推荐类别
                  </Tag>
                )}
              </Space>
            }
            extra={
              <Space>
                <Button
                  icon={<StarOutlined />}
                  onClick={handleRecommend}
                  disabled={rawDetected.length === 0 || recommendCatSet.size === 0}
                >
                  推荐勾选
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    setSelectedOids([]);
                    setMetricKeys({});
                    setRecommendSort(false);
                  }}
                >
                  清空选择
                </Button>
                <Button
                  type="primary"
                  icon={<ImportOutlined />}
                  onClick={handleImport}
                  loading={importMut.isPending}
                  disabled={selectedOids.length === 0}
                >
                  导入 {selectedOids.length} 个指标模板
                </Button>
              </Space>
            }
          >
            <Space wrap style={{ marginBottom: 12 }}>
              <Input
                allowClear
                placeholder="筛选 OID / 采样值"
                prefix={<SearchOutlined />}
                style={{ width: 240 }}
                value={oidKeyword}
                onChange={(e) => setOidKeyword(e.target.value)}
              />
              <Select
                allowClear
                placeholder="类型筛选"
                style={{ width: 160 }}
                value={oidTypeFilter}
                onChange={setOidTypeFilter}
                options={Object.keys(scanResult?.type_summary ?? {}).map((t) => ({
                  label: `${t} (${scanResult!.type_summary[t]})`,
                  value: t
                }))}
              />
            </Space>
            <DataTable<MibScanOid>
              columns={columns}
              dataSource={displayDetected}
              loading={scanMut.isPending}
              rowKey={(r) => r.oid}
              total={displayDetected.length}
              emptyText="未发现 OID"
              searchable={false}
              showCard={false}
              tableProps={table}
              rowSelection={{
                preserveSelectedRowKeys: true,
                selectedRowKeys: selectedOids.map((o) => o.oid),
                onChange: (keys) => {
                  const oidMap = new Map(rawDetected.map((r) => [r.oid, r]));
                  setSelectedOids(
                    (keys as string[]).map((k) => oidMap.get(k)).filter((r): r is MibScanOid => !!r)
                  );
                }
              }}
            />
          </Card>
        </>
      )}

      {!scanResult && !scanMut.isPending && (
        <Card variant="borderless">
          <Paragraph type="secondary" style={{ textAlign: 'center', padding: 48 }}>
            选择设备后点击「开始探测」，将自动发现设备支持的 OID 清单
          </Paragraph>
        </Card>
      )}
    </div>
  );
}
