/**
 * Zabbix 端口流量折线图（方案 B：数据自绘，零落库）
 *
 * 默认不获取流量数据。用户选端口 + 时间范围 + 点「获取流量图」才请求 API。
 * 用 @ant-design/charts Line（G2 5.x）渲染 rx/tx 折线（smooth，非点状）。
 * 流量数值自适应进位：bps → Kbps → Mbps → Gbps。
 */
import { useMemo, useState } from 'react';
import { Card, Empty, Segmented, Select, Button, Space } from 'antd';
import { Line } from '@ant-design/charts';
import { useTranslation } from 'react-i18next';
import { useDeviceTrafficPorts, useDeviceTraffic } from '@/services/monitor';
import { useMessage } from '@/hooks/useMessage';

type RangeKey = 'h1' | 'h6' | 'h24';

const RANGE_MAP: Record<RangeKey, number> = {
  h1: 3600,
  h6: 6 * 3600,
  h24: 24 * 3600
};

const RANGE_LABEL_KEY = {
  h1: 'traffic.range.h1',
  h6: 'traffic.range.h6',
  h24: 'traffic.range.h24'
} as const;

function pickUnit(max: number): { label: string; divisor: number } {
  const a = Math.abs(max);
  if (a >= 1e12) return { label: 'Tbps', divisor: 1e12 };
  if (a >= 1e9) return { label: 'Gbps', divisor: 1e9 };
  if (a >= 1e6) return { label: 'Mbps', divisor: 1e6 };
  if (a >= 1e3) return { label: 'Kbps', divisor: 1e3 };
  return { label: 'bps', divisor: 1 };
}

function fmt(n: number): string {
  if (!isFinite(n)) return '-';
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

export default function TrafficChart({ deviceId }: { deviceId: number }) {
  const { t } = useTranslation('monitor');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const [rangeKey, setRangeKey] = useState<RangeKey>('h1');
  const [selectedPort, setSelectedPort] = useState<string | undefined>(undefined);
  const [shouldFetch, setShouldFetch] = useState(false);

  const { data: portsData, isLoading: portsLoading } = useDeviceTrafficPorts(deviceId);
  const ports = portsData?.ports ?? [];

  const now = useMemo(() => Math.floor(Date.now() / 1000), [rangeKey, shouldFetch]);
  const windowSec = RANGE_MAP[rangeKey];

  const { data, isLoading, isFetching } = useDeviceTraffic(
    deviceId,
    selectedPort,
    now - windowSec,
    now,
    shouldFetch
  );

  const { series, unit } = useMemo(() => {
    if (!data || !data.time?.length) return { series: [], unit: { label: 'bps', divisor: 1 } };
    const rx = data.rx_bps ?? [];
    const tx = data.tx_bps ?? [];
    const allVals = [...rx, ...tx].filter((v): v is number => v != null && isFinite(v));
    const max = allVals.length ? Math.max(...allVals.map(Math.abs)) : 0;
    const u = pickUnit(max);
    const rows: { time: string; value: number | null; direction: string }[] = [];
    data.time.forEach((ts, i) => {
      const timeLabel = new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
      const rv = rx[i];
      const tv = tx[i];
      rows.push({
        time: timeLabel,
        value: rv != null && isFinite(rv) ? rv / u.divisor : null,
        direction: t('traffic.direction.rx')
      });
      rows.push({
        time: timeLabel,
        value: tv != null && isFinite(tv) ? tv / u.divisor : null,
        direction: t('traffic.direction.tx')
      });
    });
    return { series: rows, unit: u };
  }, [data, t]);

  const handleFetch = () => {
    if (!selectedPort) {
      message.warning(t('traffic.selectPortFirst'));
      return;
    }
    setShouldFetch(true);
  };

  if (portsLoading) {
    return (
      <Card title={t('traffic.title')}>
        <div style={{ textAlign: 'center', padding: 48 }}>{tCommon('message.loading')}</div>
      </Card>
    );
  }

  if (portsData && !portsData.configured) {
    const errorMsg =
      portsData.error === 'credential_error'
        ? t('traffic.error.credential')
        : portsData.error === 'fetch_error'
          ? t('traffic.error.fetch')
          : t('traffic.error.noCredential');
    return (
      <Card title={t('traffic.title')}>
        <Empty description={errorMsg} />
      </Card>
    );
  }

  return (
    <Card
      title={t('traffic.title')}
      extra={
        <Segmented
          options={(Object.keys(RANGE_MAP) as RangeKey[]).map((k) => ({
            label: t(RANGE_LABEL_KEY[k]),
            value: k
          }))}
          value={rangeKey}
          onChange={(v) => {
            setRangeKey(v as RangeKey);
            setShouldFetch(false);
          }}
        />
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 端口选择 + 获取按钮 */}
        <Space wrap>
          <Select
            style={{ width: 320 }}
            placeholder={t('traffic.selectPortPlaceholder')}
            value={selectedPort}
            onChange={(v) => {
              setSelectedPort(v);
              setShouldFetch(false);
            }}
            options={ports.map((p) => ({ label: p.port, value: p.port }))}
            loading={portsLoading}
            showSearch
            optionFilterProp="label"
          />
          <Button type="primary" onClick={handleFetch} loading={isFetching}>
            {t('traffic.fetch')}
          </Button>
        </Space>

        {/* 图表 */}
        {isLoading || isFetching ? (
          <div style={{ textAlign: 'center', padding: 48 }}>{tCommon('message.loading')}</div>
        ) : !shouldFetch || !series.length ? (
          <Empty
            description={
              shouldFetch
                ? t('traffic.noData')
                : t('traffic.emptyHint', { action: t('traffic.fetch') })
            }
          />
        ) : (
          <Line
            data={series}
            xField="time"
            yField="value"
            colorField="direction"
            shape="smooth"
            height={320}
            axis={{
              y: { title: `${unit.label}` },
              x: { labelAutoRotate: true }
            }}
            scale={{ y: { nice: true } }}
            tooltip={{
              title: 'time',
              items: [
                { field: 'direction', name: t('traffic.tooltip.direction') },
                {
                  field: 'value',
                  name: t('traffic.tooltip.value', { unit: unit.label }),
                  valueFormatter: (v: number) => fmt(v)
                }
              ]
            }}
            legend={{ color: { position: 'top' } }}
          />
        )}
      </Space>
    </Card>
  );
}
