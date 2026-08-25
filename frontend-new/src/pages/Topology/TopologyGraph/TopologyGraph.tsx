/**
 * TopologyGraph — 组合根
 *
 * 仅负责渲染容器节点，所有 G6 副作用（实例生命周期、事件、尺寸、高亮）
 * 由 useG6Graph Hook 持有。类型与纯逻辑见 graphBuilders / graphConfig。
 */
import React, { forwardRef } from 'react';
import { useG6Graph } from './useG6Graph';
import type { TopologyGraphHandle, TopologyGraphProps } from './graphBuilders';

const TopologyGraph = forwardRef<TopologyGraphHandle, TopologyGraphProps>(
  ({ nodes, edges, layout, onNodeClick, onEdgeClick, highlightNodeId, style }, ref) => {
    const { containerRef } = useG6Graph({
      nodes,
      edges,
      layout,
      onNodeClick,
      onEdgeClick,
      highlightNodeId,
      ref
    });

    return (
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          background: '#fafafa',
          borderRadius: 8,
          overflow: 'hidden',
          ...style
        }}
      />
    );
  }
);

TopologyGraph.displayName = 'TopologyGraph';

export default TopologyGraph;
