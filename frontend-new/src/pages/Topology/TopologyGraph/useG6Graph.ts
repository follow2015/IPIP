/**
 * useG6Graph — G6 Graph 生命周期 Hook
 *
 * 把 TopologyGraph 中与 G6 实例相关的所有副作用（创建/销毁、事件绑定、
 * 尺寸监听、快捷键、数据更新、高亮）收敛到单一 Hook，组合根只负责渲染容器。
 */
import {
  useEffect,
  useRef,
  useCallback,
  useState,
  useImperativeHandle,
  type ForwardedRef,
  type RefObject
} from 'react';
import { Graph } from '@antv/g6';
import type { GraphData } from '@antv/g6';
import type { TopologyNode, TopologyEdge } from '@/types/models';
import {
  transformDataFromRefs,
  type LayoutType,
  type TopologyGraphHandle,
  type TopologyGraphProps
} from './graphBuilders';
import { buildGraphOptions } from './graphConfig';

export interface UseG6GraphParams extends TopologyGraphProps {
  ref: ForwardedRef<TopologyGraphHandle>;
}

export function useG6Graph({
  nodes,
  edges,
  layout = 'force',
  onNodeClick,
  onEdgeClick,
  highlightNodeId,
  ref
}: UseG6GraphParams): { containerRef: RefObject<HTMLDivElement | null> } {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  
  const nodesRef = useRef<TopologyNode[]>(nodes);
  const edgesRef = useRef<TopologyEdge[]>(edges);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);
  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'F') {
        e.preventDefault();
        graphRef.current?.fitView();
      }
    };
    
    
    window.addEventListener('keydown', handleKey);
    return () => {
      
      window.removeEventListener('keydown', handleKey);
    };
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        graphRef.current?.zoomTo(graphRef.current.getZoom() * 1.2);
      },
      zoomOut: () => {
        graphRef.current?.zoomTo(graphRef.current.getZoom() / 1.2);
      },
      fitView: () => {
        graphRef.current?.fitView();
      }
    }),
    []
  );

  
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setContainerSize({ width: Math.floor(width), height: Math.floor(height) });
        }
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const { width, height } = containerSize;
    if (width === 0 || height === 0) return;

    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }

    const graph = new Graph(buildGraphOptions({ container, width, height, layout }));

    graph.on('node:click', (evt) => {
      const nodeId = (evt as unknown as { target?: { id?: string } }).target?.id;
      if (nodeId && onNodeClick) {
        const nodeData = nodesRef.current.find((n) => String(n.id) === nodeId);
        if (nodeData) onNodeClick(nodeData);
      }
    });

    graph.on('edge:click', (evt) => {
      const edgeId = (evt as unknown as { target?: { id?: string } }).target?.id;
      if (edgeId && onEdgeClick) {
        const edgeData = edgesRef.current.find((e) => e.id === edgeId);
        if (edgeData) onEdgeClick(edgeData);
      }
    });

    graphRef.current = graph;

    
    let destroyed = false;
    if (nodesRef.current.length > 0) {
      graph.setData(
        transformDataFromRefs(nodesRef.current, edgesRef.current) as unknown as GraphData
      );
      graph.render().catch((e: unknown) => {
        if (!destroyed) console.warn('[TopologyGraph] render error:', e);
      });
    }

    return () => {
      destroyed = true;
      graph.destroy();
      graphRef.current = null;
    };
  }, [containerSize, layout]);

  
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !nodesRef.current.length) return;
    try {
      graph.setData(
        transformDataFromRefs(nodesRef.current, edgesRef.current) as unknown as GraphData
      );
      graph.render();
    } catch {
      
    }
  }, [nodes, edges]);

  
  const prevAffectedRef = useRef<{ nodes: Set<string>; edges: Set<string> }>({
    nodes: new Set(),
    edges: new Set()
  });
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;

    
    const computeAffected = (nodeId: number | null) => {
      const nodes = new Set<string>();
      const edges = new Set<string>();
      if (nodeId == null) return { nodes, edges };
      nodes.add(String(nodeId));
      const connectedEdgeIds = new Set(
        currentEdges.filter((e) => e.source === nodeId || e.target === nodeId).map((e) => e.id)
      );
      connectedEdgeIds.forEach((id) => edges.add(id));
      currentEdges.forEach((e) => {
        if (connectedEdgeIds.has(e.id)) {
          nodes.add(String(e.source === nodeId ? e.target : e.source));
        }
      });
      return { nodes, edges };
    };

    
    const existingNodeIds = new Set(currentNodes.map((n) => String(n.id)));
    const existingEdgeIds = new Set(currentEdges.map((e) => e.id));
    const revert = (affected: { nodes: Set<string>; edges: Set<string> }) => {
      affected.nodes.forEach((id) => {
        if (existingNodeIds.has(id)) graph.setElementState(id, []);
      });
      affected.edges.forEach((id) => {
        if (existingEdgeIds.has(id)) graph.setElementState(id, []);
      });
    };
    const apply = (affected: { nodes: Set<string>; edges: Set<string> }, nodeId: number) => {
      affected.nodes.forEach((id) => {
        graph.setElementState(id, id === String(nodeId) ? 'highlight' : 'dim');
      });
      affected.edges.forEach((id) => graph.setElementState(id, 'highlight'));
    };

    try {
      
      revert(prevAffectedRef.current);

      
      const newAffected = computeAffected(highlightNodeId ?? null);
      if (highlightNodeId != null) {
        apply(newAffected, highlightNodeId);
        
        try {
          graph.focusElement(String(highlightNodeId), {
            duration: 400,
            easing: 'ease-in-out'
          });
        } catch {
          
        }
      }

      
      prevAffectedRef.current = newAffected;
    } catch {
      
    }
  }, [highlightNodeId]);

  return { containerRef };
}
