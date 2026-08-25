import React from 'react';
import { Tag, theme } from 'antd';
import { TYPE_CONFIG, pctColor } from './constants';
import DetailPanel from './DetailPanel';
import type { DropMsg } from './useRackLayout';
import type { RackDeviceType, OccupiedPosition } from './types';

interface SidePanelProps {
  selectedDevice: OccupiedPosition | null;
  totalU: number;
  ratedPower: number;
  usedU: number;
  usedP: number;
  uPct: number;
  pPct: number;
  dropMsg: DropMsg;
}

const SidePanel: React.FC<SidePanelProps> = ({
  selectedDevice,
  totalU,
  ratedPower,
  usedU,
  usedP,
  uPct,
  pPct,
  dropMsg
}) => {
  const { token } = theme.useToken();

  return (
    <>
      {/* 图例 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {(
          Object.entries(TYPE_CONFIG) as [RackDeviceType, (typeof TYPE_CONFIG)[RackDeviceType]][]
        ).map(([type, cfg]) => (
          <span
            key={type}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 10,
              color: token.colorTextSecondary
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: cfg.accent,
                display: 'inline-block'
              }}
            />
            {cfg.label}
          </span>
        ))}
      </div>

      {/* 设备详情面板 */}
      <DetailPanel device={selectedDevice} totalU={totalU} />

      {/* 利用率概况 */}
      <div
        style={{
          background: token.colorBgContainer,
          border: `0.5px solid ${token.colorBorderSecondary}`,
          borderRadius: 8,
          padding: '10px 12px'
        }}
      >
        {[
          { label: 'U位利用率', pct: uPct, detail: `${usedU}/${totalU}U` },
          { label: '功率利用率', pct: pPct, detail: `${usedP}/${ratedPower}W` }
        ].map(({ label, pct, detail }) => (
          <div key={label} style={{ marginBottom: 8 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 11,
                marginBottom: 3
              }}
            >
              <span style={{ color: token.colorTextSecondary }}>{label}</span>
              <span style={{ fontWeight: 500, color: token.colorText }}>
                {pct}%
                <Tag
                  color={pct > 85 ? 'error' : pct > 65 ? 'warning' : 'success'}
                  style={{ fontSize: 9, marginLeft: 4, padding: '0 4px', lineHeight: '14px' }}
                >
                  {detail}
                </Tag>
              </span>
            </div>
            <div
              style={{
                height: 4,
                background: token.colorFillQuaternary,
                borderRadius: 2,
                overflow: 'hidden'
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(pct, 100)}%`,
                  background: pctColor(pct),
                  borderRadius: 2,
                  transition: 'width 0.3s'
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* 拖放反馈 */}
      {dropMsg.text && (
        <div
          style={{
            fontSize: 11,
            padding: '4px 8px',
            borderRadius: 4,
            background: dropMsg.type === 'err' ? '#FFF2F0' : '#F6FFED',
            color: dropMsg.type === 'err' ? '#A32D2D' : '#389E0D',
            border: `1px solid ${dropMsg.type === 'err' ? '#FFCCC7' : '#B7EB8F'}`
          }}
        >
          {dropMsg.text}
        </div>
      )}
    </>
  );
};

export default SidePanel;
