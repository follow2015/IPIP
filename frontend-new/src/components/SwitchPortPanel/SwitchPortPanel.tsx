/**
 * SwitchPortPanel — 交换机端口可视化面板
 *
 * 【展示组件】纯 Props 驱动，不内部获取数据，不直接订阅 Store。
 *
 * 按物理端口类型分组展示端口状态，模拟交换机面板指示灯效果：
 * - 按端口名前缀分组：100GE / 40GE / 25GE / 10GE / XGE / GE / 100M
 *   / Vlanif / Eth-Trunk / Sub-interface / Tunnel / Stack / Peer-link / 其他
 * - 每组内端口按端口号数字从小到大排列
 * - 端口状态用颜色区分：up=绿色, down=红色, admin-down=灰色, 降速=黄色, 其他=浅灰
 * - 降速检测：实际速率 < 端口最大速率时黄色显示（如 100GE 口实际跑 10GE）
 * - 悬停 Tooltip 显示端口详情
 * - 点击端口色块触发 onPortClick 回调
 * - 每组显示 up/down/降速 统计
 */
import { useMemo } from 'react';
import { Tooltip, Tag, Space, theme } from 'antd';
import {
  classifyPortType,
  getShortPortNum,
  extractPortIndex,
  PORT_TYPE_ORDER,
  PORT_TYPE_TAG_COLOR,
  getBlockWidth,
  getBlockFontSize
} from '@/utils/portType';
import { getStatusLabel } from '@/utils/portStatus';
import { PORT_USAGE_STATUS_MAP } from '@/types/enums';
import type { SwitchPort } from '@/types/models';

interface SwitchPortPanelProps {
  ports: SwitchPort[];
  onPortClick?: (port: SwitchPort) => void;
}


function getLinkStatus(port: SwitchPort): string | null {
  return port.link_status ?? port.status ?? null;
}


function parseSpeedMbps(speed: string): number {
  if (!speed) return 0;
  const s = speed.toUpperCase().replace(/\s/g, '');

  const patterns: [RegExp, number][] = [
    [/^(\d+(?:\.\d+)?)GBPS$/, 1000], // 100GBPS
    [/^(\d+(?:\.\d+)?)MBPS$/, 1], // 1000MBPS
    [/^(\d+(?:\.\d+)?)G(?:E|B)?$/, 1000], // 10G/10GE/10GB
    [/^(\d+(?:\.\d+)?)M(?:E|B)?$/, 1] // 100M/100ME/100MB
  ];

  for (const [regex, factor] of patterns) {
    const m = s.match(regex);
    if (m) return Math.round(parseFloat(m[1]) * factor);
  }

  const numMatch = s.match(/^(\d+(?:\.\d+)?)$/);
  if (numMatch) return Math.round(parseFloat(numMatch[1]));

  return 0;
}

const PORT_TYPE_MAX_SPEED: Record<string, number> = {
  '100GE': 100000,
  '40GE': 40000,
  '25GE': 25000,
  '10GE': 10000,
  XGE: 10000,
  GE: 1000,
  '100M': 100
};

function isUnderspeed(portType: string, speed: string): boolean {
  const maxSpeed = PORT_TYPE_MAX_SPEED[portType];
  if (!maxSpeed) return false;
  const actualSpeed = parseSpeedMbps(speed);
  return actualSpeed > 0 && actualSpeed < maxSpeed;
}



function getPortVisual(status: string | null | undefined, underspeed: boolean) {
  const lower = (status || '').toLowerCase();
  if (underspeed && lower === 'up') {
    return { color: '#faad14', border: 'solid', glow: true };
  }
  if (lower === 'up') {
    return { color: '#52c41a', border: 'solid', glow: true };
  }
  if (lower === 'down') {
    return { color: '#ff4d4f', border: 'solid', glow: false };
  }
  if (lower.includes('down') || lower === 'disabled') {
    return { color: '#bfbfbf', border: 'dashed', glow: false };
  }
  return { color: '#d9d9d9', border: 'dotted', glow: false };
}


