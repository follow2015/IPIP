import React from 'react';
import { theme } from 'antd';
import { uToTop, displayLabel } from './geometry';
import DeviceBlock from './DeviceBlock';
import type { LayoutMetrics } from './layout';
import type { OccupiedPosition } from './types';

interface RackBodyProps {
  bodyRef: React.RefObject<HTMLDivElement | null>;
  devices: OccupiedPosition[];
  layout: LayoutMetrics;
  totalU: number;
  readOnly: boolean;
  selectedId: number | null;
  collapsed: Record<number, boolean>;
  highlightUs: number[];
  occupiedSet: Set<number>;
  totalH: number;
  deviceCount: number;
  usedU: number;
  usedP: number;
  onSelect: (id: number) => void;
  onToggleCollapse: (deviceId: number) => void;
  onDragStart: (e: React.DragEvent, id: number, offsetInDevice: number) => void;
  onSlotDragOver: (e: React.DragEvent) => void;
  onSlotDrop: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  clearHighlight: () => void;
  onNodeReorder?: (chassisId: number, newOrderedNodeIds: string[]) => void;
}


const RackBody: React.FC<RackBodyProps> = ({
  bodyRef,
  devices,
  layout,
  totalU,
  readOnly,
  selectedId,
  collapsed,
  highlightUs,
  occupiedSet,
  totalH,
  deviceCount,
  usedU,
  usedP,
  onSelect,
  onToggleCollapse,
  onDragStart,
  onSlotDragOver,
  onSlotDrop,
  onDragEnd,
  clearHighlight,
  onNodeReorder
}) => {
  const { token } = theme.useToken();

  return (
    <div
      style={{
        flex: layout.showSidePanel ? '1 1 320' : '1 1 100%',
        minWidth: 240,
        maxWidth: layout.showSidePanel ? 600 : undefined,
        background: token.colorBgLayout,
        border: `1.5px solid ${token.colorBorder}`,
        borderRadius: 8,
        overflow: 'hidden'
      }}
    >
      {}
      <div
        style={{
          background: token.colorFillQuaternary,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          padding: '8px 12px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 500 }}>U 位布局</span>
        <span style={{ fontSize: 11, color: token.colorTextSecondary }}>
          {totalU}U · {deviceCount} 台{!readOnly && ' · 可拖拽'}
        </span>
      </div>

      {}
      <div style={{ padding: 6 }}>
        <div
          ref={bodyRef}
          onDragOver={onSlotDragOver}
          onDragLeave={clearHighlight}
          onDrop={onSlotDrop}
          onDragEnd={onDragEnd}
          style={{ position: 'relative', height: totalH, userSelect: 'none' }}
        >
          {}
          {Array.from({ length: totalU }, (_, i) => i + 1).map((u) => {
            const isHl = highlightUs.includes(u);
            const isOccupied = occupiedSet.has(u);
            return (
              <div
                key={u}
                style={{
                  position: 'absolute',
                  top: uToTop(u, layout.unit),
                  left: 0,
                  right: 0,
                  height: layout.rowH,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4
                }}
              >
                {}
                <span
                  style={{
                    width: layout.uNumW,
                    textAlign: 'right',
                    fontSize: layout.uNumFontSize,
                    color: token.colorTextTertiary,
                    fontVariantNumeric: 'tabular-nums',
                    flexShrink: 0
                  }}
                >
                  {displayLabel(u, totalU)}
                </span>
                {}
                {!isOccupied && (
                  <div
                    style={{
                      flex: 1,
                      height: layout.rowH,
                      borderRadius: 3,
                      border: isHl
                        ? '1.5px dashed #378ADD'
                        : `1px dashed ${token.colorBorderSecondary}`,
                      background: isHl ? 'rgba(55,138,221,0.08)' : 'transparent',
                      transition: 'background 0.1s, border-color 0.1s'
                    }}
                  />
                )}
              </div>
            );
          })}

          {}
          {devices.map((device) => (
            <DeviceBlock
              key={device.deviceId}
              device={device}
              totalU={totalU}
              readOnly={readOnly}
              isSelected={selectedId === device.deviceId}
              isCollapsed={!!collapsed[device.deviceId]}
              layout={layout}
              onSelect={() => onSelect(device.deviceId)}
              onToggleCollapse={() => onToggleCollapse(device.deviceId)}
              onDragStart={onDragStart}
              onNodeReorder={onNodeReorder}
            />
          ))}
        </div>
      </div>

      {}
      <div
        style={{
          padding: '6px 10px',
          borderTop: `1px solid ${token.colorBorderSecondary}`,
          display: 'flex',
          gap: 14
        }}
      >
        {[
          { label: 'U位', val: `${usedU}/${totalU}` },
          { label: '功率', val: `${usedP}W` },
          { label: '设备', val: `${deviceCount}台` }
        ].map(({ label, val }) => (
          <span key={label} style={{ fontSize: 11, color: token.colorTextSecondary }}>
            {label} <strong style={{ color: token.colorText, fontWeight: 500 }}>{val}</strong>
          </span>
        ))}
      </div>
    </div>
  );
};

export default RackBody;
