import { describe, it, expect } from 'vitest';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import {
  truncateLabel,
  svgToDataUrl,
  getNodeIcon,
  transformDataFromRefs,
  getLayoutConfig,
  SWITCH_ICON_SVG,
  CORE_SWITCH_ICON_SVG,
  SERVER_ICON_SVG,
  OFFLINE_ICON_SVG,
  COMBO_COLORS
} from './graphBuilders';

const mkNode = (o: Partial<TopologyNode>): TopologyNode => o as TopologyNode;
const mkEdge = (o: Partial<TopologyEdge>): TopologyEdge => o as TopologyEdge;

describe('graphBuilders — 纯逻辑', () => {
  describe('truncateLabel', () => {
    it('超长名称截断并追加省略号', () => {
      const long = 'a'.repeat(20);
      const out = truncateLabel(long);
      expect(out.length).toBe(14);
      expect(out.endsWith('…')).toBe(true);
    });
    it('短名称原样返回', () => {
      expect(truncateLabel('sw-01')).toBe('sw-01');
    });
    it('空字符串返回空', () => {
      expect(truncateLabel('')).toBe('');
    });
  });

  describe('svgToDataUrl', () => {
    it('包装为 data URI', () => {
      expect(svgToDataUrl('<svg/>')).toBe('data:image/svg+xml;charset=utf-8,%3Csvg%2F%3E');
    });
  });

  describe('getNodeIcon', () => {
    it('offline → OFFLINE 图标', () => {
      expect(getNodeIcon(mkNode({ status: 'offline' }))).toBe(svgToDataUrl(OFFLINE_ICON_SVG));
    });
    it('server → SERVER 图标', () => {
      expect(getNodeIcon(mkNode({ status: 'online', device_type: 'server' }))).toBe(
        svgToDataUrl(SERVER_ICON_SVG)
      );
    });
    it('switch_role=0 → CORE 图标', () => {
      expect(getNodeIcon(mkNode({ status: 'online', device_type: 'switch', switch_role: 0 }))).toBe(
        svgToDataUrl(CORE_SWITCH_ICON_SVG)
      );
    });
    it('普通交换机 → SWITCH 图标', () => {
      expect(getNodeIcon(mkNode({ status: 'online', device_type: 'switch', switch_role: 1 }))).toBe(
        svgToDataUrl(SWITCH_ICON_SVG)
      );
    });
  });

  describe('transformDataFromRefs', () => {
    const nodes = [
      mkNode({ id: 1, name: 'sw1', cabinet_id: 10, cabinet_name: '机柜A' }),
      mkNode({ id: 2, name: 'sw2', cabinet_id: 10, cabinet_name: '机柜A' }),
      mkNode({ id: 3, name: 'sw3' }) // 无 cabinet_id
    ];
    const edges = [mkEdge({ id: 'e1', source: 1, target: 2 })];
    const data = transformDataFromRefs(nodes, edges);

    it('按 cabinet_id 生成 combo 并关联节点', () => {
      expect(data.combos).toHaveLength(1);
      expect(data.combos[0].id).toBe('cabinet-10');
      expect(data.combos[0].data.label).toBe('机柜A');
      expect(data.nodes[0].combo).toBe('cabinet-10');
      expect(data.nodes[1].combo).toBe('cabinet-10');
    });
    it('无 cabinet_id 的节点不关联 combo', () => {
      expect(data.nodes[2].combo).toBeUndefined();
    });
    it('combo 配色按索引循环', () => {
      expect(data.combos[0].data.colorIdx).toBe(0 % COMBO_COLORS.length);
    });
    it('节点 id 转为字符串且 data 深拷贝', () => {
      expect(data.nodes[0].id).toBe('1');
      expect(data.nodes[0].data).toEqual(nodes[0]);
      expect(data.nodes[0].data).not.toBe(nodes[0]);
    });
    it('边映射为字符串 source/target 并保留原始 data', () => {
      expect(data.edges).toHaveLength(1);
      expect(data.edges[0].source).toBe('1');
      expect(data.edges[0].target).toBe('2');
      expect(data.edges[0].data).toEqual(edges[0]);
    });
  });

  describe('getLayoutConfig', () => {
    it('force', () => {
      expect(getLayoutConfig('force').type).toBe('force');
    });
    it('dagre', () => {
      expect(getLayoutConfig('dagre')).toEqual({
        type: 'dagre',
        rankdir: 'TB',
        nodesep: 80,
        ranksep: 120
      });
    });
    it('concentric', () => {
      expect(getLayoutConfig('concentric').type).toBe('concentric');
    });
    it('radial', () => {
      expect(getLayoutConfig('radial').type).toBe('radial');
    });
  });
});
