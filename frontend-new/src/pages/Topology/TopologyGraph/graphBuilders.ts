/**
 * graphBuilders — 拓扑图纯逻辑层
 *
 * 把 TopologyGraph 中「拓扑数据 → G6 数据」转换、布局配置、图标/常量等
 * 与 G6 实例无关的纯逻辑下沉为可单测模块。
 *
 * 注意：本文件不含 JSX、不含 @antv/g6 运行时依赖，可独立单测。
 */
import type { CSSProperties } from 'react';
import type { TopologyNode, TopologyEdge } from '@/types/models';


export type LayoutType = 'force' | 'dagre' | 'concentric' | 'radial';

export interface TopologyGraphHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

export interface TopologyGraphProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  layout?: LayoutType;
  onNodeClick?: (node: TopologyNode) => void;
  onEdgeClick?: (edge: TopologyEdge) => void;
  highlightNodeId?: number | null;
  style?: CSSProperties;
}


export interface TopologyComboDatum {
  type: string;
  label: string;
  cabinetId: number;
  colorIdx: number;
}


export const NODE_SIZES = {
  core: 44, 
  access: 34, 
  server: 28 
};
export const LABEL_FONT_SIZE = 10;
export const MAX_LABEL_LEN = 14;


export const COMBO_COLORS = [
  { fill: '#f0f5ff', stroke: '#adc6ff' },
  { fill: '#f6ffed', stroke: '#b7eb8f' },
  { fill: '#fffbe6', stroke: '#ffe58f' },
  { fill: '#fff1f0', stroke: '#ffa39e' },
  { fill: '#f9f0ff', stroke: '#d3adf7' },
  { fill: '#e6fffb', stroke: '#87e8de' },
  { fill: '#fff0f6', stroke: '#ffadd2' },
  { fill: '#fcffe6', stroke: '#eaff8f' }
];


export const SWITCH_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="4" y="16" width="56" height="32" rx="4" fill="#e6f4ff" stroke="#1677ff" stroke-width="2"/>
  <circle cx="16" cy="28" r="3" fill="#52c41a"/><circle cx="26" cy="28" r="3" fill="#52c41a"/>
  <circle cx="36" cy="28" r="3" fill="#52c41a"/><circle cx="46" cy="28" r="3" fill="#52c41a"/>
  <rect x="12" y="36" width="6" height="6" rx="1" fill="#1677ff"/><rect x="22" y="36" width="6" height="6" rx="1" fill="#1677ff"/>
  <rect x="32" y="36" width="6" height="6" rx="1" fill="#1677ff"/><rect x="42" y="36" width="6" height="6" rx="1" fill="#1677ff"/>
</svg>`;

export const CORE_SWITCH_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="4" y="16" width="56" height="32" rx="4" fill="#e6f4ff" stroke="#1677ff" stroke-width="2.5"/>
  <circle cx="16" cy="28" r="3" fill="#1677ff"/><circle cx="26" cy="28" r="3" fill="#1677ff"/>
  <circle cx="36" cy="28" r="3" fill="#1677ff"/><circle cx="46" cy="28" r="3" fill="#1677ff"/>
  <rect x="12" y="36" width="6" height="6" rx="1" fill="#1677ff"/><rect x="22" y="36" width="6" height="6" rx="1" fill="#1677ff"/>
  <rect x="32" y="36" width="6" height="6" rx="1" fill="#1677ff"/><rect x="42" y="36" width="6" height="6" rx="1" fill="#1677ff"/>
  <polygon points="32,2 34,8 40,8 35,12 37,18 32,14 27,18 29,12 24,8 30,8" fill="#1677ff"/>
</svg>`;

export const SERVER_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="8" y="4" width="48" height="16" rx="3" fill="#fffbe6" stroke="#faad14" stroke-width="2"/>
  <rect x="8" y="24" width="48" height="16" rx="3" fill="#fffbe6" stroke="#faad14" stroke-width="2"/>
  <rect x="8" y="44" width="48" height="16" rx="3" fill="#fffbe6" stroke="#faad14" stroke-width="2"/>
  <circle cx="48" cy="12" r="2.5" fill="#52c41a"/><circle cx="48" cy="32" r="2.5" fill="#52c41a"/>
  <circle cx="48" cy="52" r="2.5" fill="#52c41a"/>
  <rect x="14" y="9" width="24" height="2" rx="1" fill="#faad14" opacity="0.5"/>
  <rect x="14" y="29" width="24" height="2" rx="1" fill="#faad14" opacity="0.5"/>
  <rect x="14" y="49" width="24" height="2" rx="1" fill="#faad14" opacity="0.5"/>
