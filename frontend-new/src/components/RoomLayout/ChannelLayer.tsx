import React from 'react';
import type { GlobalToken } from 'antd';
import type { RoomChannel } from '@/types/models';
import { bandLeft, gridHeight, gridWidth, BAND_WIDTH_RATIO } from './geometry';
import { CHANNEL_TYPE_LABEL, SUPPLY_LABEL, paletteKeyOf } from './palette';

export interface ChannelLayerProps {
  channels: RoomChannel[];
  rows: number;
  cols: number;
  cellWidth: number;
  cellHeight: number;
  gap: number;
  token: GlobalToken;
  colOffset?: number;
}

function ChannelLayer({
  channels,
  rows,
  cols,
  cellWidth,
  cellHeight,
  gap,
  token,
  colOffset = 0
}: ChannelLayerProps) {
  if (channels.length === 0 || rows <= 0 || cols <= 0) return null;

  const width = gridWidth(cols, cellWidth, gap);
  const height = gridHeight(rows, cellHeight, gap);
  const bandWidth = Math.max(6, Math.round(cellWidth * BAND_WIDTH_RATIO));

  return (
    <svg
      data-testid="room-layout-channels"
      width={width}
      height={height}
      style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}
    >
      {channels.map((channel) => {
        const key = paletteKeyOf(channel.channel_type);
        const fill = token[`${key}1`];
        const stroke = token[`${key}6`];
        const x = bandLeft(channel.col_number - colOffset, cellWidth, gap, bandWidth);
        const typeLabel = CHANNEL_TYPE_LABEL[channel.channel_type] ?? channel.channel_type;
        const name = channel.label ?? channel.display_name ?? '';

        return (
          <g key={channel.id}>
            <title>
              {`${name} ${typeLabel}`.trim()}
              {channel.enclosed ? '（封闭）' : '（开放）'}
              {channel.supply ? ` · ${SUPPLY_LABEL[channel.supply] ?? channel.supply}` : ''}
            </title>
            <rect
              x={x}
              y={0}
              width={bandWidth}
              height={height}
              rx={3}
              fill={fill}
              stroke={stroke}
              strokeWidth={1.5}
              strokeDasharray={channel.enclosed ? undefined : '5 3'}
              opacity={0.9}
            />
            {channel.enclosed ? (
              <>
                {/* 封头：表达端门 / 顶封板 */}
                <line x1={x} y1={0} x2={x + bandWidth} y2={0} stroke={stroke} strokeWidth={3} />
                <line
                  x1={x}
                  y1={height}
                  x2={x + bandWidth}
                  y2={height}
                  stroke={stroke}
                  strokeWidth={3}
                />
              </>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

export default React.memo(ChannelLayer);
