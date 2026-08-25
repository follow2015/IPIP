import { useMemo } from 'react';
import { Select, InputNumber, Space, Alert, Spin, Descriptions, Tag } from 'antd';
import { DEVICE_TYPE_MAP, DEVICE_SUBTYPE_LABELS } from '@/types/enums';
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
  
  const templatePreviewItems = useMemo(() => {
    if (!templateDetail) return [];
    const d = templateDetail;
    const typeLabel =
      DEVICE_TYPE_MAP[d.device_type as keyof typeof DEVICE_TYPE_MAP]?.label ?? d.device_type;
    const subtypeLabel = d.device_subtype
      ? (DEVICE_SUBTYPE_LABELS[d.device_subtype as keyof typeof DEVICE_SUBTYPE_LABELS] ??
        d.device_subtype)
      : '-';
    const items = [
      { label: '设备名称', children: d.device_name },
      { label: '设备类型', children: `${typeLabel} / ${subtypeLabel}` },
      { label: '品牌/型号', children: `${d.brand ?? '-'} / ${d.device_model ?? '-'}` },
      { label: '机柜', children: d.cabinet_number ?? '未分配' },
      {
        label: 'U位/U高',
        children: `${d.u_position != null ? `U${d.u_position}` : '-'} / ${d.height_u}U`
      },
      {
        label: '状态',
        children: <Tag color={getStatusColor(d.status)}>{getStatusLabel(d.status)}</Tag>
      }
    ];
    
    if (d.is_chassis && d.node_rows && d.node_cols) {
      items.push({
        label: '节点布局',
        children: `${d.node_rows}行 × ${d.node_cols}列 = ${d.node_rows * d.node_cols}节点`
      });
    }
    return items;
  }, [templateDetail]);

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>模板设备</label>
        <Select
          value={templateId}
          onChange={setTemplateId}
          onSearch={setSearchText}
          options={deviceSelectOptions}
          showSearch
          filterOption={false}
          placeholder="搜索设备名称..."
          style={{ width: '100%' }}
          loading={isDeviceListLoading}
          notFoundContent={isTemplateLoading ? <Spin size="small" /> : '无匹配设备'}
        />
      </div>

      {templateId && isTemplateLoading && (
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <Spin description="加载模板详情..." />
        </div>
      )}

      {templateDetail && (
        <Descriptions
          bordered
          size="small"
          column={2}
          items={templatePreviewItems}
          style={{ marginBottom: 16 }}
        />
      )}

      {isChassisTemplate && (
        <Alert
          type="info"
          title="机箱设备克隆将自动生成与模板相同布局的子节点"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Space size="large" wrap>
        <div>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>克隆数量</label>
          <Space>
            <InputNumber
              value={cloneCount}
              onChange={(v) => setCloneCount(v ?? 1)}
              min={1}
              max={50}
              style={{ width: 120 }}
            />
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>最多 50 台</span>
          </Space>
        </div>
        {}
        {isNodeTemplate ? (
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              目标机箱 <span style={{ color: '#ff4d4f' }}>*</span>
            </label>
            <Select
              value={cloneChassisId}
              onChange={setCloneChassisId}
              options={cloneChassisOptions}
              placeholder="请选择目标机箱"
              style={{ width: 280 }}
              allowClear
            />
            {cloneChassisId && (
              <span style={{ color: '#8c8c8c', fontSize: 12, marginLeft: 8 }}>
                空余位置：{cloneAvailablePositions.length} 个
              </span>
            )}
          </div>
        ) : (
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>目标机柜</label>
            <Select
              value={targetCabinetId}
              onChange={setTargetCabinetId}
              options={cabinetOptions}
              placeholder={
                templateDetail?.cabinet_number
                  ? `默认：${templateDetail.cabinet_number}`
                  : '选择目标机柜'
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
