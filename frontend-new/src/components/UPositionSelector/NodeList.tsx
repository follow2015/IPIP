import React, { useState } from 'react';
import { Tooltip } from 'antd';
import { NODE_STATUS_COLOR } from './constants';
import type { DeviceNode } from './types';

interface NodeListProps {
  nodes: DeviceNode[];
  draggable?: boolean;
  onNodeDragStart?: (nodeId: string, idx: number) => void;
  onNodeDrop?: (targetIdx: number) => void;
}

const NodeList: React.FC<NodeListProps> = ({ nodes, draggable, onNodeDragStart, onNodeDrop }) => {
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  return (
    <div
      style={{
        display: 'flex',
        gap: 3,
        flexWrap: 'wrap',
        alignItems: 'center',
        overflow: 'hidden'
      }}
    >
      {nodes.map((n, idx) => (
        <Tooltip
          key={n.id}
          title={`${n.label}${n.ip ? ` · ${n.ip}` : ''}${n.ipmiAddress ? ` · IPMI:${n.ipmiAddress}` : ''}`}
        >
          <span
            draggable={draggable}
            onDragStart={
              draggable
                ? (e) => {
                    e.stopPropagation();
                    onNodeDragStart?.(n.id, idx);
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
              display: 'inline-block',
              width: 10,
              height: 10,
              borderRadius: 2,
              background: NODE_STATUS_COLOR[n.status],
              flexShrink: 0,
              cursor: draggable ? 'grab' : 'default',
              outline: dragOverIdx === idx ? '2px solid #378ADD' : 'none'
            }}
          />
        </Tooltip>
      ))}
    </div>
  );
};

export default NodeList;
