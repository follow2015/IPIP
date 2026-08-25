/**
 * graphConfig — G6 配置构造层
 *
 * 把 `new Graph(options)` 所需的 node / edge / combo 样式、状态、插件、布局等
 * 「配置数据」构造为纯函数，便于结构与 tooltip 内容单测。
 *
 * 注意：本文件只产出配置对象，不实例化 Graph、不绑定事件监听
 * （事件监听由 useG6Graph 在 Graph 创建后绑定）。
 */
import type { GraphOptions } from '@antv/g6';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import { escapeHtml } from '@/utils/escapeHtml';
import {
  NODE_SIZES,
  LABEL_FONT_SIZE,
  COMBO_COLORS,
  SWITCH_ICON_SVG,
  svgToDataUrl,
  getNodeIcon,
  truncateLabel,
  getLayoutConfig,
  type LayoutType,
  type TopologyComboDatum
} from './graphBuilders';

interface G6StyleDatum {
  data?: {
    switch_role?: number;
    device_type?: string;
    name?: string;
    edge_type?: string;
    bandwidth?: string;
    colorIdx?: number;
    label?: string;
  };
}


const TOOLTIP_BOX_STYLE = `
  padding:8px 12px;
  background:#fff; border:1px solid #f0f0f0;
  border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.12);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:12px; line-height:1.8; color:#262626;
`;

/**
 * 根据节点 / 边 / 机柜 combo 的数据生成 tooltip HTML 字符串。
 * 判定顺序：device_type → cabinetId → 否则视为边。
 */
export function buildTooltipContent(
  data: TopologyNode | TopologyEdge | TopologyComboDatum
): string {
  if ('device_type' in data) {
    const node = data;
    const role = node.switch_role === 0 ? '核心' : node.switch_role === 1 ? '接入' : '-';
    const statusColor = node.status === 'online' ? '#52c41a' : '#d9d9d9';
    return `<div style="min-width:160px; ${TOOLTIP_BOX_STYLE}">
      <div style="font-weight:600;font-size:13px;margin-bottom:4px">${escapeHtml(node.name)}</div>
      <div style="color:#8c8c8c">
        <span style="display:inline-block;width:6px;height:6px;border-radius:50%;
          background:${statusColor};margin-right:4px;vertical-align:middle"></span>
        ${node.status === 'online' ? '在线' : '离线'}
      </div>
      ${node.ip ? `<div>IP: <span style="color:#1677ff">${escapeHtml(node.ip)}</span></div>` : ''}
      ${node.switch_role != null ? `<div>角色: ${role}</div>` : ''}
      ${node.layer != null ? `<div>层级: L${node.layer}</div>` : ''}
      ${node.room_name ? `<div style="color:#8c8c8c;margin-top:2px">${escapeHtml(node.room_name)}</div>` : ''}
    </div>`;
  }
  if ('cabinetId' in data) {
    return `<div style="${TOOLTIP_BOX_STYLE}">
      <div style="font-weight:600">${escapeHtml(data.label)}</div>
    </div>`;
  }
  const edge = data;
  return `<div style="${TOOLTIP_BOX_STYLE}">
    <div>类型: ${escapeHtml(edge.edge_type ?? '-')}</div>
    <div>带宽: ${escapeHtml(edge.bandwidth ?? '-')}</div>
    <div>状态: ${escapeHtml(edge.status ?? '-')}</div>
  </div>`;
}

interface BuildGraphOptionsParams {
  container: HTMLDivElement;
  width: number;
  height: number;
  layout: LayoutType;
}

/**
 * 构造 G6 Graph 实例所需的完整配置对象（不含事件监听）。
 */
