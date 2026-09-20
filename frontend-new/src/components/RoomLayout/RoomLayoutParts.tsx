import React from 'react';
import { Tag, Tooltip } from 'antd';
import type { GlobalToken } from 'antd';
import { WarningFilled } from '@ant-design/icons';
import type { Cabinet } from '@/types/models';
import { CABINET_STATUS_MAP } from '@/types/enums';
import {
  CHANNEL_TYPE_LABEL,
  DEFAULT_STATUS,
  getStatusPalette,
  paletteKeyOf,
  positionLabel
} from './palette';

export function StatusLegend({ statuses, token }: { statuses: number[]; token: GlobalToken }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 12,
        marginBottom: 12
      }}
    >
      <span style={{ fontSize: 12, color: token.colorTextTertiary }}>状态</span>
      {statuses.map((status) => {
        const palette = getStatusPalette(token, status);
        const info = CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP];
        return (
          <span
            key={status}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              color: token.colorTextSecondary
            }}
          >
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: 3,
                backgroundColor: palette.bg,
                border: `1px solid ${palette.border}`,
                display: 'inline-block'
              }}
            />
            {info?.label ?? status}
          </span>
        );
      })}
    </div>
  );
}

export function ChannelLegend({ token }: { token: GlobalToken }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 12,
        marginBottom: 12
      }}
    >
      <span style={{ fontSize: 12, color: token.colorTextTertiary }}>通道</span>
      {(['cold', 'hot', 'mixed'] as const).map((type) => {
        const key = paletteKeyOf(type);
        return (
          <span
            key={type}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              color: token.colorTextSecondary
            }}
          >
            <span
              style={{
                width: 8,
                height: 14,
                borderRadius: 2,
                backgroundColor: token[`${key}1`],
                border: `1px solid ${token[`${key}6`]}`
              }}
            />
            {CHANNEL_TYPE_LABEL[type]}
          </span>
        );
      })}
      <span style={{ fontSize: 12, color: token.colorTextTertiary }}>
        （实线+封头 = 封闭，虚线 = 开放）
      </span>
    </div>
  );
}

export function DuplicatedCabinetList({
  cabinets,
  readOnly,
  onOpen,
  token
}: {
  cabinets: Cabinet[];
  readOnly: boolean;
  onOpen: (cabinetId: number) => void;
  token: GlobalToken;
}) {
  if (cabinets.length === 0) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, color: token.colorWarning, marginBottom: 8 }}>
        位置冲突的机柜（{cabinets.length}个）：与同机房其它机柜填了相同的行列号，
        未在平面图上显示，请修正行列号
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {cabinets.map((c) => (
          <Tooltip
            key={c.id}
            title={`${c.cabinet_number}（${positionLabel(c.row ?? 0, c.col ?? 0)}）与图上机柜位置重复${
              readOnly ? '' : '，点击查看详情'
            }`}
          >
            <Tag
              icon={<WarningFilled />}
              color="warning"
              style={{ cursor: readOnly ? 'default' : 'pointer', marginInlineEnd: 0 }}
              onClick={() => {
                if (!readOnly) onOpen(c.id);
              }}
            >
              {c.cabinet_number}
            </Tag>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

export function UnpositionedCabinetList({
  cabinets,
  matchedIds,
  selectedId,
  readOnly,
  token,
  onSelect,
  onOpen
}: {
  cabinets: Cabinet[];
  matchedIds: Set<number> | null;
  selectedId: number | null;
  readOnly: boolean;
  token: GlobalToken;
  onSelect: (cabinetId: number) => void;
  onOpen: (cabinetId: number) => void;
}) {
  if (cabinets.length === 0) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, color: token.colorTextSecondary, marginBottom: 8 }}>
        未设置位置的机柜（{cabinets.length}个）
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {cabinets.map((c) => {
          const status = c.status ?? DEFAULT_STATUS;
          const palette = getStatusPalette(token, status);
          const dimmed = matchedIds != null && !matchedIds.has(c.id);
          const selected = selectedId === c.id;
          return (
            <Tooltip
              key={c.id}
              title={`${c.cabinet_number} - ${
                CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP]?.label ?? ''
              }`}
            >
              <div
                role="button"
                tabIndex={0}
                onClick={() => onSelect(c.id)}
                onDoubleClick={() => onOpen(c.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(c.id);
                  }
                }}
                style={{
                  padding: '4px 12px',
                  backgroundColor: palette.bg,
                  border: `1px solid ${palette.border}`,
                  borderRadius: 4,
                  fontSize: 12,
                  cursor: readOnly ? 'default' : 'pointer',
                  color: token.colorText,
                  opacity: dimmed ? 0.25 : 1,
                  outline: selected ? `2px solid ${token.colorPrimary}` : undefined,
                  outlineOffset: 2
                }}
              >
                {c.cabinet_number}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}
