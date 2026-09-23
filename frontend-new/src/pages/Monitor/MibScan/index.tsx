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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const { Text, Paragraph } = Typography;

type MibDeviceTypeKey = 'oid.deviceType.network' | 'oid.deviceType.server' | 'oid.deviceType.other';
type MibMetricTypeKey =
  | 'mib.metricTypeOption.gauge'
  | 'mib.metricTypeOption.counter'
  | 'mib.metricTypeOption.state'
  | 'mib.metricTypeOption.event';

const getDeviceTypeOptions = (t: TFunction<'monitor'>) =>
  (
    [
      { key: 'oid.deviceType.network', value: 'network' },
      { key: 'oid.deviceType.server', value: 'server' },
      { key: 'oid.deviceType.other', value: 'other' }
    ] as { key: MibDeviceTypeKey; value: string }[]
  ).map(({ key, value }) => ({ label: t(key), value }));

const getMetricTypeOptions = (t: TFunction<'monitor'>) =>
  (
    [
      { key: 'mib.metricTypeOption.gauge', value: 'gauge' },
      { key: 'mib.metricTypeOption.counter', value: 'counter' },
      { key: 'mib.metricTypeOption.state', value: 'state' },
      { key: 'mib.metricTypeOption.event', value: 'event' }
    ] as { key: MibMetricTypeKey; value: string }[]
  ).map(({ key, value }) => ({ label: t(key), value }));

export default function MibScanPage() {
  const { t } = useTranslation('monitor');
  const { t: tc } = useTranslation('common');
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
      message.info(t('mib.message.noRecommend'));
      return;
    }
    setSelectedOids(hits);
    setRecommendSort(true);
    message.success(t('mib.message.recommendSelected', { count: hits.length }));
  };

  const handlePersistRule = async (r: MibScanOid) => {
    if (!r.category) return;
    try {
      await persistRuleMut.mutateAsync({
        oid: r.oid,
        device_type: deviceType,
        vendor_id: scanResult?.vendor_id ?? null
      });
      message.success(t('mib.message.ruleSaved', { name: r.category_label ?? r.category }));
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('mib.message.saveRuleFailed'));
    }
  };

  const handleScan = async () => {
    if (!deviceId) {
      message.warning(t('mib.message.selectDeviceFirst'));
      return;
    }
    setSelectedOids([]);
    setMetricKeys({});
    const t0 = Date.now();
    const elapsedHint = message.loading(t('mib.message.scanning'), 0);
    try {
      await scanMut.mutateAsync({ device_id: deviceId, timeout: 15 });
      elapsedHint();
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      message.success(t('mib.message.scanDone', { seconds: elapsed }));
    } catch (err: unknown) {
      elapsedHint();
      message.error(err instanceof Error ? err.message : t('mib.message.scanFailed'));
    }
  };

  const suggestMetricKey = (oid: string): string => {
    const parts = oid.split('.');
    return `oid_${parts.slice(-2).join('_')}`;
  };

  const handleImport = async () => {
    if (selectedOids.length === 0) {
      message.warning(t('mib.message.selectOidFirst'));
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
        autoFilled.length > 0 ? t('mib.message.autoFilledNote', { count: autoFilled.length }) : '';
      message.success(t('mib.message.imported', { count: res.count }) + autoNote);
      setSelectedOids([]);
      setMetricKeys({});
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : t('mib.message.importFailed'));
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
      title: t('mib.column.category'),
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
                {t('mib.action.saveAsRule')}
              </Button>
            )}
          </Space>
        );
      }
    },
    {
      title: tc('field.type'),
      dataIndex: 'type',
      key: 'type',
      width: 160,
      render: (v: string) => <Tag color="blue">{v}</Tag>
    },
    {
      title: t('mib.column.sampleValue'),
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
      <Card title={t('mib.title')} variant="borderless">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('mib.alert.message')}
          description={t('mib.alert.description')}
        />
        <Space wrap size="middle">
          <Input
            placeholder={t('mib.placeholder.searchDevice')}
            prefix={<SearchOutlined />}
            style={{ width: 200 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
          <Select
            style={{ width: 280 }}
            placeholder={t('mib.placeholder.selectDevice')}
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
            options={getDeviceTypeOptions(t)}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={handleScan}
            loading={scanMut.isPending}
            disabled={!deviceId}
          >
            {t('mib.action.scan')}
          </Button>
        </Space>
      </Card>

      {scanResult && (
        <>
          <Card variant="borderless">
            <Row gutter={16}>
              <Col xs={12} md={6}>
                <Statistic title={t('mib.stat.deviceIp')} value={scanResult.device_ip} />
              </Col>
              <Col xs={12} md={6}>
                <Statistic title={t('mib.stat.oidCount')} value={scanResult.oid_count} />
              </Col>
              <Col xs={24} md={12}>
                <Statistic
                  title={t('mib.stat.typeDistribution')}
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
                <Text strong>{t('mib.oidListTitle')}</Text>
                <Tag color="processing">
                  {t('mib.count.selected', { count: selectedOids.length })}
                </Tag>
                <Tag>
                  {filteredDetected.length}/{rawDetected.length}
                </Tag>
                {recommendCatSet.size > 0 && (
                  <Tag color="gold" icon={<StarOutlined />}>
                    {t('mib.count.recommendCategory', { count: recommendCatSet.size })}
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
                  {t('mib.action.recommend')}
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    setSelectedOids([]);
                    setMetricKeys({});
                    setRecommendSort(false);
                  }}
                >
                  {t('mib.action.clear')}
                </Button>
                <Button
                  type="primary"
                  icon={<ImportOutlined />}
                  onClick={handleImport}
                  loading={importMut.isPending}
                  disabled={selectedOids.length === 0}
                >
                  {t('mib.action.import', { count: selectedOids.length })}
                </Button>
              </Space>
            }
          >
            <Space wrap style={{ marginBottom: 12 }}>
              <Input
                allowClear
                placeholder={t('mib.placeholder.filterOid')}
                prefix={<SearchOutlined />}
                style={{ width: 240 }}
                value={oidKeyword}
                onChange={(e) => setOidKeyword(e.target.value)}
              />
              <Select
                allowClear
                placeholder={t('mib.placeholder.filterType')}
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
              emptyText={t('mib.empty')}
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
            {t('mib.emptyHint', { action: t('mib.action.scan') })}
          </Paragraph>
        </Card>
      )}
    </div>
  );
}