function SwitchPortPanel({ ports, onPortClick }: SwitchPortPanelProps) {
  const { token } = theme.useToken();
  const groupedPorts = useMemo(() => {
    const groups: Record<string, SwitchPort[]> = {};
    for (const port of ports) {
      const key = classifyPortType(port.port_name);
      if (!groups[key]) groups[key] = [];
      groups[key].push(port);
    }
    for (const key of Object.keys(groups)) {
      groups[key].sort((a, b) => extractPortIndex(a.port_name) - extractPortIndex(b.port_name));
    }
    const sorted = PORT_TYPE_ORDER.filter((key) => groups[key]?.length).map((key) => ({
      type: key,
      ports: groups[key]
    }));
    for (const key of Object.keys(groups)) {
      if (!PORT_TYPE_ORDER.includes(key)) {
        sorted.push({ type: key, ports: groups[key] });
      }
    }
    return sorted;
  }, [ports]);

  if (!ports.length) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      {/* 图例 */}
      <div
        style={{ marginBottom: 8, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}
      >
        <span style={{ fontSize: 12, color: token.colorTextSecondary }}>状态：</span>
        <Space size={4} wrap>
          <Tag color="green" style={{ fontSize: 11, margin: 0 }}>
            在线
          </Tag>
          <Tag color="red" style={{ fontSize: 11, margin: 0 }}>
            离线
          </Tag>
          <Tag color="#faad14" style={{ fontSize: 11, margin: 0, color: '#fff' }}>
            降速
          </Tag>
          <Tag color="default" style={{ fontSize: 11, margin: 0, borderStyle: 'dashed' }}>
            管理关闭
          </Tag>
          <Tag color="default" style={{ fontSize: 11, margin: 0, borderStyle: 'dotted' }}>
            未知
          </Tag>
        </Space>
      </div>

      {/* 按端口类型分组展示 */}
      {groupedPorts.map(({ type, ports: groupPorts }) => {
        const upCount = groupPorts.filter((p) => getLinkStatus(p)?.toLowerCase() === 'up').length;
        const downCount = groupPorts.filter(
          (p) => getLinkStatus(p)?.toLowerCase() === 'down'
        ).length;
        const underspeedCount = groupPorts.filter(
          (p) => isUnderspeed(type, p.speed || '') && getLinkStatus(p)?.toLowerCase() === 'up'
        ).length;
        const otherCount = groupPorts.length - upCount - downCount;

        return (
          <div key={type} style={{ marginBottom: 12 }}>
            {/* 分组标题 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Tag
                color={PORT_TYPE_TAG_COLOR[type] ?? 'default'}
                style={{ margin: 0, fontSize: 12, fontWeight: 500 }}
              >
                {type}
              </Tag>
              <span style={{ fontSize: 11, color: token.colorTextSecondary }}>
                共 {groupPorts.length} 口
                {upCount > 0 && (
                  <span style={{ color: '#52c41a', marginLeft: 4 }}>
                    ↑{upCount - underspeedCount}
                    {underspeedCount > 0 && (
                      <span style={{ color: '#faad14' }}>+⚠{underspeedCount}</span>
                    )}
                  </span>
                )}
                {downCount > 0 && (
                  <span style={{ color: '#ff4d4f', marginLeft: 4 }}>↓{downCount}</span>
                )}
                {otherCount > 0 && (
                  <span style={{ color: '#bfbfbf', marginLeft: 4 }}>?{otherCount}</span>
                )}
              </span>
            </div>

            {/* 端口色块面板 */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 3,
                padding: '6px 8px',
                background: token.colorFillQuaternary,
                borderRadius: 6,
                border: '1px solid #f0f0f0'
              }}
            >
              {groupPorts.map((port) => {
                const underspeed = isUnderspeed(type, port.speed || '');
                const {
                  color,
                  border: borderStyle,
                  glow
                } = getPortVisual(getLinkStatus(port), underspeed);
                const shortNum = getShortPortNum(port.port_name);
                const blockWidth = getBlockWidth(shortNum);
                const fontSize = getBlockFontSize(shortNum);
                const tooltipContent = (
                  <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                    <div>
                      <b>{port.port_name}</b>
                    </div>
                    <div>
                      链路状态：{getStatusLabel(getLinkStatus(port))}
                      {underspeed ? '（降速）' : ''}
                    </div>
                    <div>
                      占用状态：
                      {PORT_USAGE_STATUS_MAP[port.usage_status]?.label ?? port.usage_status}
                    </div>
                    <div>速率：{port.speed || '-'}</div>
                    {underspeed && (
                      <div style={{ color: '#faad14' }}>
                        降速：{type} 口实际运行 {port.speed}
                      </div>
                    )}
                    <div>VLAN：{port.vlan ?? '-'}</div>
                    {port.ip_list && port.ip_list.length > 0
                      ? port.ip_list.map((ip, i) => (
                          <div key={i}>
                            IP
                            {port.ip_list!.length > 1 ? (ip.is_primary ? '（主）' : '（从）') : ''}
                            ：{ip.ip_address}
                            {ip.prefix
                              ? `/${ip.prefix}`
                              : ip.subnet_mask
                                ? `/${ip.subnet_mask}`
                                : ''}
                          </div>
                        ))
                      : port.ip_address && <div>IP：{port.ip_address}</div>}
                    {port.customer_name && <div>客户：{port.customer_name}</div>}
                  </div>
                );

                return (
                  <Tooltip key={port.port_name} title={tooltipContent} mouseEnterDelay={0.1}>
                    <div
                      onClick={() => onPortClick?.(port)}
                      style={{
                        width: blockWidth,
                        height: 22,
                        backgroundColor: color,
                        border: `1px ${borderStyle} ${color}`,
                        borderRadius: 3,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize,
                        color: '#fff',
                        fontWeight: 500,
                        cursor: onPortClick ? 'pointer' : 'default',
                        transition: 'transform 0.15s, box-shadow 0.15s',
                        boxShadow: glow ? `0 0 4px ${color}40` : 'none',
                        userSelect: 'none'
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLDivElement).style.transform = 'scale(1.15)';
                        (e.currentTarget as HTMLDivElement).style.zIndex = '1';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                        (e.currentTarget as HTMLDivElement).style.zIndex = '0';
                      }}
                    >
                      {shortNum}
                    </div>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default SwitchPortPanel;
