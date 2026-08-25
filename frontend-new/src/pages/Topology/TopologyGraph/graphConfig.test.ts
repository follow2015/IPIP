import { describe, it, expect } from 'vitest';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import type { TopologyComboDatum } from './graphBuilders';
import { buildTooltipContent } from './graphConfig';

const mkNode = (o: Partial<TopologyNode>): TopologyNode =>
  ({ device_type: 'switch', ...o }) as TopologyNode;
const mkEdge = (o: Partial<TopologyEdge>): TopologyEdge => o as TopologyEdge;
const mkCombo = (o: Partial<TopologyComboDatum>): TopologyComboDatum => o as TopologyComboDatum;

describe('buildTooltipContent — XSS 转义 (F1)', () => {
  it('节点 name 含脚本 payload 被转义为纯文本', () => {
    const html = buildTooltipContent(
      mkNode({ name: '<img src=x onerror=alert(document.cookie)>', status: 'online' })
    );
    expect(html).toContain('&lt;img src=x onerror=alert(document.cookie)&gt;');
    expect(html).not.toContain('<img src=x');
  });

  it('节点 ip 被转义', () => {
    const html = buildTooltipContent(
      mkNode({ name: 'sw1', status: 'online', ip: '"><script>alert(1)</script>' })
    );
    expect(html).toContain('&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(html).not.toContain('<script>');
  });

  it('节点 room_name 被转义', () => {
    const html = buildTooltipContent(
      mkNode({ name: 'sw1', status: 'offline', room_name: '机房<script>x</script>' })
    );
    expect(html).toContain('机房&lt;script&gt;x&lt;/script&gt;');
  });

  it('机柜 combo label 被转义', () => {
    const html = buildTooltipContent(mkCombo({ cabinetId: 10, label: 'A&B"机房' }));
    expect(html).toContain('A&amp;B&quot;机房');
  });

  it('边字段 (edge_type/bandwidth/status) 被转义', () => {
    const html = buildTooltipContent(
      mkEdge({ edge_type: '<b>x</b>', bandwidth: '"1G"', status: "'up'" })
    );
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;');
    expect(html).toContain('&quot;1G&quot;');
    expect(html).toContain('&#39;up&#39;');
  });

  it('正常文本不被破坏（不双重转义）', () => {
    const html = buildTooltipContent(mkNode({ name: 'sw-01', status: 'online', ip: '10.0.0.1' }));
    expect(html).toContain('sw-01');
    expect(html).toContain('10.0.0.1');
    expect(html).not.toContain('&amp;sw');
  });

  it('name 中的 & 被转义为 &amp;', () => {
    const html = buildTooltipContent(mkNode({ name: 'A & B', status: 'online' }));
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('A & B');
  });
});
