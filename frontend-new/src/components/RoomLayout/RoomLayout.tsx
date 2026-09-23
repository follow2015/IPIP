import React, { useMemo, useCallback, useEffect, useRef, useState } from 'react';
import { Tooltip, Empty, Input, Segmented, Button, Space, theme } from 'antd';
import {
  SearchOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  ExpandOutlined,
  WarningFilled
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getCabinetStatusMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Cabinet } from '@/types/models';
import CabinetNode from './CabinetNode';
import ChannelLayer from './ChannelLayer';
import MarkerNode from './MarkerNode';
import {
  ChannelLegend,
  DuplicatedCabinetList,
  StatusLegend,
  UnpositionedCabinetList
} from './RoomLayoutParts';
import { DEFAULT_STATUS, MARKER_TYPE_LABEL_KEYS } from './palette';
import {
  cellLeft,
  cellTop,
  gridBounds,
  gridHeight,
  gridWidth,
  groupCabinetsByCell,
  isMarkerPositioned,
  isPositioned
} from './geometry';
import type { RoomChannel, RoomLayoutMarker } from '@/types/models';
import { clampScale, scrollForZoom, toScaleTransform } from './view-transform';

interface RoomLayoutProps {
  cabinets: Cabinet[];
  channels?: RoomChannel[];
  markers?: RoomLayoutMarker[];
  highlightCabinetIds?: number[];
  readOnly?: boolean;
}

const ROW_HEADER_WIDTH = 48;
const COL_HEADER_HEIGHT = 24;

type DensityKey = 'compact' | 'standard' | 'large';

type DensityLabelKey =
  | 'roomLayout.density.compact'
  | 'roomLayout.density.standard'
  | 'roomLayout.density.large';

interface DensityConfig {
  labelKey: DensityLabelKey;
  cellWidth: number;
  cellHeight: number;
  gap: number;
  showCustomer: boolean;
}

const DENSITY_CONFIG: Record<DensityKey, DensityConfig> = {
  compact: { labelKey: 'roomLayout.density.compact', cellWidth: 88, cellHeight: 72, gap: 6, showCustomer: false },
  standard: { labelKey: 'roomLayout.density.standard', cellWidth: 120, cellHeight: 96, gap: 8, showCustomer: true },
  large: { labelKey: 'roomLayout.density.large', cellWidth: 156, cellHeight: 124, gap: 10, showCustomer: true }
};

const DENSITY_KEYS = Object.keys(DENSITY_CONFIG) as DensityKey[];

function extractCabinetPrefix(cabinetNumber: string): string {
  const match = cabinetNumber.match(/^[A-Za-z]+/);
  return match ? match[0].toUpperCase() : '';
}

const NO_CHANNELS: RoomChannel[] = [];
const NO_MARKERS: RoomLayoutMarker[] = [];

