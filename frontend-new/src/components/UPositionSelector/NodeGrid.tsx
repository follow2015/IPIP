import React, { useState, useMemo } from 'react';
import { Tooltip } from 'antd';
import { NODE_STATUS_COLOR } from './constants';
import type { DeviceNode } from './types';

interface NodeGridProps {
  nodes: DeviceNode[];
  nodeRows: number;
  nodeCols: number;
  draggable?: boolean;
  onNodeDragStart?: (nodeId: string, idx: number) => void;
  onNodeDrop?: (targetIdx: number) => void;
}

const NodeGrid: React.FC<NodeGridProps> = ({
  nodes,
  nodeRows,
  nodeCols,
  draggable,
  onNodeDragStart,
  onNodeDrop
}) => {
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const grid: (DeviceNode | null)[][] = useMemo(() => {
    const g: (DeviceNode | null)[][] = Array.from({ length: nodeRows }, () =>
      Array(nodeCols).fill(null)
    );
    const unplaced: DeviceNode[] = [];
    for (const n of nodes) {
      if (
        n.row != null &&
        n.col != null &&
        n.row >= 0 &&
        n.row < nodeRows &&
        n.col >= 0 &&
        n.col < nodeCols
      ) {
        g[n.row][n.col] = n;
      } else {
        unplaced.push(n);
      }
    }
    let ui = 0;
    for (let r = 0; r < nodeRows && ui < unplaced.length; r++) {
      for (let c = 0; c < nodeCols && ui < unplaced.length; c++) {
        if (!g[r][c]) g[r][c] = unplaced[ui++];
      }
    }
    return g;
  }, [nodes, nodeRows, nodeCols]);

  const flat = grid.flat();

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${nodeCols}, 1fr)`,
        gridTemplateRows: `repeat(${nodeRows}, 1fr)`,
        gap: 2,
        width: '100%',
        flex: 1,
        minHeight: 0
      }}
    >
      {flat.map((node, idx) => {
        if (!node) {
          return (
            <div
              key={`e-${idx}`}
              onDragOver={
                draggable
                  ? (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDragOverIdx(idx);
                    }
                  : undefined
              }
              onDrop={
                draggable
                  ? (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      onNodeDrop?.(idx);
                      setDragOverIdx(null);
                    }
                  : undefined
              }
              onDragLeave={draggable ? () => setDragOverIdx(null) : undefined}
              style={{
                borderRadius: 2,
                background: dragOverIdx === idx ? 'rgba(55,138,221,0.15)' : 'rgba(0,0,0,0.04)',
                border: dragOverIdx === idx ? '1px dashed #378ADD' : '1px dashed rgba(0,0,0,0.1)',
                transition: 'background 0.1s'
              }}
            />
          );
        }
        return (
          <Tooltip
            key={node.id}
            title={
              <div style={{ fontSize: 11 }}>
                <div style={{ fontWeight: 500 }}>{node.label}</div>
                {node.ip && <div>IP: {node.ip}</div>}
                {node.ipmiAddress && <div>IPMI: {node.ipmiAddress}</div>}
                <div style={{ marginTop: 2 }}>
                  状态:{' '}
                  {node.status === 'active' ? '在线' : node.status === 'fault' ? '故障' : '离线'}
                </div>
              </div>
            }
            placement="top"
          >
            <div
              draggable={draggable}
              onDragStart={
                draggable
                  ? (e) => {
                      e.stopPropagation();
                      onNodeDragStart?.(node.id, idx);
                    }
                  : undefined
              }
              onDragOver={
                draggable
                  ? (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDragOverIdx(idx);
                    }
                  : undefined
              }
              onDrop={
                draggable
                  ? (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      onNodeDrop?.(idx);
                      setDragOverIdx(null);
                    }
                  : undefined
              }
              onDragLeave={draggable ? () => setDragOverIdx(null) : undefined}
              style={{
                borderRadius: 2,
                background: NODE_STATUS_COLOR[node.status],
                border: `1px solid ${
                  node.status === 'active'
                    ? '#148F68'
                    : node.status === 'fault'
                      ? '#C43A39'
                      : '#A0A0A0'
                }`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                cursor: draggable ? 'grab' : 'default',
                outline: dragOverIdx === idx ? '2px solid #378ADD' : 'none'
              }}
            >
              <span
                style={{
                  fontSize: 8,
                  fontWeight: 500,
                  color: '#fff',
                  textShadow: '0 1px 1px rgba(0,0,0,0.3)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  padding: '0 1px',
                  lineHeight: 1
                }}
              >
                {node.label.replace(/^(Node|节点)\s*/i, '')}
              </span>
            </div>
          </Tooltip>
        );
      })}
    </div>
  );
};

export default NodeGrid;
