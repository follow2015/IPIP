/**
 * 拓扑工具栏
 *
 * 布局切换 / 缩放 / 适配 / 搜索定位
 */
import React, { useMemo } from 'react';
import { Space, Select, Button, Input, Tooltip, Segmented } from 'antd';
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { LayoutType } from './TopologyGraph';

interface TopologyToolbarProps {
  layout: LayoutType;
  onLayoutChange: (layout: LayoutType) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onSearch: (value: string) => void;
}

type LayoutLabelKey =
  | 'topology.layout.force'
  | 'topology.layout.hierarchical'
  | 'topology.layout.concentric'
  | 'topology.layout.radial';

const LAYOUT_OPTIONS: { key: LayoutLabelKey; value: LayoutType }[] = [
  { key: 'topology.layout.force', value: 'force' },
  { key: 'topology.layout.hierarchical', value: 'dagre' },
  { key: 'topology.layout.concentric', value: 'concentric' },
  { key: 'topology.layout.radial', value: 'radial' },
];

const TopologyToolbar: React.FC<TopologyToolbarProps> = ({
  layout,
  onLayoutChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onSearch,
}) => {
  const { t } = useTranslation('network');

  const layoutOptions = useMemo(
    () => LAYOUT_OPTIONS.map((o) => ({ label: t(o.key), value: o.value })),
    [t]
  );

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
        <span style={{ fontSize: 13, color: '#666' }}>{t('topology.toolbar.layout')}</span>
        <Segmented
          options={layoutOptions}
          value={layout}
          onChange={(val) => onLayoutChange(val as LayoutType)}
          size="small"
        />
      </Space>

      <Space size="small">
        <Input
          placeholder={t('topology.toolbar.searchPlaceholder')}
          prefix={<SearchOutlined />}
          allowClear
          size="small"
          style={{ width: 180 }}
          onChange={(e) => onSearch(e.target.value)}
          onPressEnter={(e) => onSearch((e.target as HTMLInputElement).value)}
        />
      </Space>

      <Space size="small">
        <Tooltip title={t('topology.toolbar.zoomIn')}>
          <Button size="small" icon={<ZoomInOutlined />} onClick={onZoomIn} />
        </Tooltip>
        <Tooltip title={t('topology.toolbar.zoomOut')}>
          <Button size="small" icon={<ZoomOutOutlined />} onClick={onZoomOut} />
        </Tooltip>
        <Tooltip title={t('topology.toolbar.fitView')}>
          <Button size="small" icon={<FullscreenOutlined />} onClick={onFitView} />
        </Tooltip>
      </Space>
    </div>
  );
};

export default TopologyToolbar;
