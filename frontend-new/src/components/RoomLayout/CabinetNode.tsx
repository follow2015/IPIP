import React from 'react';
import { Tooltip, Progress } from 'antd';
import type { GlobalToken } from 'antd';
import { CABINET_STATUS_MAP } from '@/types/enums';
import type { Cabinet } from '@/types/models';
import { DEFAULT_STATUS, getStatusPalette } from './palette';
import { isPositioned } from './geometry';

export interface CabinetNodeProps {
  cabinet: Cabinet;
  token: GlobalToken;
  left: number;
  top: number;
  cellWidth: number;
  cellHeight: number;
  showCustomer: boolean;
  dimmed: boolean;
  highlighted: boolean;
  selected: boolean;
  readOnly: boolean;
  onSelect: (cabinetId: number) => void;
  onOpen: (cabinetId: number) => void;
}

function CabinetNode({
  cabinet,
  token,
  left,
  top,
  cellWidth,
  cellHeight,
  showCustomer,
  dimmed,
  highlighted,
  selected,
  readOnly,
  onSelect,
  onOpen
}: CabinetNodeProps) {
  const status = cabinet.status ?? DEFAULT_STATUS;
  const palette = getStatusPalette(token, status);
  const statusInfo = CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP];
  const uUsageRate = cabinet.u_usage_rate ?? 0;
  const powerUsageRate = cabinet.power_usage_rate ?? 0;

  const cell = (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={() => onSelect(cabinet.id)}
      onDoubleClick={() => onOpen(cabinet.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(cabinet.id);
        }
      }}
      style={{
        position: 'absolute',
        left,
        top,
        width: cellWidth,
        height: cellHeight,
        boxSizing: 'border-box',
        backgroundColor: palette.bg,
        border: `2px solid ${palette.border}`,
        borderRadius: 6,
        padding: '6px 8px',
        cursor: readOnly ? 'default' : 'pointer',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        transition: 'box-shadow 0.15s ease, transform 0.15s ease',
        overflow: 'hidden',
        opacity: dimmed ? 0.25 : 1,
        outline: selected
          ? `2px solid ${token.colorPrimary}`
          : highlighted
            ? `2px solid ${token.colorWarning}`
            : undefined,
        outlineOffset: 2
      }}
      onMouseEnter={(e) => {
        if (!readOnly) {
          (e.currentTarget as HTMLDivElement).style.transform = 'scale(1.03)';
          (e.currentTarget as HTMLDivElement).style.boxShadow = token.boxShadowSecondary;
        }
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          backgroundColor: palette.accent,
          borderRadius: '6px 6px 0 0'
        }}
      />
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: token.colorText,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        }}
      >
        {cabinet.cabinet_number}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Progress
          percent={uUsageRate}
          size="small"
          showInfo={false}
          strokeColor={uUsageRate > 80 ? token.colorError : palette.accent}
          railColor={token.colorFillSecondary}
          style={{ flex: 1, margin: 0, minWidth: 0 }}
        />
        <span
          style={{
            fontSize: 11,
            color: token.colorTextSecondary,
            minWidth: 32,
            textAlign: 'right'
          }}
        >
          {uUsageRate}%
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: token.colorTextSecondary }}>
          {cabinet.device_count ?? 0}台
        </span>
        <span style={{ fontSize: 10, color: palette.text, fontWeight: 500 }}>
          {statusInfo?.label ?? ''}
        </span>
      </div>
      {showCustomer && cabinet.customer_name ? (
        <div
          style={{
            fontSize: 10,
            color: token.colorTextSecondary,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}
        >
          {cabinet.customer_name}
        </div>
      ) : null}
    </div>
  );

  return (
    <Tooltip
      title={
        <div style={{ fontSize: 12, lineHeight: 1.8 }}>
          <div>
            <strong>{cabinet.cabinet_number}</strong>
          </div>
          <div>状态：{statusInfo?.label ?? status}</div>
          <div>
            U位：{cabinet.used_u ?? 0}/{cabinet.total_u ?? 42}U ({uUsageRate}%)
          </div>
          {cabinet.total_power ? (
            <div>
              功率：{cabinet.used_power ?? 0}/{cabinet.total_power}W ({powerUsageRate}%)
            </div>
          ) : null}
          <div>设备：{cabinet.device_count ?? 0}台</div>
          {isPositioned(cabinet) ? (
            <div>
              位置：第{cabinet.row}行 第{cabinet.col}列
            </div>
          ) : (
            <div>位置：未定位</div>
          )}
          {cabinet.customer_name ? <div>客户：{cabinet.customer_name}</div> : null}
          {cabinet.notes ? <div>备注：{cabinet.notes}</div> : null}
        </div>
      }
      placement="top"
    >
      {cell}
    </Tooltip>
  );
}

export default React.memo(CabinetNode);