function RoomLayout({
  cabinets,
  channels = NO_CHANNELS,
  markers = NO_MARKERS,
  highlightCabinetIds,
  readOnly = false
}: RoomLayoutProps) {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { t } = useTranslation('asset');
  const { t: tDevice } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');

  const [density, setDensity] = useState<DensityKey>('standard');
  const [keyword, setKeyword] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedMarkerId, setSelectedMarkerId] = useState<number | null>(null);

  const { cellWidth, cellHeight, gap, showCustomer } = DENSITY_CONFIG[density];

  const bounds = useMemo(() => gridBounds(cabinets, markers), [cabinets, markers]);
  const { minRow, minCol, maxCol, rows, cols } = bounds;
  const rowOffset = minRow - 1;
  const colOffset = minCol - 1;

  const { positioned, unpositioned, duplicatedCabinets, colLabels } = useMemo(() => {
    const positioned: Cabinet[] = [];
    const duplicatedCabinets: Cabinet[] = [];
    groupCabinetsByCell(cabinets).forEach((list) => {
      const sorted = [...list].sort((a, b) => a.id - b.id);
      positioned.push(sorted[0]);
      duplicatedCabinets.push(...sorted.slice(1));
    });

    const unpositioned = cabinets.filter((c) => !isPositioned(c));

    const prefixCountsByCol = new Map<number, Map<string, number>>();
    for (const cab of positioned) {
      if (cab.col == null) continue; // 未定位机柜不参与列头（防御，isPositioned 已滤）
      const prefix = extractCabinetPrefix(cab.cabinet_number);
      if (!prefix) continue;
      let counts = prefixCountsByCol.get(cab.col);
      if (!counts) {
        counts = new Map();
        prefixCountsByCol.set(cab.col, counts);
      }
      counts.set(prefix, (counts.get(prefix) ?? 0) + 1);
    }

    const colLabels: string[] = [];
    for (let c = minCol; c <= maxCol; c++) {
      const counts = prefixCountsByCol.get(c);
      let best = '';
      let bestCount = 0;
      counts?.forEach((count, prefix) => {
        if (count > bestCount) {
          bestCount = count;
          best = prefix;
        }
      });
      colLabels.push(best);
    }

    return { positioned, unpositioned, duplicatedCabinets, colLabels };
  }, [cabinets, minCol, maxCol]);

  const highlightSet = useMemo(() => new Set(highlightCabinetIds ?? []), [highlightCabinetIds]);

  const visibleMarkers = useMemo(() => markers.filter(isMarkerPositioned), [markers]);

  const occupiedCells = useMemo(
    () => new Set(positioned.map((c) => `${c.row},${c.col}`)),
    [positioned]
  );

  const renderableMarkers = useMemo(
    () => visibleMarkers.filter((m) => !occupiedCells.has(`${m.row_number},${m.col_number}`)),
    [visibleMarkers, occupiedCells]
  );

  const cellConflicts = useMemo(() => {
    const map = new Map<string, { cabinetNumbers: string[]; markerNames: string[] }>();

    groupCabinetsByCell(cabinets).forEach((list, key) => {
      if (list.length > 1) {
        map.set(key, { cabinetNumbers: list.map((c) => c.cabinet_number), markerNames: [] });
      }
    });

    for (const marker of visibleMarkers) {
      const key = `${marker.row_number},${marker.col_number}`;
      if (!occupiedCells.has(key)) continue;
      const entry = map.get(key) ?? { cabinetNumbers: [], markerNames: [] };
      entry.markerNames.push(
        marker.label ||
        (MARKER_TYPE_LABEL_KEYS[marker.marker_type]
          ? t(MARKER_TYPE_LABEL_KEYS[marker.marker_type])
          : marker.marker_type)
      );
      map.set(key, entry);
    }

    return map;
  }, [cabinets, visibleMarkers, occupiedCells]);

  const legendStatuses = useMemo(
    () => [...new Set(cabinets.map((c) => c.status ?? DEFAULT_STATUS))].sort((a, b) => a - b),
    [cabinets]
  );

  const matchedIds = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return null;
    return new Set(
      cabinets
        .filter(
          (c) =>
            c.cabinet_number.toLowerCase().includes(kw) ||
            (c.customer_name ?? '').toLowerCase().includes(kw)
        )
        .map((c) => c.id)
    );
  }, [cabinets, keyword]);

  const selectedCabinet = useMemo(
    () => cabinets.find((c) => c.id === selectedId) ?? null,
    [cabinets, selectedId]
  );

  const handleSelect = useCallback((cabinetId: number) => {
    setSelectedMarkerId(null);
    setSelectedId(cabinetId);
  }, []);

  const handleSelectMarker = useCallback((markerId: number) => {
    setSelectedId(null);
    setSelectedMarkerId((prev) => (prev === markerId ? null : markerId));
  }, []);

  const handleOpen = useCallback(
    (cabinetId: number) => {
      if (readOnly) return;
      navigate(`/cabinets/${cabinetId}`);
    },
    [navigate, readOnly]
  );


  const viewportRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const panRef = useRef<{ x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  const zoomWithAnchor = useCallback(
    (nextScale: number, pointerX: number, pointerY: number) => {
      const el = viewportRef.current;
      if (!el || nextScale === scale) return;
      el.scrollLeft = scrollForZoom(el.scrollLeft, pointerX, scale, nextScale);
      el.scrollTop = scrollForZoom(el.scrollTop, pointerY, scale, nextScale);
      setScale(nextScale);
    },
    [scale]
  );

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomWithAnchor(
        clampScale(scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1)),
        e.clientX - rect.left,
        e.clientY - rect.top
      );
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [scale, zoomWithAnchor]);

  const handlePanStart = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('[role="button"]')) return;
    panRef.current = { x: e.clientX, y: e.clientY };
    setPanning(true);
  }, []);

  useEffect(() => {
    if (!panning) return;
    const onMove = (e: MouseEvent) => {
      const last = panRef.current;
      const el = viewportRef.current;
      if (!last || !el) return;
      el.scrollLeft -= e.clientX - last.x;
      el.scrollTop -= e.clientY - last.y;
      panRef.current = { x: e.clientX, y: e.clientY };
    };
    const onUp = () => setPanning(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [panning]);

  const zoomAtCenter = useCallback(
    (factor: number) => {
      const el = viewportRef.current;
      if (!el) return;
      zoomWithAnchor(clampScale(scale * factor), el.clientWidth / 2, el.clientHeight / 2);
    },
    [scale, zoomWithAnchor]
  );

  const resetView = useCallback(() => {
    const el = viewportRef.current;
    setScale(1);
    if (el) {
      el.scrollLeft = 0;
      el.scrollTop = 0;
    }
  }, []);

  const layoutWidth = ROW_HEADER_WIDTH + gap + gridWidth(cols, cellWidth, gap);
  const layoutHeight = COL_HEADER_HEIGHT + gap + gridHeight(rows, cellHeight, gap);

  if (cabinets.length === 0 && markers.length === 0) {
    return <Empty description={t('roomLayout.empty.noCabinetOrMarker')} />;
  }

  /*
   * 无定位机柜时只把网格降级为空态提示，**不可改为提前 return**：
   * 下方「未设置位置的机柜」列表必须始终渲染，否则全部机柜都未定位时
   * 会连列表一起消失，用户看不到任何机柜（回归见 RoomLayout.test.tsx）。
   */
  return (
    <div>
      {/* 工具栏：关键字定位 + 密度切换 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 12,
          marginBottom: 12
        }}
      >
        <Input
          allowClear
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t('roomLayout.searchPlaceholder')}
          prefix={<SearchOutlined style={{ color: token.colorTextTertiary }} />}
          style={{ width: 220 }}
          aria-label={t('roomLayout.searchPlaceholder')}
        />
        {matchedIds ? (
          <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
            {t('roomLayout.matched', { count: matchedIds.size })}
          </span>
        ) : null}
        <Segmented
          value={density}
          onChange={(value) => setDensity(value as DensityKey)}
          options={DENSITY_KEYS.map((key) => ({
            label: t(DENSITY_CONFIG[key].labelKey),
            value: key
          }))}
        />
        <Space.Compact>
          <Button
            icon={<ZoomOutOutlined />}
            onClick={() => zoomAtCenter(1 / 1.2)}
            aria-label={t('roomLayout.zoom.out')}
          />
          <Button
            icon={<ZoomInOutlined />}
            onClick={() => zoomAtCenter(1.2)}
            aria-label={t('roomLayout.zoom.in')}
          />
          <Button
            icon={<ExpandOutlined />}
            onClick={resetView}
            aria-label={t('roomLayout.zoom.reset')}
          />
        </Space.Compact>
        <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
          {t('roomLayout.zoom.level', { pct: Math.round(scale * 100) })}
        </span>
      </div>

      {/* 选中信息条：同时提供显式跳转入口（双击不便发现、键盘无法触发） */}
      {selectedCabinet ? (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 12,
            marginBottom: 12,
            padding: '6px 12px',
            borderRadius: 6,
            backgroundColor: token.colorFillQuaternary,
            fontSize: 12,
            color: token.colorTextSecondary
          }}
        >
          <strong style={{ color: token.colorText, fontSize: 13 }}>
            {selectedCabinet.cabinet_number}
          </strong>
          <span>
            {t('roomLayout.tooltip.status', {
              value:
                getCabinetStatusMeta(selectedCabinet.status ?? DEFAULT_STATUS, tDevice)?.label ?? ''
            })}
          </span>
          <span>{t('roomLayout.uUsage', { pct: selectedCabinet.u_usage_rate ?? 0 })}</span>
          <span>{t('roomLayout.devices', { count: selectedCabinet.device_count ?? 0 })}</span>
          <span>
            {isPositioned(selectedCabinet)
              ? t('roomLayout.tooltip.position', {
                  value: t('roomLayout.position', {
                    row: selectedCabinet.row,
                    col: selectedCabinet.col
                  })
                })
              : t('roomLayout.tooltip.position', { value: t('roomLayout.positionUnset') })}
          </span>
          <Button type="link" size="small" onClick={() => handleOpen(selectedCabinet.id)}>
            {t('roomLayout.action.viewDetail')}
          </Button>
          <Button type="text" size="small" onClick={() => setSelectedId(null)}>
            {t('roomLayout.action.clearSelection')}
          </Button>
          {readOnly ? <span>{t('roomLayout.readOnlyHint')}</span> : null}
        </div>
      ) : null}

      {/* 状态图例 */}
      {legendStatuses.length > 0 ? <StatusLegend statuses={legendStatuses} token={token} /> : null}

      {/* 通道图例：仅有配置时显示，避免给未使用该特性的机房增加视觉噪音 */}
      {channels.length > 0 ? <ChannelLegend token={token} /> : null}

      {rows > 0 && cols > 0 ? (
        <div
          ref={viewportRef}
          data-testid="room-layout-viewport"
          onMouseDown={handlePanStart}
          style={{
            overflow: 'auto',
            maxHeight: '70vh',
            paddingBottom: 8,
            cursor: panning ? 'grabbing' : 'grab',
            userSelect: panning ? 'none' : undefined
          }}
        >
          {/*
            占位层：按 scale 撑出与缩放后内容一致的滚动空间。
            transform 不改变布局尺寸，若无此层，滚动条范围会停留在未缩放的尺寸上
            （缩小时滚动条多余、放大时又滚不到边）。
          */}
          <div
            data-testid="room-layout-canvas"
            style={{ width: layoutWidth * scale, height: layoutHeight * scale }}
          >
            <div
              style={{
                display: 'inline-grid',
                gridTemplateColumns: `${ROW_HEADER_WIDTH}px auto`,
                gridTemplateRows: `${COL_HEADER_HEIGHT}px auto`,
                gap,
                alignItems: 'center',
                transform: toScaleTransform(scale),
                transformOrigin: '0 0'
              }}
            >
              {/* 列头：线性量级，承担坐标参照；显示该列编号前缀（取不到则回退"列N"） */}
              <div
                data-testid="room-layout-col-headers"
                style={{
                  gridColumn: 2,
                  gridRow: 1,
                  display: 'grid',
                  gridTemplateColumns: `repeat(${cols}, ${cellWidth}px)`,
                  gap
                }}
              >
                {Array.from({ length: cols }, (_, i) => (
                  <div
                    key={`col-header-${i}`}
                    style={{
                      textAlign: 'center',
                      fontSize: 12,
                      color: token.colorTextSecondary,
                      fontWeight: 500
                    }}
                  >
                    {colLabels[i]
                      ? `${colLabels[i]}(${minCol + i})`
                      : t('roomLayout.colHeader', { index: minCol + i })}
                  </div>
                ))}
              </div>

              {/* 行头：线性量级，只显示行号（编号前缀属于"列"，已移到列头） */}
              <div
                data-testid="room-layout-row-headers"
                style={{
                  gridColumn: 1,
                  gridRow: 2,
                  display: 'grid',
                  gridTemplateRows: `repeat(${rows}, ${cellHeight}px)`,
                  gap
                }}
              >
                {Array.from({ length: rows }, (_, i) => (
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
                    {minRow + i}
                  </div>
                ))}
              </div>

              {/*
              平面主体：只为有机柜的格子建 DOM，空位由容器背景网格线表达。
              网格线画在间隙正中（cell + gap/2），避开不透明机柜色块下方，
              否则线会被色块盖住而不可见。
              机柜为绝对定位，故容器只需 position: relative；尺寸由几何函数算出，
              与改造前 grid 的 width/height 公式完全一致（保证既有断言不变）。
              后续 §3.1 通道色带、§3.2 标记、上架模拟预览都在此容器内叠加 SVG 图层。
            */}
              <div
                data-testid="room-layout-grid"
                style={{
                  gridColumn: 2,
                  gridRow: 2,
                  position: 'relative',
                  width: gridWidth(cols, cellWidth, gap),
                  height: gridHeight(rows, cellHeight, gap),
                  backgroundImage: `linear-gradient(to right, ${token.colorBorderSecondary} 1px, transparent 1px), linear-gradient(to bottom, ${token.colorBorderSecondary} 1px, transparent 1px)`,
                  backgroundSize: `${cellWidth + gap}px ${cellHeight + gap}px`,
                  backgroundPosition: `${cellWidth + gap / 2}px ${cellHeight + gap / 2}px`
                }}
              >
                {/* 通道色带：绝对定位覆盖层；渲染在机柜之前，DOM 顺序在前 = 视觉在下 */}
                <ChannelLayer
                  channels={channels}
                  rows={rows}
                  cols={cols}
                  cellWidth={cellWidth}
                  cellHeight={cellHeight}
                  gap={gap}
                  token={token}
                  colOffset={colOffset}
                />
                {/* 占位标记：与机柜同为"占据格子"的内容，同样画在机柜之前 */}
                {renderableMarkers.map((marker) => (
                  <MarkerNode
                    key={marker.id}
                    marker={marker}
                    token={token}
                    left={cellLeft(marker.col_number - colOffset, cellWidth, gap)}
                    top={cellTop(marker.row_number - rowOffset, cellHeight, gap)}
                    cellWidth={cellWidth}
                    cellHeight={cellHeight}
                    selected={selectedMarkerId === marker.id}
                    onSelect={handleSelectMarker}
                  />
                ))}
                {positioned.map((cabinet) => (
                  <CabinetNode
                    key={cabinet.id}
                    cabinet={cabinet}
                    token={token}
                    left={cellLeft(cabinet.col! - colOffset, cellWidth, gap)}
                    top={cellTop(cabinet.row! - rowOffset, cellHeight, gap)}
                    cellWidth={cellWidth}
                    cellHeight={cellHeight}
                    showCustomer={showCustomer}
                    dimmed={matchedIds != null && !matchedIds.has(cabinet.id)}
                    highlighted={
                      (matchedIds != null && matchedIds.has(cabinet.id)) ||
                      highlightSet.has(cabinet.id)
                    }
                    selected={selectedId === cabinet.id}
                    readOnly={readOnly}
                    onSelect={handleSelect}
                    onOpen={handleOpen}
                  />
                ))}
                {/* 冲突角标画在机柜之后（DOM 顺序在后 = 视觉在上），免得被机柜格子盖住 */}
                {[...cellConflicts.entries()].map(([key, info]) => {
                  const [r, c] = key.split(',').map(Number);
                  const reasons: string[] = [];
                  if (info.cabinetNumbers.length > 1) {
                    reasons.push(
                      t('roomLayout.conflict.cellCabinets', {
                        count: info.cabinetNumbers.length,
                        list: info.cabinetNumbers.join(t('roomLayout.conflict.listSeparator'))
                      })
                    );
                  }
                  if (info.markerNames.length > 0) {
                    reasons.push(
                      t('roomLayout.conflict.cellMarkers', {
                        list: info.markerNames.join(t('roomLayout.conflict.listSeparator'))
                      })
                    );
                  }
                  return (
                    <Tooltip
                      key={`conflict-${key}`}
                      title={
                        <div style={{ fontSize: 12 }}>{`${reasons.join(
                          t('roomLayout.conflict.separator')
                        )}${t('roomLayout.conflict.verify')}`}</div>
                      }
                    >
                      <WarningFilled
                        data-testid={`cell-conflict-${r}-${c}`}
                        style={{
                          position: 'absolute',
                          left: cellLeft(c - colOffset, cellWidth, gap) + cellWidth - 9,
                          top: cellTop(r - rowOffset, cellHeight, gap) - 5,
                          fontSize: 14,
                          color: token.colorWarning,
                          zIndex: 2
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <Empty description={t('roomLayout.empty.noPosition')} />
      )}

      {/*
        位置冲突的机柜：与同机房其它机柜填了相同行列号，未在平面图上显示。
        这一段是必需而非锦上添花——没有它，被挤掉的机柜在整个界面上完全不可见，
        运维会以为机柜根本没创建成功（真实案例：A1 被新建的 A8 顶替）。
      */}
      <DuplicatedCabinetList
        cabinets={duplicatedCabinets}
        readOnly={readOnly}
        onOpen={handleOpen}
        token={token}
      />

      <UnpositionedCabinetList
        cabinets={unpositioned}
        matchedIds={matchedIds}
        selectedId={selectedId}
        readOnly={readOnly}
        token={token}
        onSelect={handleSelect}
        onOpen={handleOpen}
      />
    </div>
  );
}

export default RoomLayout;