export function buildGraphOptions({
  container,
  width,
  height,
  layout
}: BuildGraphOptionsParams): GraphOptions {
  return {
    container,
    width,
    height,
    autoFit: 'view',
    node: {
      type: 'image',
      style: {
        size: (d: G6StyleDatum) => {
          const node = d.data;
          if (node?.switch_role === 0) return NODE_SIZES.core;
          if (node?.device_type === 'server') return NODE_SIZES.server;
          return NODE_SIZES.access;
        },
        src: (d: G6StyleDatum) => {
          const node = d.data;
          if (!node) return svgToDataUrl(SWITCH_ICON_SVG);
          return getNodeIcon(node as unknown as TopologyNode);
        },
        labelText: (d: G6StyleDatum) => truncateLabel(d.data?.name ?? ''),
        labelPlacement: 'bottom',
        labelOffsetY: 6,
        labelFontSize: LABEL_FONT_SIZE,
        labelFontWeight: 400,
        labelFill: '#595959',
        cursor: 'pointer',
        shadowColor: (d: G6StyleDatum) =>
          d.data?.switch_role === 0 ? 'rgba(22,119,255,0.25)' : 'transparent',
        shadowBlur: (d: G6StyleDatum) => (d.data?.switch_role === 0 ? 16 : 0)
      },
      state: {
        selected: { shadowColor: 'rgba(22,119,255,0.4)', shadowBlur: 16 },
        highlight: { shadowColor: 'rgba(22,119,255,0.2)', shadowBlur: 10 },
        dim: { opacity: 0.18, filter: 'grayscale(80%)' }
      }
    },
    edge: {
      type: 'line',
      style: {
        stroke: (d: G6StyleDatum) => {
          switch (d.data?.edge_type) {
            case 'uplink':
              return '#1677ff';
            case 'd2n':
              return '#ff7a45';
            case 'n2n':
              return '#52c41a';
            default:
              return '#8c8c8c';
          }
        },
        lineWidth: (d: G6StyleDatum) => {
          if (d.data?.edge_type === 'uplink') return 2.5;
          if (d.data?.edge_type === 'n2n') return 1.5;
          return 1;
        },
        lineDash: (d: G6StyleDatum) => {
          if (d.data?.edge_type === 'uplink') return [6, 3];
          if (d.data?.edge_type === 'd2n') return [2, 2];
          return undefined;
        },
        startArrow: (d: G6StyleDatum) => d.data?.edge_type === 'n2n',
        endArrow: true,
        labelText: (d: G6StyleDatum) => {
          if (d.data?.edge_type === 'd2n') return '';
          return d.data?.bandwidth ?? '';
        },
        labelFontSize: 9,
        labelFill: '#8c8c8c',
        labelBackground: true,
        labelBackgroundFill: 'rgba(255,255,255,0.8)',
        labelBackgroundPadding: [1, 4],
        cursor: 'pointer'
      },
      state: {
        selected: { lineWidth: 3, stroke: '#1677ff' },
        highlight: { stroke: '#1677ff', lineWidth: 2 },
        dim: { opacity: 0.15 }
      }
    },
    combo: {
      type: 'rect',
      style: {
        fill: (d: G6StyleDatum) => {
          const idx = d.data?.colorIdx ?? 0;
          return COMBO_COLORS[idx % COMBO_COLORS.length].fill;
        },
        stroke: (d: G6StyleDatum) => {
          const idx = d.data?.colorIdx ?? 0;
          return COMBO_COLORS[idx % COMBO_COLORS.length].stroke;
        },
        lineWidth: 1.5,
        radius: 8,
        labelText: (d: G6StyleDatum) => d.data?.label ?? '',
        labelFontSize: 11,
        labelFontWeight: 600,
        labelFill: '#8c8c8c',
        labelPlacement: 'top',
        labelOffsetY: -4,
        padding: [20, 16, 16, 16],
        cursor: 'default'
      },
      state: {
        selected: { lineWidth: 2, stroke: '#1677ff' },
        highlight: { lineWidth: 2, stroke: '#1677ff' },
        dim: { opacity: 0.3 }
      }
    },
    layout: getLayoutConfig(layout),
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', 'click-select', 'collapse-expand'],
    plugins: [
      {
        type: 'tooltip',
        getContent: (_e: unknown, items: Array<{ model?: { data?: G6StyleDatum['data'] } }>) => {
          if (!items.length) return '';
          const data = items[0]?.model?.data;
          if (!data) return '';
          return buildTooltipContent(data as unknown as TopologyNode);
        }
      },
      {
        type: 'minimap',
        size: [140, 90],
        position: 'right-bottom',
        offsetX: -12,
        offsetY: -12
      }
    ],
    animation: true,
    background: '#fafafa'
  };
}
