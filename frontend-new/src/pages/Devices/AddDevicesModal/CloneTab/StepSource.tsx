import { useMemo } from 'react';
import { Select, InputNumber, Space, Alert, Spin, Descriptions, Tag } from 'antd';
import { getDeviceSubtypeLabel, getDeviceTypeMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Device } from '@/types/models';
import { getStatusLabel, getStatusColor } from '../shared';

export interface StepSourceProps {
  templateId: number | null;
  setTemplateId: (id: number | null) => void;
  setSearchText: (s: string) => void;
  cloneCount: number;
  setCloneCount: (n: number) => void;
  targetCabinetId: number | null;
  setTargetCabinetId: (id: number | null) => void;
  isTemplateLoading: boolean;
  isDeviceListLoading: boolean;
  deviceSelectOptions: { label: string; value: number }[];
  templateDetail?: Device | null;
  isChassisTemplate: boolean;
  isNodeTemplate: boolean;
  cloneChassisId: number | undefined;
  setCloneChassisId: (id: number | undefined) => void;
  cloneChassisOptions: { label: string; value: number }[];
  cloneAvailablePositions: number[];
  cabinetOptions: { label: string; value: number }[];
}

const StepSource: React.FC<StepSourceProps> = ({
  templateId,
  setTemplateId,
  setSearchText,
  cloneCount,
  setCloneCount,
  targetCabinetId,
  setTargetCabinetId,
  isTemplateLoading,
  isDeviceListLoading,
  deviceSelectOptions,
  templateDetail,
  isChassisTemplate,
  isNodeTemplate,
  cloneChassisId,
  setCloneChassisId,
  cloneChassisOptions,
  cloneAvailablePositions,
  cabinetOptions
}) => {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const templatePreviewItems = useMemo(() => {
    if (!templateDetail) return [];
    const d = templateDetail;
    const typeLabel =
      getDeviceTypeMeta(d.device_type, t)?.label ?? d.device_type;
    const subtypeLabel = d.device_subtype
      ? (getDeviceSubtypeLabel(d.device_subtype, t) ?? d.device_subtype)
      : '-';
    const items = [
      { label: t('field.name'), children: d.device_name },
      { label: t('basic.field.deviceType'), children: `${typeLabel} / ${subtypeLabel}` },
      { label: t('field.brandModel'), children: `${d.brand ?? '-'} / ${d.device_model ?? '-'}` },
      { label: t('field.cabinet'), children: d.cabinet_number ?? t('addModal.unassigned') },
      {
        label: t('addModal.clone.preview.uPositionHeight'),
        children: `${d.u_position != null ? `U${d.u_position}` : '-'} / ${d.height_u}U`
      },
      {
        label: tCommon('field.status'),
        children: <Tag color={getStatusColor(d.status)}>{getStatusLabel(d.status, t)}</Tag>
      }
    ];
    if (d.is_chassis && d.node_rows && d.node_cols) {
      items.push({
        label: t('addModal.clone.preview.nodeLayout'),
        children: t('addModal.clone.preview.nodeLayoutValue', {
          rows: d.node_rows,
          cols: d.node_cols,
          total: d.node_rows * d.node_cols
        })
      });
    }
    return items;
  }, [templateDetail, t, tCommon]);

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
          {t('addModal.clone.templateDevice')}
        </label>
        <Select
          value={templateId}
          onChange={setTemplateId}
          onSearch={setSearchText}
          options={deviceSelectOptions}
          showSearch
          filterOption={false}
          placeholder={t('addModal.clone.searchPlaceholder')}
          style={{ width: '100%' }}
          loading={isDeviceListLoading}
          notFoundContent={isTemplateLoading ? <Spin size="small" /> : t('addModal.clone.noMatchDevice')}
        />
      </div>

      {templateId && isTemplateLoading && (
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <Spin description={t('addModal.clone.loadingTemplate')} />
        </div>
      )}

      {templateDetail && (
        <Descriptions
          bordered
          size="small"
          column={{ xs: 1, md: 2 }}
          items={templatePreviewItems}
          style={{ marginBottom: 16 }}
        />
      )}

      {isChassisTemplate && (
        <Alert
          type="info"
          title={t('addModal.clone.chassisHint')}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Space size="large" wrap>
        <div>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
            {t('addModal.clone.count')}
          </label>
          <Space>
            <InputNumber
              value={cloneCount}
              onChange={(v) => setCloneCount(v ?? 1)}
              min={1}
              max={50}
              style={{ width: 120 }}
            />
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>{t('addModal.clone.maxCount')}</span>
          </Space>
        </div>
        {/* 节点模式：选择目标机箱；非节点模式：选择目标机柜 */}
        {isNodeTemplate ? (
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              {t('addModal.clone.targetChassis')} <span style={{ color: '#ff4d4f' }}>*</span>
            </label>
            <Select
              value={cloneChassisId}
              onChange={setCloneChassisId}
              options={cloneChassisOptions}
              placeholder={t('addModal.clone.selectTargetChassis')}
              style={{ width: 280 }}
              allowClear
            />
            {cloneChassisId && (
              <span style={{ color: '#8c8c8c', fontSize: 12, marginLeft: 8 }}>
                {t('form.nodeAssoc.vacantCount', { count: cloneAvailablePositions.length })}
              </span>
            )}
          </div>
        ) : (
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              {t('addModal.clone.targetCabinet')}
            </label>
            <Select
              value={targetCabinetId}
              onChange={setTargetCabinetId}
              options={cabinetOptions}
              placeholder={
                templateDetail?.cabinet_number
                  ? t('addModal.clone.defaultPrefix', { name: templateDetail.cabinet_number })
                  : t('addModal.clone.selectTargetCabinet')
              }
              style={{ width: 220 }}
              allowClear
            />
          </div>
        )}
      </Space>
    </div>
  );
};

export default StepSource;
