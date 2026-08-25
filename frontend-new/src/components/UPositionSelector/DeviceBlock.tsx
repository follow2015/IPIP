import React, { useState, useCallback, useEffect } from 'react';
import { Tooltip } from 'antd';
import { DownOutlined, RightOutlined as CollapseIcon } from '@ant-design/icons';
import { TYPE_CONFIG, ROW_GAP, NODE_STATUS_COLOR } from './constants';
import { computeBlockInfoVisibility } from './layout';
import { uToTop } from './geometry';
import NodeGrid from './NodeGrid';
import NodeList from './NodeList';
import type { DeviceNode, OccupiedPosition } from './types';
import type { LayoutMetrics } from './layout';

interface DeviceBlockProps {
  device: OccupiedPosition;
  totalU: number;
  readOnly: boolean;
  isSelected: boolean;
  isCollapsed: boolean;
  layout: LayoutMetrics;
  onSelect: () => void;
  onToggleCollapse: () => void;
  onDragStart: (e: React.DragEvent, deviceId: number, offsetInDevice: number) => void;
  onNodeReorder?: (chassisId: number, newOrderedNodeIds: string[]) => void;
}

const DeviceBlock: React.FC<DeviceBlockProps> = ({
  device,
  readOnly,
  isSelected,
  isCollapsed,
  layout,
  onSelect,
  onToggleCollapse,
  onDragStart,
  onNodeReorder
}) => {
  const cfg = TYPE_CONFIG[device.deviceType ?? 'server'];
  const h = device.uSize * layout.unit - ROW_GAP;
  const top = uToTop(device.uPosition, layout.unit);
  const isMulti = device.deviceType === 'multinode';
  const hasNodes = isMulti && device.nodes && device.nodes.length > 0;

  const { titleFontSize, infoFontSize, contentWidth, rowH } = layout;

  const { showInfoLine, showModelLine, showSnLine, showInlineInfo } = computeBlockInfoVisibility(
    h,
    contentWidth,
    rowH
  );

  const [nodeDragSrcIdx, setNodeDragSrcIdx] = useState<number | null>(null);
  const [localNodes, setLocalNodes] = useState<DeviceNode[]>(device.nodes ?? []);
  useEffect(() => {
    setLocalNodes(device.nodes ?? []);
  }, [device.nodes]);

  const handleNodeDragStart = useCallback((_nodeId: string, idx: number) => {
    setNodeDragSrcIdx(idx);
  }, []);

  const handleNodeDrop = useCallback(
    (targetIdx: number) => {
      if (nodeDragSrcIdx === null || nodeDragSrcIdx === targetIdx) {
        setNodeDragSrcIdx(null);
        return;
      }
      const next = [...localNodes];
      const [moved] = next.splice(nodeDragSrcIdx, 1);
      next.splice(targetIdx, 0, moved);
      setLocalNodes(next);
      setNodeDragSrcIdx(null);
      onNodeReorder?.(
        device.deviceId,
        next.map((n) => n.id)
      );
    },
    [nodeDragSrcIdx, localNodes, device.deviceId, onNodeReorder]
  );

  const handleDragStart = (e: React.DragEvent) => {
    const blockRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const relY = e.clientY - blockRect.top;
    const offsetInDevice = Math.floor(relY / layout.unit);
    onDragStart(e, device.deviceId, offsetInDevice);
  };

  const infoParts: string[] = [];
  if (device.ip) infoParts.push(device.ip);
  if (device.ipmiAddress) infoParts.push(`IPMI:${device.ipmiAddress}`);

  return (
    <div
      draggable={!readOnly}
      onClick={onSelect}
      onDragStart={handleDragStart}
      style={{
        position: 'absolute',
        left: layout.uNumW + 4,
        right: 4,
        top,
        height: h,
        borderRadius: 4,
        border: `1px solid ${isSelected ? cfg.accent : cfg.border}`,
        background: cfg.bg,
        cursor: readOnly ? 'default' : 'grab',
        overflow: 'hidden',
        boxShadow: isSelected ? `0 0 0 2px ${cfg.accent}44` : undefined,
        transition: 'box-shadow 0.15s',
        zIndex: 2,
        boxSizing: 'border-box'
      }}
    >
      {/* 左侧色条 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: cfg.accent
        }}
      />

      <div
        style={{
          marginLeft: 7,
          height: '100%',
          width: 'calc(100% - 7px)',
          display: 'flex',
          flexDirection: 'column',
          padding: isMulti ? '2px 6px 2px 5px' : '0 6px 0 5px',
          gap: 1,
          overflow: 'hidden'
        }}
      >
        {/* 标题行 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          {/* 机箱折叠按钮 */}
          {hasNodes && !readOnly && (
            <span
              onClick={(e) => {
                e.stopPropagation();
                onToggleCollapse();
              }}
              style={{
                cursor: 'pointer',
                color: cfg.subText,
                fontSize: 9,
                flexShrink: 0,
                lineHeight: 1,
                padding: '1px 2px'
              }}
            >
              {isCollapsed ? <CollapseIcon /> : <DownOutlined />}
            </span>
          )}

          <span
            style={{
              fontSize: titleFontSize,
              fontWeight: 500,
              color: cfg.text,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flex: 1,
              minWidth: 0,
              lineHeight: 1.2
            }}
          >
            {device.deviceName}
          </span>

          {/* 1U设备内联IP（宽度足够但不占额外行） */}
          {showInlineInfo && !isMulti && infoParts.length > 0 && (
            <span
              style={{
                fontSize: infoFontSize,
                color: cfg.subText,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                flexShrink: 0,
                maxWidth: '40%'
              }}
            >
              {infoParts.join(' · ')}
            </span>
          )}

          {/* 多节点汇总 */}
          {isMulti && hasNodes && (
            <span
              style={{
                fontSize: Math.max(infoFontSize, 8),
                color: cfg.subText,
                flexShrink: 0,
                whiteSpace: 'nowrap'
              }}
            >
              {localNodes.filter((n) => n.status === 'active').length}/{localNodes.length} 在线
              {device.power ? ` · ${device.power}W` : ''}
            </span>
          )}

          {/* 普通设备：型号 + 功率（自适应：仅空间足够时显示） */}
          {!isMulti && (
            <>
              {showModelLine && device.model && (
                <span
                  style={{
                    fontSize: infoFontSize + 1,
                    color: cfg.subText,
                    whiteSpace: 'nowrap',
                    flexShrink: 0
                  }}
                >
                  {device.model}
                </span>
              )}
              {showInfoLine && device.power ? (
                <span
                  style={{
                    fontSize: infoFontSize + 1,
                    color: cfg.subText,
                    whiteSpace: 'nowrap',
                    flexShrink: 0
                  }}
                >
                  {device.power}W
                </span>
              ) : null}
            </>
          )}
        </div>

        {/* IP / IPMI 信息行（自适应：宽度+高度足够时显示） */}
        {showInfoLine && infoParts.length > 0 && (
          <div
            style={{
              fontSize: infoFontSize,
              color: cfg.subText,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flexShrink: 0,
              lineHeight: 1.2
            }}
          >
            {infoParts.join(' · ')}
          </div>
        )}

        {/* 序列号行（自适应：宽度+高度足够时显示） */}
        {showSnLine && device.sn && (
          <div
            style={{
              fontSize: infoFontSize,
              color: cfg.subText,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flexShrink: 0,
              lineHeight: 1.2
            }}
          >
            SN: {device.sn}
          </div>
        )}

        {/* 机箱节点区域（未折叠时显示） */}
        {hasNodes && !isCollapsed && (
          <>
            {device.nodeRows && device.nodeCols ? (
              <NodeGrid
                nodes={localNodes}
                nodeRows={device.nodeRows}
                nodeCols={device.nodeCols}
                draggable={!readOnly}
                onNodeDragStart={handleNodeDragStart}
                onNodeDrop={handleNodeDrop}
              />
            ) : (
              <NodeList
                nodes={localNodes}
                draggable={!readOnly}
                onNodeDragStart={handleNodeDragStart}
                onNodeDrop={handleNodeDrop}
              />
            )}
          </>
        )}

        {/* 折叠态：只显示圆点汇总 */}
        {hasNodes && isCollapsed && (
          <div
            style={{
              display: 'flex',
              gap: 2,
              flexWrap: 'wrap',
              alignItems: 'center',
              overflow: 'hidden'
            }}
          >
            {localNodes.slice(0, 20).map((n) => (
              <Tooltip key={n.id} title={n.label}>
                <span
                  style={{
                    display: 'inline-block',
                    width: 6,
                    height: 6,
                    borderRadius: 1,
                    background: NODE_STATUS_COLOR[n.status],
                    flexShrink: 0
                  }}
                />
              </Tooltip>
            ))}
            {localNodes.length > 20 && (
              <span style={{ fontSize: 8, color: cfg.subText }}>+{localNodes.length - 20}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DeviceBlock;
