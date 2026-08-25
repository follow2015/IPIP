/**
 * Zabbix 端口流量折线图（方案 B：数据自绘，零落库）
 *
 * 默认不获取流量数据。用户选端口 + 时间范围 + 点「获取流量图」才请求 API。
 * 用 @ant-design/charts Line（G2 5.x）渲染 rx/tx 折线（smooth，非点状）。
 * 流量数值自适应进位：bps → Kbps → Mbps → Gbps。
 */
import { useMemo, useState } from 'react';
import { Card, Empty, Segmented, Select, Button, Space, message } from 'antd';
import { Line } from '@ant-design/charts';
import { useDeviceTrafficPorts, useDeviceTraffic } from '@/services/monitor';

const RANGE_MAP: Record<string, number> = {
  '1小时': 3600,
  '6小时': 6 * 3600,
  '24小时': 24 * 3600
};

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
  const [rangeKey, setRangeKey] = useState('1小时');
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
      const t = new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
      const rv = rx[i];
      const tv = tx[i];
      rows.push({
        time: t,
        value: rv != null && isFinite(rv) ? rv / u.divisor : null,
        direction: '接收'
      });
      rows.push({
        time: t,
        value: tv != null && isFinite(tv) ? tv / u.divisor : null,
        direction: '发送'
      });
    });
    return { series: rows, unit: u };
  }, [data]);

  const handleFetch = () => {
    if (!selectedPort) {
      message.warning('请先选择端口');
      return;
    }
    setShouldFetch(true);
  };

  if (portsLoading) {
    return (
      <Card title="端口流量">
        <div style={{ textAlign: 'center', padding: 48 }}>加载中...</div>
      </Card>
    );
  }

  if (portsData && !portsData.configured) {
    const errorMsg =
      portsData.error === 'credential_error'
        ? 'Zabbix 凭据解密失败，请检查凭据配置'
        : portsData.error === 'fetch_error'
          ? 'Zabbix 端口列表拉取失败，请检查网络或 Zabbix 服务'
          : '该设备未配置 Zabbix 凭据，无法拉取端口流量';
    return (
      <Card title="端口流量">
        <Empty description={errorMsg} />
      </Card>
    );
  }

  return (
    <Card
      title="端口流量"
      extra={
        <Segmented
          options={Object.keys(RANGE_MAP)}
          value={rangeKey}
          onChange={(v) => {
            setRangeKey(v as string);
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
            placeholder="选择端口"
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
            获取流量图
          </Button>
        </Space>

        {/* 图表 */}
        {isLoading || isFetching ? (
          <div style={{ textAlign: 'center', padding: 48 }}>加载中...</div>
        ) : !shouldFetch || !series.length ? (
          <Empty
            description={
              shouldFetch ? 'Zabbix 暂无该端口流量数据' : '请选择端口并点击「获取流量图」'
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
                { field: 'direction', name: '方向' },
                {
                  field: 'value',
                  name: `流量 (${unit.label})`,
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
