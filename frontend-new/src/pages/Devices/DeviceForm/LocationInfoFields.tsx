/**
 * LocationInfoFields — 设备「位置信息」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。包含机房/机柜选择、U位录入、冲突检测告警、
 * 智能分配入口与 U 位视图。复用父级 <Form> 上下文，不持有 form 实例。
 */
import { Form, Select, InputNumber, Row, Col, Alert, Divider, Tooltip } from 'antd';
import type { SelectProps } from 'antd';
import { AimOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import UPositionView from './UPositionView';

interface CabinetLayout {
  total_u: number;
  used_u: number;
  u_map: Record<
    number,
    {
      device_id: number;
      device_name: string;
      device_type: string;
      is_start: boolean;
      height_u: number;
      power: number | null;
    }
  >;
}

interface LocationInfoFieldsProps {
  roomOptions?: SelectProps['options'];
  cabinetOptions?: SelectProps['options'];
  uPositionStatus: number[] | null;
  selectedCabinetId?: number | string;
  availableUPositions?: number[];
  onAutoAssignUPosition: () => void;
  cabinetLayout?: CabinetLayout | null;
  watchedUPosition?: number | null;
  watchedHeightU?: number | null;
}

export default function LocationInfoFields({
  roomOptions,
  cabinetOptions,
  uPositionStatus,
  selectedCabinetId,
  availableUPositions,
  onAutoAssignUPosition,
  cabinetLayout,
  watchedUPosition,
  watchedHeightU
}: LocationInfoFieldsProps) {
  const { t } = useTranslation('device');
  return (
    <>
      <Divider plain>{t('form.section.location')}</Divider>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Form.Item name="room_id" label={t('basic.field.room')}>
            <Select placeholder={t('form.select.room')} options={roomOptions} allowClear />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item
            name="cabinet_id"
            label={t('form.location.cabinet.label')}
            rules={[{ required: true, message: t('form.location.cabinet.required') }]}
          >
            <Select
              placeholder={t('form.hint.selectRoomFirst')}
              options={cabinetOptions}
              allowClear
            />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={12} md={6}>
          <Form.Item name="height_u" label={t('basic.field.occupiedU')}>
            <InputNumber
              min={1}
              max={42}
              style={{ width: '100%' }}
              placeholder={t('form.location.occupiedU.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item
            name="device_gap"
            label={t('form.location.deviceGap.label')}
            extra={t('form.location.deviceGap.extra')}
          >
            <InputNumber
              min={0}
              max={10}
              style={{ width: '100%' }}
              placeholder={t('form.location.deviceGap.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item
            name="u_position"
            label={t('field.uPosition')}
            validateStatus={uPositionStatus ? 'error' : undefined}
            help={
              uPositionStatus
                ? t('form.location.uPosition.conflict', {
                    positions: uPositionStatus.join(', U')
                  })
                : undefined
            }
          >
            <InputNumber
              min={1}
              style={{ width: '100%' }}
              placeholder={t('form.location.uPosition.placeholder')}
              disabled={!selectedCabinetId}
              addonAfter={
                <Tooltip title={t('form.location.uPosition.autoAssignTooltip')}>
                  <AimOutlined
                    onClick={onAutoAssignUPosition}
                    style={{
                      cursor: selectedCabinetId ? 'pointer' : 'not-allowed',
                      color: selectedCabinetId ? '#1890ff' : '#d9d9d9'
                    }}
                  />
                </Tooltip>
              }
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={6} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
          {availableUPositions && availableUPositions.length > 0 && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {t('form.location.availableUPositions', { count: availableUPositions.length })}
            </span>
          )}
          {selectedCabinetId && availableUPositions && availableUPositions.length === 0 && (
            <Alert
              type="warning"
              title={t('form.location.noAvailableUPosition')}
              style={{ padding: '2px 8px' }}
              showIcon
            />
          )}
        </Col>
      </Row>
      {/* U位视图 */}
      {selectedCabinetId && cabinetLayout && (
        <UPositionView
          layout={cabinetLayout}
          currentU={watchedUPosition}
          currentHeightU={watchedHeightU ?? 1}
        />
      )}
    </>
  );
}
