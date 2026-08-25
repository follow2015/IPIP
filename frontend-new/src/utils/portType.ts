/**
 * portType — 端口类型识别与分组工具
 *
 * 从 SwitchPortPanel / VlanTab / LagTab 提取的共用逻辑，
 * 统一端口类型识别规则、颜色映射、排序权重。
 */


export const PORT_TYPE_RULES: [RegExp, string][] = [
  [/^100GE/i, '100GE'],
  [/^40GE/i, '40GE'],
  [/^25GE/i, '25GE'],
  [/^10GE/i, '10GE'],
  [/^XGigabitE/i, 'XGE'],
  [/^XGE/i, 'XGE'],
  [/^GigabitE/i, 'GE'],
  [/^GE/i, 'GE'],
  [/^HundredGigE/i, '100GE'],
  [/^FortyGigE/i, '40GE'],
  [/^TwentyFiveGigE/i, '25GE'],
  [/^TenGigE/i, '10GE'],
  [/^FastE/i, '100M'],
  [/^Vlanif/i, 'Vlanif'],
  [/^Vlan-interface/i, 'Vlanif'],
  [/^Vlan/i, 'Vlanif'],
  [/^Eth-Trunk/i, 'Eth-Trunk'],
  [/^Port-channel/i, 'Eth-Trunk'],
  [/^Bridge-Aggregation/i, 'Eth-Trunk'],
  [/^Link-Aggregation/i, 'Eth-Trunk'],
  [/\.\d+$/, 'Sub-interface'],
  [/^Tunnel/i, 'Tunnel'],
  [/^Stack/i, 'Stack'],
  [/^Cluster/i, 'Stack'],
  [/^CSS/i, 'Stack'],
  [/^Peer-link/i, 'Peer-link'],
  [/^MEth/i, '管理口'],
  [/^LoopBack/i, 'LoopBack'],
  [/^NULL/i, 'NULL']
];


export function classifyPortType(name: string): string {
  for (const [regex, type] of PORT_TYPE_RULES) {
    if (regex.test(name)) return type;
  }
  return '其他';
}


const PHYSICAL_PORT_TYPES = new Set(['100GE', '40GE', '25GE', '10GE', 'XGE', 'GE', '100M']);


export function isPhysicalPort(portName: string): boolean {
  const type = classifyPortType(portName);
  return PHYSICAL_PORT_TYPES.has(type);
}


export const PORT_TYPE_ORDER = [
  '100GE',
  '40GE',
  '25GE',
  '10GE',
  'XGE',
  'GE',
  '100M',
  'Vlanif',
  'Eth-Trunk',
  'Sub-interface',
  'Tunnel',
  'Stack',
  'Peer-link',
  '管理口',
  'LoopBack',
  'NULL',
  '其他'
];


export const PORT_TYPE_SORT_WEIGHT: Record<string, number> = {
  '100GE': 0,
  '40GE': 1,
  '25GE': 2,
  '10GE': 3,
  XGE: 4,
  GE: 5,
  '100M': 6,
  Vlanif: 100,
  'Eth-Trunk': 101,
  'Sub-interface': 102,
  Tunnel: 103,
  Stack: 104,
  'Peer-link': 105,
  管理口: 200,
  LoopBack: 201,
  NULL: 202,
  其他: 300
};


export function extractPortIndex(name: string): number {
  if (!name) return 0;
  const parts = name.split('/');
  const last = parts[parts.length - 1] || '';
  if (/^\d+$/.test(last)) return parseInt(last, 10);
  const match = name.match(/(\d+)(?:\.\d+)?$/);
  return match ? parseInt(match[1], 10) : 0;
}


export function getShortPortNum(name: string): string {
  if (!name) return '';
  const parts = name.split('/');
  const last = parts[parts.length - 1] || '';
  if (/^\d+$/.test(last)) return last;
  const match = name.match(/(\d+)(?:\.\d+)?$/);
  return match ? match[1] : '';
}


export const PORT_TYPE_TAG_COLOR: Record<string, string> = {
  '100GE': 'magenta',
  '40GE': 'purple',
  '25GE': 'volcano',
  '10GE': 'orange',
  XGE: 'orange',
  GE: 'blue',
  '100M': 'cyan',
  Vlanif: 'geekblue',
  'Eth-Trunk': 'gold',
  'Sub-interface': 'lime',
  Tunnel: 'green',
  Stack: 'purple',
  'Peer-link': 'red',
  管理口: 'default',
  LoopBack: 'default',
  NULL: 'default',
  其他: 'default'
};


export const PORT_TYPE_BAR_COLOR: Record<string, string> = {
  '100GE': '#eb2f96',
  '40GE': '#722ed1',
  '25GE': '#fa541c',
  '10GE': '#fa8c16',
  XGE: '#fa8c16',
  GE: '#1677ff',
  '100M': '#13c2c2',
  'Eth-Trunk': '#d48806',
  其他: '#8c8c8c'
};


export function getBlockWidth(shortNum: string): number {
  if (shortNum.length <= 2) return 28;
  if (shortNum.length === 3) return 34;
  return 40;
}


export function getBlockFontSize(shortNum: string): number {
  if (shortNum.length <= 2) return 9;
  if (shortNum.length === 3) return 8;
  return 7;
}
