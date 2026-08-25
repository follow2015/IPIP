/**
 * 拓扑工具栏
 *
 * 布局切换 / 缩放 / 适配 / 搜索定位
 */
import React from 'react';
import { Space, Select, Button, Input, Tooltip, Segmented } from 'antd';
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { LayoutType } from './TopologyGraph';

interface TopologyToolbarProps {
  layout: LayoutType;
  onLayoutChange: (layout: LayoutType) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onSearch: (value: string) => void;
}

const LAYOUT_OPTIONS: { label: string; value: LayoutType }[] = [
  { label: '力导向', value: 'force' },
  { label: '分层', value: 'dagre' },
  { label: '同心圆', value: 'concentric' },
  { label: '辐射', value: 'radial' },
];

const TopologyToolbar: React.FC<TopologyToolbarProps> = ({
  layout,
  onLayoutChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onSearch,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        background: '#fff',
        borderBottom: '1px solid #f0f0f0',
        borderRadius: '8px 8px 0 0',
      }}
    >
      <Space size="middle">
        <span style={{ fontSize: 13, color: '#666' }}>布局</span>
        <Segmented
          options={LAYOUT_OPTIONS}
          value={layout}
          onChange={(val) => onLayoutChange(val as LayoutType)}
          size="small"
        />
      </Space>

      <Space size="small">
        <Input
          placeholder="搜索设备名"
          prefix={<SearchOutlined />}
          allowClear
          size="small"
          style={{ width: 180 }}
          onChange={(e) => onSearch(e.target.value)}
          onPressEnter={(e) => onSearch((e.target as HTMLInputElement).value)}
        />
      </Space>

      <Space size="small">
        <Tooltip title="放大">
          <Button size="small" icon={<ZoomInOutlined />} onClick={onZoomIn} />
        </Tooltip>
        <Tooltip title="缩小">
          <Button size="small" icon={<ZoomOutOutlined />} onClick={onZoomOut} />
        </Tooltip>
        <Tooltip title="适配画布">
          <Button size="small" icon={<FullscreenOutlined />} onClick={onFitView} />
        </Tooltip>
      </Space>
    </div>
  );
};

export default TopologyToolbar;
