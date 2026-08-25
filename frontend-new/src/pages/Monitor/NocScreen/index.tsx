/**
 * P2-12: NOC 大屏（Network Operations Center）— 全部重写
 *
 * 设计系统：Real-Time Monitoring（UI-UX-Pro-Max）
 * - 配色：深蓝黑背景 + 科技蓝/琥珀/玫红/翠绿（低饱和高对比）
 * - 字体：Fira Code（数字）+ Fira Sans（文字）
 * - 布局：顶部状态栏 → 4 KPI → 告警墙(2/3)+双饼图(1/3) → 密度时序
 *
 * 全屏：跳转独立路由 /monitor/noc-screen/fullscreen（脱离 AppLayout，真全屏无 chrome）
 *
 * 饼图修复（@ant-design/charts v2.6.7 / G2 5.x）：
 * - label 用 formatter 函数显示 "name: percentage"
 * - legend 用 itemFormatter 显示 name
 * - color 用 colorField + 显式 color 数组
 */
import { useEffect, useMemo, useState } from 'react';
import { Tag, Empty, Segmented, Tooltip, Button, Space } from 'antd';
import { Pie, Column } from '@ant-design/charts';
import {
  ReloadOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  ArrowLeftOutlined
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { ensureUtc } from '@/utils/format';
import { useMonitorAlerts, useAlertStatistics } from '@/services/monitor';

const T = {
  bg: '#f5f7fa',
  cardBg: '#ffffff',
  cardBgHover: '#fafbfc',
  border: '#e5e7eb',
  textPrimary: '#1f2937',
  textSecondary: '#4b5563',
  textTertiary: '#9ca3af',
  accent: '#1677ff',
  accentDeep: '#0958d9'
};

const SEV_COLOR: Record<string, string> = {
  info: '#52c41a',
  warning: '#faad14',
  critical: '#ff4d4f'
};
const SEV_ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2 };
const SEV_LABEL: Record<string, string> = { critical: '严重', warning: '警告', info: '提示' };

const REFRESH_OPTIONS = [
  { label: '关闭', value: 0 },
  { label: '10s', value: 10 },
  { label: '15s', value: 15 },
  { label: '30s', value: 30 },
  { label: '60s', value: 60 }
];

const FONT_NUM = "'Fira Code', 'Courier New', monospace";
const FONT_TXT = "'Fira Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

