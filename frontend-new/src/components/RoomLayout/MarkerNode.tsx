import React from 'react';
import { Tooltip } from 'antd';
import type { GlobalToken } from 'antd';
import {
  AppstoreOutlined,
  BorderOutlined,
  CloudOutlined,
  LoginOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import type { RoomLayoutMarker } from '@/types/models';
import { MARKER_TYPE_LABEL, positionLabel } from './palette';

const MARKER_ICON: Record<string, React.ReactNode> = {
  ac: <CloudOutlined />,
  pdu: <ThunderboltOutlined />,
  pillar: <BorderOutlined />,
  door: <LoginOutlined />,
  other: <AppstoreOutlined />
};

export interface MarkerNodeProps {
  marker: RoomLayoutMarker;
  token: GlobalToken;
  left: number;
  top: number;
  cellWidth: number;
  cellHeight: number;
  selected: boolean;
  onSelect: (markerId: number) => void;
}

function MarkerNode({
  marker,
  token,
  left,
  top,
  cellWidth,
  cellHeight,
  selected,
  onSelect
}: MarkerNodeProps) {
  const typeLabel = MARKER_TYPE_LABEL[marker.marker_type] ?? marker.marker_type;
  const name = marker.label || typeLabel;
  const showTypeText = cellWidth >= 96;

  const tooltip = (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600 }}>{name}</div>
      <div>类型：{typeLabel}</div>
      <div>位置：{positionLabel(marker.row_number, marker.col_number)}</div>
      {marker.notes ? <div>备注：{marker.notes}</div> : null}
    </div>
  );

  return (
    <Tooltip title={tooltip}>
      <div
        role="button"
        tabIndex={0}
        data-marker-id={marker.id}
        onClick={() => onSelect(marker.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(marker.id);
          }
        }}
        style={{
          position: 'absolute',
          left,
          top,
          width: cellWidth,
          height: cellHeight,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          borderRadius: 4,
          background: token.colorFillSecondary,
          border: `1px dashed ${selected ? token.colorPrimary : token.colorBorder}`,
          outline: selected ? `2px solid ${token.colorPrimary}` : undefined,
          outlineOffset: -2,
          color: token.colorTextSecondary,
          fontSize: 11,
          lineHeight: 1.2,
          cursor: 'pointer',
          userSelect: 'none'
        }}
      >
        <span style={{ fontSize: 16 }}>{MARKER_ICON[marker.marker_type] ?? MARKER_ICON.other}</span>
        {showTypeText ? <span>{typeLabel}</span> : null}
      </div>
    </Tooltip>
  );
}

export default React.memo(MarkerNode);
