/**
 * 机房平面图组件
 *
 * 【展示组件】纯 Props 驱动，不内部获取数据，不直接订阅 Store。
 * - 以二维网格展示机柜在机房中的物理布局
 * - 机柜色块按状态着色，显示编号和U位利用率
 * - 点击机柜跳转到机柜详情页
 */
import React, { useMemo, useCallback } from 'react';
import { Tooltip, Progress, Empty, theme } from 'antd';
import { useNavigate } from 'react-router-dom';
import { CABINET_STATUS_MAP } from '@/types/enums';
import type { Cabinet } from '@/types/models';

interface RoomLayoutProps {
  
  cabinets: Cabinet[];
  
  readOnly?: boolean;
}


interface CabinetCell {
  cabinet: Cabinet;
  row: number;
  col: number;
}


function extractRowPrefix(cabinetNumber: string): string {
  const match = cabinetNumber.match(/^[A-Za-z]+/);
  return match ? match[0].toUpperCase() : '';
}


const STATUS_BG_COLORS: Record<number, string> = {
  0: '#ff4d4f', 
  1: '#52c41a', 
  2: '#1677ff', 
  3: '#fa8c16', 
  4: '#722ed1', 
};


const STATUS_BORDER_COLORS: Record<number, string> = {
  0: '#cf1322',
  1: '#389e0d',
  2: '#0958d9',
  3: '#d46b08',
  4: '#531dab',
};

