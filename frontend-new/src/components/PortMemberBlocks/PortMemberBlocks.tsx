/**
 * PortMemberBlocks — 按端口类型分组的成员端口色块展示
 *
 * 从 VlanTab / LagTab 提取的共享组件，包含：
 * - renderPortDetail: 端口详情 Popover 内容
 * - GroupedMemberPorts: 按端口类型分组的色块面板
 * - PortLegend: 占用状态 + 端口类型图例
 */
import { useMemo } from 'react';
import { Tag, Popover, Space, theme } from 'antd';
import {
  classifyPortType,
  getShortPortNum,
  extractPortIndex,
  PORT_TYPE_ORDER,
  PORT_TYPE_TAG_COLOR,
  PORT_TYPE_BAR_COLOR,
  getBlockWidth,
  getBlockFontSize
} from '@/utils/portType';
import { PORT_STATUS_BG_COLOR, PORT_USAGE_STATUS_MAP } from '@/types/enums';
import type { SwitchPort } from '@/types/models';


export function renderPortDetail(port: SwitchPort | undefined, portName: string) {
  const type = classifyPortType(portName);
  if (!port) {
    return (
      <div style={{ fontSize: 12, lineHeight: 1.8, minWidth: 160 }}>
        <div>
          <b>{portName}</b>
        </div>
        <div>类型：{type}</div>
        <div style={{ color: '#8c8c8c' }}>暂无端口详情数据</div>
      </div>
    );
  }
  return (
    <div style={{ fontSize: 12, lineHeight: 1.8, minWidth: 160 }}>
      <div>
        <b>{port.port_name}</b>
      </div>
      <div>类型：{type}</div>
      <div>占用：{PORT_USAGE_STATUS_MAP[port.usage_status]?.label ?? port.usage_status}</div>
      {port.link_status && <div>链路：{port.link_status}</div>}
      <div>速率：{port.speed || '-'}</div>
      <div>VLAN：{port.vlan ?? '-'}</div>
      {port.ip_address && <div>IP：{port.ip_address}</div>}
      {port.customer_name && <div>客户：{port.customer_name}</div>}
      {port.notes && <div>备注：{port.notes}</div>}
    </div>
  );
}


export function GroupedMemberPorts({
  memberPorts,
  portMap
}: {
  memberPorts: string[];
  portMap: Map<string, SwitchPort>;
}) {
  const { token } = theme.useToken();
  
  const groups = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const name of memberPorts) {
      const type = classifyPortType(name);
      if (!map[type]) map[type] = [];
      map[type].push(name);
    }
    
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => extractPortIndex(a) - extractPortIndex(b));
    }
    
    const sorted = PORT_TYPE_ORDER.filter((key) => map[key]?.length).map((key) => ({
      type: key,
      ports: map[key]
    }));
    
    for (const key of Object.keys(map)) {
      if (!PORT_TYPE_ORDER.includes(key)) {
        sorted.push({ type: key, ports: map[key] });
      }
    }
    return sorted;
  }, [memberPorts]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {groups.map(({ type, ports: groupPorts }) => {
        const barColor = PORT_TYPE_BAR_COLOR[type] ?? PORT_TYPE_BAR_COLOR['其他'];
        return (
          <div key={type}>
            {}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <Tag
                color={PORT_TYPE_TAG_COLOR[type] ?? 'default'}
                style={{
                  margin: 0,
                  fontSize: 11,
                  fontWeight: 500,
                  lineHeight: '18px',
                  padding: '0 4px'
                }}
              >
                {type}
              </Tag>
              <span style={{ fontSize: 11, color: token.colorTextSecondary }}>
                {groupPorts.length} 口
              </span>
            </div>
            {}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 3,
                padding: '4px 6px',
                background: token.colorFillQuaternary,
                borderRadius: 4,
                border: '1px solid #f0f0f0'
              }}
            >
              {groupPorts.map((portName) => {
                const port = portMap.get(portName);
                const usageStatus = port?.usage_status ?? 'free';
                const bgColor = PORT_STATUS_BG_COLOR[usageStatus] ?? PORT_STATUS_BG_COLOR.free;
                const shortNum = getShortPortNum(portName);
                const width = getBlockWidth(shortNum);
                const fontSize = getBlockFontSize(shortNum);

                const block = (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'stretch',
                      borderRadius: 3,
                      overflow: 'hidden',
                      cursor: 'pointer'
                    }}
                  >
                    {}
                    <div style={{ width: 3, backgroundColor: barColor, flexShrink: 0 }} />
                    {}
                    <div
                      style={{
                        width,
                        height: 20,
                        backgroundColor: bgColor,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize,
                        color: '#fff',
                        fontWeight: 500,
                        userSelect: 'none'
                      }}
                    >
                      {shortNum}
                    </div>
                  </div>
                );

                return (
                  <Popover
                    key={portName}
                    content={renderPortDetail(port, portName)}
                    title="端口详情"
                    trigger="click"
                    mouseEnterDelay={0.1}
                  >
                    {block}
                  </Popover>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}


export function PortLegend() {
  const { token } = theme.useToken();
  return (
    <div
      style={{ marginBottom: 8, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}
    >
      <span style={{ fontSize: 12, color: token.colorTextSecondary }}>占用：</span>
      <Space size={4} wrap>
        {Object.values(PORT_USAGE_STATUS_MAP).map((cfg) => (
          <Tag key={cfg.label} color={cfg.color} style={{ fontSize: 11, margin: 0 }}>
            {cfg.label}
          </Tag>
        ))}
      </Space>
      <span style={{ fontSize: 12, color: token.colorTextSecondary, marginLeft: 8 }}>类型：</span>
      <Space size={4} wrap>
        <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>
          GE
        </Tag>
        <Tag color="orange" style={{ fontSize: 11, margin: 0 }}>
          10GE
        </Tag>
        <Tag color="purple" style={{ fontSize: 11, margin: 0 }}>
          40GE
        </Tag>
        <Tag color="magenta" style={{ fontSize: 11, margin: 0 }}>
          100GE
        </Tag>
        <Tag color="gold" style={{ fontSize: 11, margin: 0 }}>
          Eth-Trunk
        </Tag>
      </Space>
    </div>
  );
}
