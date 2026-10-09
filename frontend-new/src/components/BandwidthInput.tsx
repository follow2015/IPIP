import { useEffect, useState } from 'react';
import { InputNumber, Radio, Select, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

export const BANDWIDTH_UNITS = ['M', 'G', 'T', 'P'] as const;
export type BandwidthUnit = (typeof BANDWIDTH_UNITS)[number];

export interface BandwidthValue {
  bandwidth_value?: number | null;
  bandwidth_unit?: BandwidthUnit | null;
  bandwidth_mbps?: number | null;
}

export type BandwidthFieldPrefix = 'bandwidth' | 'committed';

interface BandwidthInputProps {
  value?: BandwidthValue | Record<string, number | string | null> | null;
  onChange?: (value: Record<string, number | string | null>) => void;
  disabled?: boolean;
  fieldPrefix?: BandwidthFieldPrefix;
  integerOnly?: boolean;
  lockedMode?: InputMode | null;
  lockedUnit?: BandwidthUnit | null;
  onModeChange?: (mode: InputMode) => void;
  onUnitChange?: (unit: BandwidthUnit) => void;
}

type InputMode = 'pair' | 'mbps';

function detectMode(
  v: Record<string, number | null>,
  prefix: BandwidthFieldPrefix
): InputMode | null {
  if (v[`${prefix}_mbps`] != null) return 'mbps';
  if (v[`${prefix}_value`] != null || v[`${prefix}_unit`] != null) return 'pair';
  return null;
}

export function BandwidthInput({
  value,
  onChange,
  disabled,
  fieldPrefix = 'bandwidth',
  integerOnly = false,
  lockedMode = null,
  lockedUnit = null,
  onModeChange,
  onUnitChange
}: BandwidthInputProps) {
  const { t } = useTranslation('circuit');
  const v = (value ?? {}) as Record<string, number | null>;

  const [modeState, setModeState] = useState<InputMode | null>(() => detectMode(v, fieldPrefix));
  const mode = lockedMode ?? modeState ?? 'pair';

  useEffect(() => {
    const detected = detectMode((value ?? {}) as Record<string, number | null>, fieldPrefix);
    if (detected) setModeState(detected);
  }, [value, fieldPrefix]);

  useEffect(() => {
    onModeChange?.(mode);
  }, [mode, onModeChange]);

  const currentUnit = (v[`${fieldPrefix}_unit`] ?? lockedUnit ?? 'G') as BandwidthUnit;
  useEffect(() => {
    onUnitChange?.(currentUnit);
  }, [currentUnit, onUnitChange]);

  const numProps = integerOnly ? { precision: 0 } : undefined;

  const switchMode = (next: InputMode) => {
    if (next === mode) return;
    setModeState(next); // 中间态全 null 推断不出，直接落 state
    onChange?.(
      next === 'mbps'
        ? {
            [`${fieldPrefix}_mbps`]: null,
            [`${fieldPrefix}_value`]: null,
            [`${fieldPrefix}_unit`]: null
          }
        : {
            [`${fieldPrefix}_value`]: null,
            [`${fieldPrefix}_unit`]: 'G' as BandwidthUnit,
            [`${fieldPrefix}_mbps`]: null
          }
    );
  };

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      {/* 锁定形态（保底跟随端口带宽）时隐藏模式切换：形态由外部决定 */}
      {!lockedMode && (
        <Radio.Group
          value={mode}
          disabled={disabled}
          onChange={(e) => switchMode(e.target.value as InputMode)}
          optionType="button"
          buttonStyle="solid"
          options={[
            { label: t('bandwidth.mode.pair'), value: 'pair' },
            { label: t('bandwidth.mode.mbps'), value: 'mbps' }
          ]}
        />
      )}

      {mode === 'pair' ? (
        <Space.Compact style={{ width: '100%' }}>
          <InputNumber
            style={{ width: '100%' }}
            min={0}
            {...numProps}
            disabled={disabled}
            placeholder={t('bandwidth.valuePlaceholder')}
            value={v[`${fieldPrefix}_value`] ?? null}
            onChange={(n) =>
              onChange?.({
                [`${fieldPrefix}_value`]: n ?? null,
                [`${fieldPrefix}_unit`]: lockedUnit ?? v[`${fieldPrefix}_unit`] ?? 'G',
                [`${fieldPrefix}_mbps`]: null
              })
            }
            addonAfter={lockedUnit ? `${lockedUnit}bps` : undefined}
          />
          {!lockedUnit && (
            <Select
              style={{ width: '40%' }}
              disabled={disabled}
              value={(v[`${fieldPrefix}_unit`] ?? 'G') as BandwidthUnit}
              onChange={(unit: BandwidthUnit) =>
                onChange?.({
                  [`${fieldPrefix}_value`]: v[`${fieldPrefix}_value`] ?? null,
                  [`${fieldPrefix}_unit`]: unit,
                  [`${fieldPrefix}_mbps`]: null
                })
              }
              options={BANDWIDTH_UNITS.map((u) => ({ label: `${u}bps`, value: u }))}
            />
          )}
        </Space.Compact>
      ) : (
        <Space.Compact style={{ width: '100%' }}>
          <InputNumber
            style={{ width: '100%' }}
            min={0}
            {...numProps}
            disabled={disabled}
            placeholder={t('bandwidth.mbpsPlaceholder')}
            value={v[`${fieldPrefix}_mbps`] ?? null}
            onChange={(n) =>
              onChange?.({
                [`${fieldPrefix}_mbps`]: n ?? null,
                [`${fieldPrefix}_value`]: null,
                [`${fieldPrefix}_unit`]: null
              })
            }
            addonAfter="Mbps"
          />
        </Space.Compact>
      )}
    </Space>
  );
}

export default BandwidthInput;


export interface BandwidthPairValue {
  bandwidth?: Record<string, number | string | null>;
  committed?: Record<string, number | string | null>;
}

export function BandwidthPairInput({
  value,
  onChange,
  disabled
}: {
  value?: BandwidthPairValue | null;
  onChange?: (v: BandwidthPairValue) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation('circuit');
  const [bwMode, setBwMode] = useState<'pair' | 'mbps'>('pair');
  const [bwUnit, setBwUnit] = useState<BandwidthUnit>('G');

  const patch = (key: 'bandwidth' | 'committed', v: Record<string, number | string | null>) =>
    onChange?.({
      bandwidth: key === 'bandwidth' ? v : (value?.bandwidth ?? {}),
      committed: key === 'committed' ? v : (value?.committed ?? {})
    });

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('field.bandwidth')}
        </Typography.Text>
        <BandwidthInput
          value={value?.bandwidth ?? null}
          onChange={(v) => patch('bandwidth', v)}
          disabled={disabled}
          onModeChange={setBwMode}
          onUnitChange={setBwUnit}
        />
      </div>
      <div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('field.committed')}
        </Typography.Text>
        <BandwidthInput
          value={value?.committed ?? null}
          onChange={(v) => patch('committed', v)}
          disabled={disabled}
          fieldPrefix="committed"
          integerOnly
          lockedMode={bwMode}
          lockedUnit={bwUnit}
        />
      </div>
    </Space>
  );
}
