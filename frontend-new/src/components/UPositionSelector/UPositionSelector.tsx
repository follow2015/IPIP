/**
 * 机柜U位布局图 v6（组合根）
 *
 * 设计要点（详见 ./docs 中各模块）：
 * 1. 拖拽后位置持久化 —— 使用 "已提交" 标记（committedRef）隔离本地状态与外部同步，
 *    拖拽成功后不再被 useEffect 重置，直到下一次外部数据真正变化才重新同步。
 * 2. U位编号与物理位置严格对应 —— 遵循机柜行业标准：底部=U1，顶部=U42。
 *    内部坐标系（U1=顶部）与物理U位通过 physicalToInternal/internalToPhysical 双向转换。
 * 3. 机箱子节点独立拖拽 —— 机箱子节点以独立 DeviceBlock 渲染在机箱内部，
 *    支持在机箱范围内上下拖动调整节点行序（仅视觉重排，通过 onNodeReorder 回调上报）。
 * 4. 显示逻辑优化 —— 机箱展开/折叠；子节点悬浮卡片；空槽高亮逻辑修正。
 * 5. 响应式自适应 —— 使用 ResizeObserver 监听容器宽度，动态调整行高、字号、信息密度；
 *    大屏显示更多设备信息（IP、型号、SN），小屏精简显示；
 *    右侧面板在大屏时显示，小屏时折叠为底部区域。
 *
 * 模块拆分：
 * - useRackLayout: 核心状态与拖拽/选中/折叠/响应式/统计逻辑
 * - RackBody: 机柜头 + 空槽网格 + 设备块 + 底栏统计
 * - SidePanel: 图例 + 利用率 + 拖放反馈 + 详情面板
 * - DeviceBlock / NodeGrid / NodeList / DetailPanel: 展示子组件
 * - geometry / layout / constants / types: 纯函数与常量
 */

import React from 'react';
import { useRackLayout } from './useRackLayout';
import RackBody from './RackBody';
import SidePanel from './SidePanel';
import type { UPositionSelectorProps } from './types';

export type {
  RackDeviceType,
  NodeStatus,
  DeviceNode,
  OccupiedPosition,
  UPositionSelectorProps
} from './types';

const UPositionSelector: React.FC<UPositionSelectorProps> = (props) => {
  const { totalU = 42, ratedPower = 8000, readOnly = false, onNodeReorder } = props;

  const rack = useRackLayout(props);

  return (
    <div
      ref={rack.containerRef}
      style={{
        display: 'flex',
        gap: 16,
        alignItems: 'flex-start',
        flexWrap: rack.layout.showSidePanel ? 'nowrap' : 'wrap'
      }}
    >
      <RackBody
        bodyRef={rack.bodyRef}
        devices={rack.devices}
        layout={rack.layout}
        totalU={totalU}
        readOnly={readOnly}
        selectedId={rack.selectedId}
        collapsed={rack.collapsed}
        highlightUs={rack.highlightUs}
        occupiedSet={rack.occupiedSet}
        totalH={rack.totalH}
        deviceCount={rack.devices.length}
        usedU={rack.stats.usedU}
        usedP={rack.stats.usedP}
        onSelect={rack.handleSelect}
        onToggleCollapse={rack.toggleCollapse}
        onDragStart={rack.handleDragStart}
        onSlotDragOver={rack.handleSlotDragOver}
        onSlotDrop={rack.handleSlotDrop}
        onDragEnd={rack.handleDragEnd}
        clearHighlight={rack.clearHighlight}
        onNodeReorder={onNodeReorder}
      />

      {/* ── 右侧信息列（大屏） / 底部信息区（小屏） ── */}
      {rack.layout.showSidePanel ? (
        <div
          style={{
            flex: '0 0 220',
            minWidth: 180,
            maxWidth: 260,
            display: 'flex',
            flexDirection: 'column',
            gap: 10
          }}
        >
          <SidePanel
            selectedDevice={rack.selectedDevice}
            totalU={totalU}
            ratedPower={ratedPower}
            usedU={rack.stats.usedU}
            usedP={rack.stats.usedP}
            uPct={rack.stats.uPct}
            pPct={rack.stats.pPct}
            dropMsg={rack.dropMsg}
          />
        </div>
      ) : (
        <div
          style={{
            flex: '1 1 100%',
            display: 'flex',
            flexDirection: 'row',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'flex-start'
          }}
        >
          <SidePanel
            selectedDevice={rack.selectedDevice}
            totalU={totalU}
            ratedPower={ratedPower}
            usedU={rack.stats.usedU}
            usedP={rack.stats.usedP}
            uPct={rack.stats.uPct}
            pPct={rack.stats.pPct}
            dropMsg={rack.dropMsg}
          />
        </div>
      )}
    </div>
  );
};

export default UPositionSelector;