function RoomLayout({ cabinets, readOnly = false }: RoomLayoutProps) {
  const navigate = useNavigate();
  const { token } = theme.useToken();

  
  const { maxRow, maxCol, grid, rowLabels } = useMemo(() => {
    const positioned = cabinets.filter(
      (c) => c.row != null && c.col != null && c.row > 0 && c.col > 0,
    );

    if (positioned.length === 0) {
      return { maxRow: 0, maxCol: 0, grid: [], rowLabels: [] };
    }

    const maxRow = Math.max(...positioned.map((c) => c.row!));
    const maxCol = Math.max(...positioned.map((c) => c.col!));

    const cellMap = new Map<string, CabinetCell>();
    for (const c of positioned) {
      cellMap.set(`${c.row},${c.col}`, { cabinet: c, row: c.row!, col: c.col! });
    }

    const grid: (CabinetCell | null)[][] = [];
    for (let r = 1; r <= maxRow; r++) {
      const row: (CabinetCell | null)[] = [];
      for (let c = 1; c <= maxCol; c++) {
        row.push(cellMap.get(`${r},${c}`) ?? null);
      }
      grid.push(row);
    }

    
    const rowLabels: string[] = [];
    for (let r = 1; r <= maxRow; r++) {
      const prefixCounts = new Map<string, number>();
      for (let c = 1; c <= maxCol; c++) {
        const cell = cellMap.get(`${r},${c}`);
        if (cell) {
          const prefix = extractRowPrefix(cell.cabinet.cabinet_number);
          if (prefix) {
            prefixCounts.set(prefix, (prefixCounts.get(prefix) ?? 0) + 1);
          }
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

    return { maxRow, maxCol, grid, rowLabels };
  }, [cabinets]);

  
  const handleClick = useCallback(
    (cabinetId: number) => {
      if (readOnly) return;
      navigate(`/cabinets/${cabinetId}`);
    },
    [navigate, readOnly],
  );

  
  const renderCell = (cell: CabinetCell | null, rowIdx: number, colIdx: number) => {
    if (!cell) {
      return (
        <div
          style={{
            width: 120,
            height: 96,
            border: `1px dashed ${token.colorBorderSecondary}`,
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: token.colorTextQuaternary,
            fontSize: 12,
          }}
        >
          空
        </div>
      );
    }

    const { cabinet } = cell;
    const status = cabinet.status ?? 1;
    const bgColor = STATUS_BG_COLORS[status] || '#1677ff';
    const borderColor = STATUS_BORDER_COLORS[status] || '#0958d9';
    const statusInfo = CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP];
    const uUsageRate = cabinet.u_usage_rate ?? 0;
    const powerUsageRate = cabinet.power_usage_rate ?? 0;

    const cellContent = (
      <div
        onClick={() => handleClick(cabinet.id)}
        style={{
          width: 120,
          height: 96,
          backgroundColor: `${bgColor}15`,
          border: `2px solid ${borderColor}`,
          borderRadius: 6,
          padding: '6px 8px',
          cursor: readOnly ? 'default' : 'pointer',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          transition: 'all 0.2s ease',
          position: 'relative',
          overflow: 'hidden',
        }}
        onMouseEnter={(e) => {
          if (!readOnly) {
            (e.currentTarget as HTMLDivElement).style.transform = 'scale(1.03)';
            (e.currentTarget as HTMLDivElement).style.boxShadow = `0 2px 8px ${bgColor}40`;
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
            backgroundColor: bgColor,
            borderRadius: '6px 6px 0 0',
          }}
        />
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: token.colorText,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {cabinet.cabinet_number}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Progress
            percent={uUsageRate}
            size="small"
            showInfo={false}
            strokeColor={uUsageRate > 80 ? '#ff4d4f' : bgColor}
            railColor="#f0f0f0"
            style={{ flex: 1, margin: 0 }}
          />
          <span style={{ fontSize: 11, color: token.colorTextSecondary, minWidth: 32, textAlign: 'right' }}>
            {uUsageRate}%
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: token.colorTextSecondary }}>
            {cabinet.device_count ?? 0}台
          </span>
          <span style={{ fontSize: 10, color: bgColor, fontWeight: 500 }}>
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
              textOverflow: 'ellipsis',
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
            <div><strong>{cabinet.cabinet_number}</strong></div>
            <div>状态：{statusInfo?.label ?? status}</div>
            <div>U位：{cabinet.used_u ?? 0}/{cabinet.total_u ?? 42}U ({uUsageRate}%)</div>
            {cabinet.total_power ? (
              <div>功率：{cabinet.used_power ?? 0}/{cabinet.total_power}W ({powerUsageRate}%)</div>
            ) : null}
            <div>设备：{cabinet.device_count ?? 0}台</div>
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

  const unpositionedCabinets = cabinets.filter(
    (c) => c.row == null || c.col == null,
  );

  if (cabinets.length === 0) {
    return <Empty description="该机房暂无机柜" />;
  }

  return (
    <div>
      {maxRow > 0 && maxCol > 0 ? (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 4, paddingLeft: 56 }}>
            {Array.from({ length: maxCol }, (_, i) => (
              <div
                key={`col-header-${i}`}
                style={{
                  width: 120,
                  textAlign: 'center',
                  fontSize: 12,
                  color: token.colorTextSecondary,
                  fontWeight: 500,
                }}
              >
                列{i + 1}
              </div>
            ))}
          </div>
          {grid.map((row, rowIdx) => (
            <div
              key={`row-${rowIdx}`}
              style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}
            >
              <div
                style={{
                  width: 48,
                  textAlign: 'center',
                  fontSize: 12,
                  color: token.colorTextSecondary,
                  fontWeight: 500,
                  flexShrink: 0,
                }}
              >
                {rowLabels[rowIdx] ? `${rowLabels[rowIdx]}(${rowIdx + 1})` : `行${rowIdx + 1}`}
              </div>
              {row.map((cell, colIdx) => (
                <React.Fragment key={cell ? `cabinet-${cell.cabinet.id}` : `empty-${rowIdx}-${colIdx}`}>
                  {renderCell(cell, rowIdx, colIdx)}
                </React.Fragment>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <Empty description="暂无机柜位置信息，请在机柜表单中设置行号和列号" />
      )}
      {unpositionedCabinets.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, color: token.colorTextSecondary, marginBottom: 8 }}>
            未设置位置的机柜（{unpositionedCabinets.length}个）
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {unpositionedCabinets.map((c) => {
              const status = c.status ?? 1;
              const bgColor = STATUS_BG_COLORS[status] || '#1677ff';
              return (
                <Tooltip
                  key={c.id}
                  title={`${c.cabinet_number} - ${CABINET_STATUS_MAP[status as keyof typeof CABINET_STATUS_MAP]?.label ?? ''}`}
                >
                  <div
                    onClick={() => handleClick(c.id)}
                    style={{
                      padding: '4px 12px',
                      backgroundColor: `${bgColor}10`,
                      border: `1px solid ${bgColor}`,
                      borderRadius: 4,
                      fontSize: 12,
                      cursor: readOnly ? 'default' : 'pointer',
                      color: token.colorText,
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
