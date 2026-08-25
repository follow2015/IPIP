import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, cleanup, act } from '@testing-library/react';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import type { TopologyGraphHandle } from './graphBuilders';
import { Graph } from '@antv/g6';

vi.mock('@antv/g6', () => ({
  Graph: vi.fn().mockImplementation(function (opts: any) {
    return {
      options: opts,
      on: vi.fn(),
      setData: vi.fn(),
      render: vi.fn().mockResolvedValue(undefined),
      destroy: vi.fn(),
      setElementState: vi.fn(),
      focusElement: vi.fn(),
      zoomTo: vi.fn(),
      getZoom: vi.fn().mockReturnValue(1),
      fitView: vi.fn()
    };
  })
}));

import TopologyGraph from './TopologyGraph';

const mkNode = (o: Partial<TopologyNode>): TopologyNode => o as TopologyNode;
const mkEdge = (o: Partial<TopologyEdge>): TopologyEdge => o as TopologyEdge;

const mockedGraph = vi.mocked(Graph);

beforeEach(() => {
  mockedGraph.mockClear();
});

afterEach(() => {
  cleanup();
});

describe('TopologyGraph — 组件冒烟', () => {
  it('挂载时构造 Graph 实例并传入容器/尺寸/布局', () => {
    const nodes = [mkNode({ id: 1, name: 'sw1' })];
    const edges = [mkEdge({ id: 'e1', source: 1, target: 2 })];
    const { container } = render(<TopologyGraph nodes={nodes} edges={edges} layout="force" />);

    expect(container.querySelector('div')).toBeTruthy();
    expect(mockedGraph).toHaveBeenCalledTimes(1);
    const opts = mockedGraph.mock.calls[0][0];
    expect(opts.width).toBe(800);
    expect(opts.height).toBe(600);
    expect((opts.layout as unknown as { type: string }).type).toBe('force');
    expect(opts.behaviors).toContain('drag-canvas');
    expect(opts.plugins!.some((p: any) => p.type === 'tooltip')).toBe(true);
    expect(opts.plugins!.some((p: any) => p.type === 'minimap')).toBe(true);
  });

  it('切换布局时传入对应布局配置', () => {
    const nodes = [mkNode({ id: 1 })];
    const edges = [mkEdge({ id: 'e1', source: 1, target: 2 })];
    render(<TopologyGraph nodes={nodes} edges={edges} layout="dagre" />);
    expect((mockedGraph.mock.calls[0][0].layout as unknown as { type: string }).type).toBe('dagre');
  });

  it('highlightNodeId 变化时调用 setElementState', () => {
    const nodes = [mkNode({ id: 1, name: 'sw1' })];
    const edges = [mkEdge({ id: 'e1', source: 1, target: 2 })];
    const ref = React.createRef<TopologyGraphHandle>();
    render(<TopologyGraph ref={ref} nodes={nodes} edges={edges} highlightNodeId={1} />);

    const instance = mockedGraph.mock.results[0].value;
    expect(instance.setElementState).toHaveBeenCalled();
  });

  it('imperative handle 调用 Graph 方法（fitView / zoomIn）', () => {
    const nodes = [mkNode({ id: 1 })];
    const edges = [mkEdge({ id: 'e1', source: 1, target: 2 })];
    const ref = React.createRef<TopologyGraphHandle>();
    render(<TopologyGraph ref={ref} nodes={nodes} edges={edges} />);

    const instance = mockedGraph.mock.results[0].value;
    act(() => {
      ref.current?.fitView();
    });
    expect(instance.fitView).toHaveBeenCalled();
    act(() => {
      ref.current?.zoomIn();
    });
    expect(instance.zoomTo).toHaveBeenCalledWith(1.2);
  });
});