</svg>`;

export const OFFLINE_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="4" y="16" width="56" height="32" rx="4" fill="#f5f5f5" stroke="#d9d9d9" stroke-width="2"/>
  <circle cx="16" cy="28" r="3" fill="#d9d9d9"/><circle cx="26" cy="28" r="3" fill="#d9d9d9"/>
  <circle cx="36" cy="28" r="3" fill="#d9d9d9"/><circle cx="46" cy="28" r="3" fill="#d9d9d9"/>
  <rect x="12" y="36" width="6" height="6" rx="1" fill="#d9d9d9"/><rect x="22" y="36" width="6" height="6" rx="1" fill="#d9d9d9"/>
  <rect x="32" y="36" width="6" height="6" rx="1" fill="#d9d9d9"/><rect x="42" y="36" width="6" height="6" rx="1" fill="#d9d9d9"/>
</svg>`;

export function svgToDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function getNodeIcon(node: TopologyNode): string {
  if (node.status === 'offline') return svgToDataUrl(OFFLINE_ICON_SVG);
  if (node.device_type === 'server') return svgToDataUrl(SERVER_ICON_SVG);
  if (node.switch_role === 0) return svgToDataUrl(CORE_SWITCH_ICON_SVG);
  return svgToDataUrl(SWITCH_ICON_SVG);
}

export function truncateLabel(name: string): string {
  if (!name) return '';
  return name.length > MAX_LABEL_LEN ? name.slice(0, MAX_LABEL_LEN - 1) + '…' : name;
}


export interface G6TopologyData {
  nodes: { id: string; combo?: string; data: TopologyNode }[];
  edges: { id: string; source: string; target: string; data: TopologyEdge }[];
  combos: { id: string; data: TopologyComboDatum }[];
}


export function transformDataFromRefs(
  nodes: TopologyNode[],
  edges: TopologyEdge[]
): G6TopologyData {
  
  const cabinetMap = new Map<number, { name: string; nodeIds: string[] }>();
  nodes.forEach((node) => {
    const cid = node.cabinet_id;
    if (cid == null) return;
    if (!cabinetMap.has(cid)) {
      cabinetMap.set(cid, {
        name: node.cabinet_name ?? `机柜 ${cid}`,
        nodeIds: []
      });
    }
    cabinetMap.get(cid)!.nodeIds.push(String(node.id));
  });

  const combos = Array.from(cabinetMap.entries()).map(([cid, info], idx) => ({
    id: `cabinet-${cid}`,
    data: {
      type: 'rect',
      label: info.name,
      cabinetId: cid,
      colorIdx: idx % COMBO_COLORS.length
    } satisfies TopologyComboDatum
  }));

  
  const g6Nodes = nodes.map((node) => ({
    id: String(node.id),
    combo: node.cabinet_id != null ? `cabinet-${node.cabinet_id}` : undefined,
    data: { ...node }
  }));

  
  const g6Edges = edges.map((edge) => ({
    id: edge.id,
    source: String(edge.source),
    target: String(edge.target),
    data: { ...edge }
  }));

  return { nodes: g6Nodes, edges: g6Edges, combos };
}


export function getLayoutConfig(type: LayoutType) {
  switch (type) {
    case 'force':
      return {
        type: 'force',
        preventOverlap: true,
        nodeSize: NODE_SIZES.access + 24,
        linkDistance: 180,
        nodeStrength: -600,
        edgeStrength: 0.08,
        collideStrength: 1.2,
        alphaDecay: 0.028,
        alphaMin: 0.001,
        animated: false
      };
    case 'dagre':
      return { type: 'dagre', rankdir: 'TB', nodesep: 80, ranksep: 120 };
    case 'concentric':
      return {
        type: 'concentric',
        preventOverlap: true,
        nodeSize: NODE_SIZES.access + 24,
        minNodeSpacing: 40
      };
    case 'radial':
      return {
        type: 'radial',
        preventOverlap: true,
        nodeSize: NODE_SIZES.access + 24,
        unitRadius: 120,
        minNodeSpacing: 40
      };
    default:
      return {
        type: 'force',
        preventOverlap: true,
        nodeSize: NODE_SIZES.access + 24,
        linkDistance: 180,
        nodeStrength: -600
      };
  }
}
