/**
 * ConnectionFormModal — 新增连接表单 Modal
 *
 * 从 ConnectionTab.tsx 拆出。复用父级 form 实例（父级负责提交与校验），
 * 内部通过 Form.useWatch 监听 room/cabinet/switch 联动以控制禁用与占位文案。
 */
import { Form, Modal, Select, Input, Row, Col } from 'antd';
import type { FormInstance, SelectProps } from 'antd';

interface ConnectionFormModalProps {
  open: boolean;
  onOk: () => void;
  onCancel: () => void;
  form: FormInstance;
  isNetworkDevice: boolean;
  linkTypeOptions: SelectProps['options'];
  connectionTypeOptions: SelectProps['options'];
  roomOptions?: SelectProps['options'];
  cabinetOptions?: SelectProps['options'];
  switchOptions?: SelectProps['options'];
  peerPortOptions?: SelectProps['options'];
  localPortOptions?: SelectProps['options'];
  nicPortOptions?: SelectProps['options'];
}

export default function ConnectionFormModal({
  open,
  onOk,
  onCancel,
  form,
  isNetworkDevice,
  linkTypeOptions,
  connectionTypeOptions,
  roomOptions,
  cabinetOptions,
  switchOptions,
  peerPortOptions,
  localPortOptions,
  nicPortOptions
}: ConnectionFormModalProps) {
  
  const selectedRoomId = Form.useWatch('room_id', form);
  const selectedCabinetId = Form.useWatch('cabinet_id', form);
  const selectedSwitchId = Form.useWatch('switch_device_id', form);

  return (
    <Modal title="新增连接" open={open} onOk={onOk} onCancel={onCancel} width={700} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="link_type" label="连接模式">
              <Select placeholder="请选择" options={linkTypeOptions} disabled />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="connection_type" label="连接类型">
              <Select placeholder="请选择" options={connectionTypeOptions} allowClear />
            </Form.Item>
          </Col>
        </Row>

        {}
        {isNetworkDevice && (
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="switch_port_id"
                label="本机端口"
                rules={[{ required: true, message: '请选择本机端口' }]}
              >
                <Select
                  placeholder="请选择本机端口"
                  options={localPortOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
          </Row>
        )}

        {}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="room_id" label="对端设备所在机房">
              <Select
                placeholder="请选择机房"
                options={roomOptions}
                allowClear
                onChange={() => {
                  form.setFieldsValue({ cabinet_id: undefined, switch_device_id: undefined });
                }}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="cabinet_id" label="机柜">
              <Select
                placeholder="请选择机柜"
                options={cabinetOptions}
                allowClear
                showSearch
                optionFilterProp="label"
                disabled={!selectedRoomId}
                onChange={() => {
                  form.setFieldsValue({ switch_device_id: undefined });
                }}
              />
            </Form.Item>
          </Col>
        </Row>

        {}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="switch_device_id"
              label="对端设备"
              rules={[{ required: true, message: '请选择对端设备' }]}
            >
              <Select
                placeholder="请选择设备"
                options={switchOptions}
                allowClear
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name={isNetworkDevice ? 'peer_port_id' : 'switch_port_id'}
              label="对端端口"
              rules={[{ required: true, message: '请选择对端端口' }]}
            >
              <Select
                placeholder={selectedSwitchId ? '请选择端口' : '请先选择对端设备'}
                options={peerPortOptions}
                allowClear
                showSearch
                optionFilterProp="label"
                disabled={!selectedSwitchId}
              />
            </Form.Item>
          </Col>
        </Row>

        {}
        {!isNetworkDevice && (
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="device_nics_port_id" label="本机网卡端口">
                <Select
                  placeholder="请选择网卡端口"
                  options={nicPortOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
          </Row>
        )}

        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
