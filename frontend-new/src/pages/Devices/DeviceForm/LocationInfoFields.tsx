/**
 * LocationInfoFields — 设备「位置信息」表单区块
 *
 * 从原 DeviceForm.tsx 拆出。包含机房/机柜选择、U位录入、冲突检测告警、
 * 智能分配入口与 U 位视图。复用父级 <Form> 上下文，不持有 form 实例。
 */
import { Form, Select, InputNumber, Row, Col, Alert, Divider, Tooltip } from 'antd';
import type { SelectProps } from 'antd';
import { AimOutlined } from '@ant-design/icons';
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
  return (
    <>
      <Divider plain>位置信息</Divider>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="room_id" label="所属机房">
            <Select placeholder="请选择机房" options={roomOptions} allowClear />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="cabinet_id"
            label="所属机柜"
            rules={[{ required: true, message: '请选择所属机柜' }]}
          >
            <Select placeholder="请先选择机房" options={cabinetOptions} allowClear />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={6}>
          <Form.Item name="height_u" label="占用U数">
            <InputNumber min={1} max={42} style={{ width: '100%' }} placeholder="占用U数" />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="device_gap" label="设备间隔(U)" extra="自动分配U位时生效">
            <InputNumber min={0} max={10} style={{ width: '100%' }} placeholder="间隔" />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item
            name="u_position"
            label="U位"
            validateStatus={uPositionStatus ? 'error' : undefined}
            help={uPositionStatus ? `U位冲突：U${uPositionStatus.join(', U')}` : undefined}
          >
            <InputNumber
              min={1}
              style={{ width: '100%' }}
              placeholder="手动输入或自动分配"
              disabled={!selectedCabinetId}
              addonAfter={
                <Tooltip title="自动分配U位">
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
        <Col span={6} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
          {availableUPositions && availableUPositions.length > 0 && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              可用U位：{availableUPositions.length} 个
            </span>
          )}
          {selectedCabinetId && availableUPositions && availableUPositions.length === 0 && (
            <Alert type="warning" title="机柜无可用U位" style={{ padding: '2px 8px' }} showIcon />
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
