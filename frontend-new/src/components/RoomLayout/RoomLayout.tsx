import React, { useMemo, useCallback } from 'react';
import { Tooltip, Progress, Empty, theme } from 'antd';
import type { GlobalToken } from 'antd';
import { useNavigate } from 'react-router-dom';
import { CABINET_STATUS_MAP, CabinetStatusCode } from '@/types/enums';
import type { Cabinet } from '@/types/models';

interface RoomLayoutProps {
  cabinets: Cabinet[];
  readOnly?: boolean;
}

const CELL_WIDTH = 120;
const CELL_HEIGHT = 96;
const GRID_GAP = 8;
const ROW_HEADER_WIDTH = 48;
const COL_HEADER_HEIGHT = 24;

type StatusPaletteKey = 'red' | 'green' | 'blue' | 'orange' | 'purple';

interface StatusPalette {
  bg: string;
  accent: string;
  border: string;
  text: string;
}

const DEFAULT_STATUS = CabinetStatusCode.AVAILABLE;

const STATUS_PALETTE_KEYS: Record<number, StatusPaletteKey> = {
  [CabinetStatusCode.DISABLED]: 'red',
  [CabinetStatusCode.AVAILABLE]: 'green',
  [CabinetStatusCode.IN_USE]: 'blue',
  [CabinetStatusCode.MAINTENANCE]: 'orange',
  [CabinetStatusCode.RESERVED]: 'purple'
};

function getStatusPalette(token: GlobalToken, status: number): StatusPalette {
  const key = STATUS_PALETTE_KEYS[status] ?? 'blue';
  return {
    bg: token[`${key}1`],
    accent: token[`${key}5`],
    border: token[`${key}6`],
    text: token[`${key}7`]
  };
}

function extractRowPrefix(cabinetNumber: string): string {
  const match = cabinetNumber.match(/^[A-Za-z]+/);
  return match ? match[0].toUpperCase() : '';
}

function isPositioned(cabinet: Cabinet): boolean {
  return cabinet.row != null && cabinet.col != null && cabinet.row > 0 && cabinet.col > 0;
}