export default function MonitorNocScreenPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const isFullscreenRoute = location.pathname === '/monitor/noc-screen/fullscreen';

  const [refreshSec, setRefreshSec] = useState(15);
  const [now, setNow] = useState(() => dayjs());

  useEffect(() => {
    const t = setInterval(() => setNow(dayjs()), 1000);
    return () => clearInterval(t);
  }, []);

  const alertsQuery = useMonitorAlerts({ status: 'pending', page: 1, per_page: 50 });
  const statsQuery = useAlertStatistics({ bucket: 'hour', top_n: 10 });

  useEffect(() => {
    if (refreshSec <= 0) return;
    const t = setInterval(() => {
      alertsQuery.refetch();
      statsQuery.refetch();
    }, refreshSec * 1000);
    return () => clearInterval(t);
  }, [refreshSec, alertsQuery, statsQuery]);

  const alerts = alertsQuery.data?.items ?? [];
  const stats = statsQuery.data;

  const sortedAlerts = useMemo(
    () =>
      [...alerts].sort((a, b) => {
        const sa = SEV_ORDER[a.severity ?? 'info'] ?? 99;
        const sb = SEV_ORDER[b.severity ?? 'info'] ?? 99;
        if (sa !== sb) return sa - sb;
        return (b.id ?? 0) - (a.id ?? 0);
      }),
    [alerts]
  );

  const criticalCount = sortedAlerts.filter((a) => a.severity === 'critical').length;
  const warningCount = sortedAlerts.filter((a) => a.severity === 'warning').length;
  const infoCount = sortedAlerts.filter((a) => a.severity === 'info').length;

  const severityPieData = useMemo(
    () =>
      (stats?.by_severity ?? []).map((x) => ({
        name: SEV_LABEL[x.severity ?? ''] ?? x.severity ?? '未知',
        value: x.count ?? 0
      })),
    [stats]
  );
  const typePieData = useMemo(
    () =>
      (stats?.by_type ?? []).map((x) => ({ name: x.alert_type ?? '未知', value: x.count ?? 0 })),
    [stats]
  );
  const densityData = useMemo(
    () =>
      (stats?.density ?? []).map((x) => ({
        time: x.bucket_start ? dayjs(ensureUtc(x.bucket_start)).format('MM-DD HH:mm') : '',
        count: x.count ?? 0
      })),
    [stats]
  );

  const toggleFullscreen = () => {
    if (isFullscreenRoute) {
      navigate('/monitor/alerts?tab=noc');
    } else {
      navigate('/monitor/noc-screen/fullscreen');
    }
  };

  const buildPieConfig = (
    data: { name: string; value: number }[],
    colorMap: Record<string, string>
  ) => ({
    data: data.length === 0 ? [{ name: '暂无', value: 1 }] : data,
    angleField: 'value',
    colorField: 'name',
    color: data.length === 0 ? [T.border] : data.map((d) => colorMap[d.name] ?? T.accent),
    radius: 0.85,
    innerRadius: 0.6,
    label: {
      text: (datum: { name?: string; value?: number }) => {
        const total = data.reduce((s, d) => s + d.value, 0) || 1;
        const pct = ((datum.value ?? 0) / total) * 100;
        return `${datum.name ?? ''} ${pct.toFixed(0)}%`;
      },
      position: 'outside' as const,
      style: { fontSize: 11, fill: T.textSecondary }
    },
    legend: {
      position: 'bottom' as const,
      layout: 'horizontal' as const,
      itemMarker: 'circle' as const,
      itemLabelFormatter: (name: string) => name,
      style: { fill: T.textSecondary, fontSize: 11 }
    },
    interactions: [{ type: 'element-active' }],
    animation: { appear: { duration: 400 } }
  });

  const severityConfig = buildPieConfig(severityPieData, SEV_COLOR);

  const typeColorMap = useMemo(() => {
    const palette = [T.accent, '#f59e0b', '#10b981', '#dc2626', '#a855f7', '#06b6d4'];
    const map: Record<string, string> = {};
    typePieData.forEach((d, i) => {
      map[d.name] = palette[i % palette.length];
    });
    return map;
  }, [typePieData]);
  const typeConfig = buildPieConfig(typePieData, typeColorMap);

  const densityConfig = {
    data: densityData,
    xField: 'time',
    yField: 'count',
    height: 160,
    color: T.accent,
    axis: {
      x: { labelAutoRotate: true, label: { style: { fill: T.textSecondary, fontSize: 10 } } },
      y: { title: '告警数', label: { style: { fill: T.textSecondary, fontSize: 10 } } }
    },
    animation: { appear: { duration: 400 } }
  };

  const cardBase: React.CSSProperties = {
    background: T.cardBg,
    borderRadius: 8,
    border: `1px solid ${T.border}`,
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
  };

  return (
    <div
      style={{
        background: T.bg,
        minHeight: '100vh',
        color: T.textPrimary,
        padding: 16,
        fontFamily: FONT_TXT
      }}
    >
      {/* ===== 顶部状态栏 ===== */}
      <div
        style={{
          ...cardBase,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          padding: '12px 20px'
        }}
      >
        <Space size="large" align="center">
          {isFullscreenRoute && (
            <Tooltip title="返回告警中心">
              <Button
                size="small"
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate('/monitor/alerts?tab=noc')}
                style={{ color: T.textSecondary }}
              />
            </Tooltip>
          )}
          <span style={{ fontSize: 22, fontWeight: 700, color: T.accent, letterSpacing: 1 }}>
            NOC 监控大屏
          </span>
          <span style={{ fontSize: 13, color: T.textTertiary }}>
            活跃告警{' '}
            <span style={{ color: T.textPrimary, fontWeight: 600, fontFamily: FONT_NUM }}>
              {sortedAlerts.length}
            </span>{' '}
            条
          </span>
        </Space>
        <Space size="middle" align="center">
          <span
            style={{
              fontSize: 15,
              color: T.textSecondary,
              fontFamily: FONT_NUM,
              letterSpacing: 1
            }}
          >
            {now.format('YYYY-MM-DD HH:mm:ss')}
          </span>
          <Segmented
            size="small"
            options={REFRESH_OPTIONS}
            value={refreshSec}
            onChange={(v) => setRefreshSec(v as number)}
          />
          <Tooltip title={isFullscreenRoute ? '退出全屏' : '全屏'}>
            <Button
              size="small"
              type="text"
              icon={isFullscreenRoute ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
              style={{ color: T.textSecondary }}
            />
          </Tooltip>
          <Tooltip title="刷新">
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={() => {
                alertsQuery.refetch();
                statsQuery.refetch();
              }}
              style={{ color: T.textSecondary }}
            />
          </Tooltip>
        </Space>
      </div>

      {/* ===== 4 KPI 卡片 ===== */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
          marginBottom: 16
        }}
      >
        {[
          { title: '活跃告警总数', value: sortedAlerts.length, color: T.accent },
          { title: '严重告警', value: criticalCount, color: SEV_COLOR.critical },
          { title: '警告告警', value: warningCount, color: SEV_COLOR.warning },
          { title: '提示告警', value: infoCount, color: SEV_COLOR.info }
        ].map((m) => (
          <div
            key={m.title}
            style={{
              ...cardBase,
              padding: '16px 20px',
              borderLeft: `3px solid ${m.color}`
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: T.textTertiary,
                marginBottom: 6,
                letterSpacing: 0.5
              }}
            >
              {m.title}
            </div>
            <div
              style={{
                fontSize: 36,
                fontWeight: 700,
                color: m.color,
                fontFamily: FONT_NUM,
                lineHeight: 1.1
              }}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* ===== 中部：告警墙 + 双饼图 ===== */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* 告警墙 */}
        <div
          style={{
            ...cardBase,
            padding: 16,
            maxHeight: isFullscreenRoute ? 'calc(100vh - 380px)' : '480px',
            overflow: 'hidden'
          }}
        >
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              marginBottom: 12,
              color: T.textSecondary,
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 3,
                height: 14,
                background: T.accent,
                borderRadius: 2
              }}
            />
            活跃告警墙（按级别排序，critical 置顶）
          </div>
          {sortedAlerts.length === 0 ? (
            <Empty
              description={<span style={{ color: T.textTertiary }}>暂无活跃告警</span>}
              style={{ padding: '60px 0' }}
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sortedAlerts.slice(0, 20).map((a) => {
                const sev = a.severity ?? 'info';
                const sevColor = SEV_COLOR[sev] ?? T.textTertiary;
                const isCritical = sev === 'critical';
                let alertTitle = a.alert_type ?? '-';
                try {
                  if (a.payload_json) {
                    const p = JSON.parse(a.payload_json);
                    if (p?.title) alertTitle = p.title;
                  }
                } catch {
                  /* ignore */
                }
                return (
                  <div
                    key={a.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '90px 70px 1fr 130px',
                      gap: 10,
                      padding: '8px 12px',
                      background: isCritical ? '#fff1f0' : T.cardBgHover,
                      borderRadius: 6,
                      borderLeft: `3px solid ${sevColor}`,
                      animation: isCritical ? 'noc-blink 1.5s infinite' : undefined,
                      alignItems: 'center'
                    }}
                  >
                    <Tag
                      color={sevColor}
                      style={{ margin: 0, width: 'fit-content', fontSize: 11, fontWeight: 600 }}
                    >
                      {SEV_LABEL[sev] ?? sev}
                    </Tag>
                    <span style={{ fontSize: 11, color: T.textTertiary, fontFamily: FONT_NUM }}>
                      #{a.id}
                    </span>
                    <Tooltip title={alertTitle}>
                      <span
                        style={{
                          fontSize: 13,
                          color: T.textPrimary,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                      >
                        {alertTitle}
                      </span>
                    </Tooltip>
                    <span
                      style={{
                        fontSize: 11,
                        color: T.textTertiary,
                        textAlign: 'right',
                        fontFamily: FONT_NUM
                      }}
                    >
                      {a.created_at ? dayjs(ensureUtc(a.created_at)).format('MM-DD HH:mm:ss') : '-'}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 双饼图 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ ...cardBase, padding: 12 }}>
            <div style={{ fontSize: 12, color: T.textTertiary, marginBottom: 8 }}>按级别分布</div>
            <Pie {...severityConfig} height={200} />
          </div>
          <div style={{ ...cardBase, padding: 12 }}>
            <div style={{ fontSize: 12, color: T.textTertiary, marginBottom: 8 }}>按类型分布</div>
            <Pie {...typeConfig} height={200} />
          </div>
        </div>
      </div>

      {/* ===== 底部：告警密度时序 ===== */}
      <div style={{ ...cardBase, padding: 16 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            marginBottom: 12,
            color: T.textSecondary,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: 3,
              height: 14,
              background: T.accent,
              borderRadius: 2
            }}
          />
          告警密度时序（按小时）
        </div>
        {densityData.length === 0 ? (
          <Empty
            description={<span style={{ color: T.textTertiary }}>暂无数据</span>}
            style={{ padding: '40px 0' }}
          />
        ) : (
          <Column {...densityConfig} />
        )}
      </div>

      <style>{`
        @keyframes noc-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.55; }
        }
      `}</style>
    </div>
  );
}
