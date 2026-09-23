/**
 * ConnectionFormModal — 新增连接表单 Modal
 *
 * 从 ConnectionTab.tsx 拆出。复用父级 form 实例（父级负责提交与校验），
 * 内部通过 Form.useWatch 监听 room/cabinet/switch 联动以控制禁用与占位文案。
 */
import { Form, Modal, Select, Input, Row, Col } from 'antd';
import type { FormInstance, SelectProps } from 'antd';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const selectedRoomId = Form.useWatch('room_id', form);
  const selectedCabinetId = Form.useWatch('cabinet_id', form);
  const selectedSwitchId = Form.useWatch('switch_device_id', form);

  return (
    <Modal
      title={t('connection.action.add')}
      open={open}
      onOk={onOk}
      onCancel={onCancel}
      width={700}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="link_type" label={t('connection.column.linkType')}>
              <Select placeholder={tCommon('message.selectRequired')} options={linkTypeOptions} disabled />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="connection_type" label={t('connection.column.connectionType')}>
              <Select
                placeholder={tCommon('message.selectRequired')}
                options={connectionTypeOptions}
                allowClear
              />
            </Form.Item>
          </Col>
        </Row>

        {/* ── network_to_network: 本机端口选择 ── */}
        {isNetworkDevice && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="switch_port_id"
                label={t('connection.column.localPort')}
                rules={[{ required: true, message: t('connection.form.selectLocalPort') }]}
              >
                <Select
                  placeholder={t('connection.form.selectLocalPort')}
                  options={localPortOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
          </Row>
        )}

        {/* ── 机房 + 机柜筛选 ── */}
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="room_id" label={t('connection.form.peerDeviceRoom')}>
              <Select
                placeholder={t('connection.form.selectRoom')}
                options={roomOptions}
                allowClear
                onChange={() => {
                  form.setFieldsValue({ cabinet_id: undefined, switch_device_id: undefined });
                }}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="cabinet_id" label={t('field.cabinet')}>
              <Select
                placeholder={t('connection.form.selectCabinet')}
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

        {/* ── 对端设备选择 + 对端端口选择 ── */}
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item
              name="switch_device_id"
              label={t('connection.column.peerDevice')}
              rules={[{ required: true, message: t('connection.form.selectPeerDevice') }]}
            >
              <Select
                placeholder={t('connection.form.selectDevice')}
                options={switchOptions}
                allowClear
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name={isNetworkDevice ? 'peer_port_id' : 'switch_port_id'}
              label={t('connection.column.peerPort')}
              rules={[{ required: true, message: t('connection.form.selectPeerPort') }]}
            >
              <Select
                placeholder={
                  selectedSwitchId
                    ? t('connection.form.selectPort')
                    : t('connection.form.selectPeerDeviceFirst')
                }
                options={peerPortOptions}
                allowClear
                showSearch
                optionFilterProp="label"
                disabled={!selectedSwitchId}
              />
            </Form.Item>
          </Col>
        </Row>

        {/* ── device_to_network: 本机网卡端口选择 ── */}
        {!isNetworkDevice && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="device_nics_port_id" label={t('connection.form.localNicPort')}>
                <Select
                  placeholder={t('connection.form.selectNicPort')}
                  options={nicPortOptions}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
          </Row>
        )}

        <Form.Item name="notes" label={tCommon('field.remarks')}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