function RoomLayout({ cabinets, readOnly = false }: RoomLayoutProps) {
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const { maxRow, maxCol, positioned, unpositioned, rowLabels } = useMemo(() => {
    const cellMap = new Map<string, Cabinet>();
    for (const c of cabinets) {
      if (isPositioned(c)) {
        cellMap.set(`${c.row},${c.col}`, c);
      }
    }
    const positioned = [...cellMap.values()];
    const unpositioned = cabinets.filter((c) => !isPositioned(c));

    const maxRow = positioned.length ? Math.max(...positioned.map((c) => c.row!)) : 0;
    const maxCol = positioned.length ? Math.max(...positioned.map((c) => c.col!)) : 0;

    const rowLabels: string[] = [];
    for (let r = 1; r <= maxRow; r++) {
      const prefixCounts = new Map<string, number>();
      for (const c of positioned) {
        if (c.row !== r) continue;
        const prefix = extractRowPrefix(c.cabinet_number);
        if (prefix) {
          prefixCounts.set(prefix, (prefixCounts.get(prefix) ?? 0) + 1);
        }
      }
      let bestPrefix = '';
      let bestCount = 0;
      prefixCounts.forEach((count, prefix) => {
        if (count > bestCount) {
          bestCount = count;
          bestPrefix = prefix;
        }
      });
      rowLabels.push(bestPrefix);
    }

    return { maxRow, maxCol, positioned, unpositioned, rowLabels };
  }, [cabinets]);

  const legendStatuses = useMemo(
    () => [...new Set(cabinets.map((c) => c.status ?? DEFAULT_STATUS))].sort((a, b) => a - b),
    [cabinets]
  );

  const handleClick = useCallback(
    (cabinetId: number) => {
      if (readOnly) return;
      navigate(`/cabinets/${cabinetId}`);
    },
    [navigate, readOnly]
  );

  const renderCell = (cabinet: Cabinet) => {
    const status = cabinet.status ?? DEFAULT_STATUS;
    const palette = getStatusPalette(token, status);
    const statusInfo = CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP];
    const uUsageRate = cabinet.u_usage_rate ?? 0;
    const powerUsageRate = cabinet.power_usage_rate ?? 0;

    const cellContent = (
      <div
        onClick={() => handleClick(cabinet.id)}
        style={{
          width: CELL_WIDTH,
          height: CELL_HEIGHT,
          boxSizing: 'border-box',
          backgroundColor: palette.bg,
          border: `2px solid ${palette.border}`,
          borderRadius: 6,
          padding: '6px 8px',
          cursor: readOnly ? 'default' : 'pointer',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          transition: 'all 0.2s ease',
          position: 'relative',
          overflow: 'hidden'
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
            style={{ flex: 1, margin: 0 }}
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
        {cabinet.customer_name && (
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
        )}
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
            <div>
              位置：第{cabinet.row}行 第{cabinet.col}列
            </div>
            {cabinet.customer_name ? <div>客户：{cabinet.customer_name}</div> : null}
            {cabinet.notes ? <div>备注：{cabinet.notes}</div> : null}
          </div>
        }
        placement="top"
      >
        {cellContent}
      </Tooltip>
    );
  };

  if (cabinets.length === 0) {
    return <Empty description="该机房暂无机柜" />;
  }

  /*
   * 无定位机柜时只把网格降级为空态提示，**不可改为提前 return**：
   * 下方「未设置位置的机柜」列表必须始终渲染，否则全部机柜都未定位时
   * 会连列表一起消失，用户看不到任何机柜（回归见 RoomLayout.test.tsx）。
   */
  return (
    <div>
      {legendStatuses.length > 0 && (
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
          {legendStatuses.map((status) => {
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
      )}

      {maxRow > 0 && maxCol > 0 ? (
        <div style={{ overflowX: 'auto', paddingBottom: 8 }}>
          <div
            style={{
              display: 'inline-grid',
              gridTemplateColumns: `${ROW_HEADER_WIDTH}px auto`,
              gridTemplateRows: `${COL_HEADER_HEIGHT}px auto`,
              gap: GRID_GAP,
              alignItems: 'center'
            }}
          >
            {/* 列头：线性量级，承担坐标参照 */}
            <div
              style={{
                gridColumn: 2,
                gridRow: 1,
                display: 'grid',
                gridTemplateColumns: `repeat(${maxCol}, ${CELL_WIDTH}px)`,
                gap: GRID_GAP
              }}
            >
              {Array.from({ length: maxCol }, (_, i) => (
                <div
                  key={`col-header-${i}`}
                  style={{
                    textAlign: 'center',
                    fontSize: 12,
                    color: token.colorTextSecondary,
                    fontWeight: 500
                  }}
                >
                  列{i + 1}
                </div>
              ))}
            </div>

            {/* 行头：线性量级，括号内为物理行号 */}
            <div
              style={{
                gridColumn: 1,
                gridRow: 2,
                display: 'grid',
                gridTemplateRows: `repeat(${maxRow}, ${CELL_HEIGHT}px)`,
                gap: GRID_GAP
              }}
            >
              {Array.from({ length: maxRow }, (_, i) => (
                <div
                  key={`row-header-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: token.colorTextSecondary,
                    fontWeight: 500
                  }}
                >
                  {rowLabels[i] ? `${rowLabels[i]}(${i + 1})` : `行${i + 1}`}
                </div>
              ))}
            </div>

            {/*
            平面主体：只为有机柜的格子建 DOM，空位由容器背景网格线表达。
            网格线画在间隙正中（cell + gap/2），避开不透明机柜色块下方，
            否则线会被色块盖住而不可见。
          */}
            <div
              data-testid="room-layout-grid"
              style={{
                gridColumn: 2,
                gridRow: 2,
                display: 'grid',
                gridTemplateColumns: `repeat(${maxCol}, ${CELL_WIDTH}px)`,
                gridTemplateRows: `repeat(${maxRow}, ${CELL_HEIGHT}px)`,
                gap: GRID_GAP,
                width: maxCol * (CELL_WIDTH + GRID_GAP) - GRID_GAP,
                height: maxRow * (CELL_HEIGHT + GRID_GAP) - GRID_GAP,
                backgroundImage: `linear-gradient(to right, ${token.colorBorderSecondary} 1px, transparent 1px), linear-gradient(to bottom, ${token.colorBorderSecondary} 1px, transparent 1px)`,
                backgroundSize: `${CELL_WIDTH + GRID_GAP}px ${CELL_HEIGHT + GRID_GAP}px`,
                backgroundPosition: `${CELL_WIDTH + GRID_GAP / 2}px ${CELL_HEIGHT + GRID_GAP / 2}px`
              }}
            >
              {positioned.map((cabinet) => (
                <div key={cabinet.id} style={{ gridColumn: cabinet.col!, gridRow: cabinet.row! }}>
                  {renderCell(cabinet)}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <Empty description="暂无机柜位置信息，请在机柜表单中设置行号和列号" />
      )}

      {unpositioned.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, color: token.colorTextSecondary, marginBottom: 8 }}>
            未设置位置的机柜（{unpositioned.length}个）
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {unpositioned.map((c) => {
              const status = c.status ?? DEFAULT_STATUS;
              const palette = getStatusPalette(token, status);
              return (
                <Tooltip
                  key={c.id}
                  title={`${c.cabinet_number} - ${
                    CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP]?.label ?? ''
                  }`}
                >
                  <div
                    onClick={() => handleClick(c.id)}
                    style={{
                      padding: '4px 12px',
                      backgroundColor: palette.bg,
                      border: `1px solid ${palette.border}`,
                      borderRadius: 4,
                      fontSize: 12,
                      cursor: readOnly ? 'default' : 'pointer',
                      color: token.colorText
                    }}
                  >
                    {c.cabinet_number}
                  </div>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default RoomLayout;
