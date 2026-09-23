import React from 'react';
import { Tooltip, Button, theme } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { TYPE_CONFIG, NODE_STATUS_COLOR } from './constants';
import { displayLabel } from './geometry';
import NodeGrid from './NodeGrid';
import type { OccupiedPosition } from './types';

interface DetailPanelProps {
  device: OccupiedPosition | null;
  totalU: number;
}

const DetailPanel: React.FC<DetailPanelProps> = ({ device, totalU }) => {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { t } = useTranslation('asset');

  if (!device) {
    return (
      <div
        style={{
          padding: '12px 14px',
          background: token.colorBgContainer,
          border: `0.5px solid ${token.colorBorderSecondary}`,
          borderRadius: 8,
          color: token.colorTextTertiary,
          fontSize: 12
        }}
      >
        {t('uposition.detail.empty')}
      </div>
    );
  }

  const cfg = TYPE_CONFIG[device.deviceType ?? 'server'];
  const isMulti = device.deviceType === 'multinode';

  const uStart = displayLabel(device.uPosition, totalU);
  const uEnd = displayLabel(device.uPosition + device.uSize - 1, totalU);
  const uRange = t('uposition.detail.uRange', {
    end: uEnd,
    start: uStart,
    size: device.uSize
  });

  const rows: [string, string][] = [[t('uposition.detail.uPosition'), uRange]];
  if (device.ip) rows.push(['IP', device.ip]);
  if (device.ipmiAddress) rows.push(['IPMI', device.ipmiAddress]);
  if (device.vendor && device.model)
    rows.push([t('uposition.detail.model'), `${device.vendor} ${device.model}`]);
  else if (device.model) rows.push([t('uposition.detail.model'), device.model]);
  if (device.sn) rows.push([t('uposition.detail.sn'), device.sn]);
  if (device.power) rows.push([t('uposition.label.power'), `${device.power}W`]);

  return (
    <div
      style={{
        background: token.colorBgContainer,
        border: `0.5px solid ${token.colorBorderSecondary}`,
        borderRadius: 8,
        overflow: 'hidden'
      }}
    >
      {/* 设备头 */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: `0.5px solid ${token.colorBorderSecondary}`,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: cfg.bg
        }}
      >
        <div
          style={{ width: 10, height: 10, borderRadius: 2, background: cfg.accent, flexShrink: 0 }}
        />
        <span
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: cfg.text,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}
        >
          {device.deviceName}
        </span>
        <span style={{ fontSize: 10, color: cfg.subText, flexShrink: 0 }}>
          {t(cfg.labelKey)}
        </span>
      </div>

      {/* 字段列表 */}
      <div style={{ padding: '4px 0' }}>
        {rows.map(([label, val]) => (
          <div
            key={label}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 11,
              padding: '3px 12px'
            }}
          >
            <span style={{ color: token.colorTextSecondary }}>{label}</span>
            <span
              style={{ fontWeight: 500, color: token.colorText, textAlign: 'right', marginLeft: 8 }}
            >
              {val}
            </span>
          </div>
        ))}
      </div>

      {/* 多节点详情 */}
      {isMulti && device.nodes && device.nodes.length > 0 && (
        <div
          style={{
            padding: '6px 12px 8px',
            borderTop: `0.5px solid ${token.colorBorderSecondary}`
          }}
        >
          <div style={{ fontSize: 10, color: token.colorTextSecondary, marginBottom: 4 }}>
            {t('uposition.detail.nodeSummary', {
              online: device.nodes.filter((n) => n.status === 'active').length,
              total: device.nodes.length,
              fault: device.nodes.filter((n) => n.status === 'fault').length
            })}
          </div>
          {device.nodeRows && device.nodeCols ? (
            <NodeGrid nodes={device.nodes} nodeRows={device.nodeRows} nodeCols={device.nodeCols} />
          ) : (
            <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              {device.nodes.map((n) => (
                <Tooltip key={n.id} title={`${n.label}${n.ip ? ` · ${n.ip}` : ''}`}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                      background: NODE_STATUS_COLOR[n.status]
                    }}
                  />
                </Tooltip>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 详情按钮 */}
      <div style={{ padding: '6px 12px', borderTop: `0.5px solid ${token.colorBorderSecondary}` }}>
        <Button
          type="link"
          size="small"
          icon={<RightOutlined />}
          style={{ padding: 0, fontSize: 11, height: 'auto' }}
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/devices/${device.deviceId}`);
          }}
        >
          {t('uposition.detail.viewDetail')}
        </Button>
      </div>
    </div>
  );
};

export default DetailPanel;
