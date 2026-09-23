/**
 * 批量修改交换机远程信息弹窗
 * 支持批量修改：端口号、协议、用户名、密码、设备类型、交换机类型、网络层级、认证方法
 * 仅提交用户勾选的字段，未勾选的字段不会被发送到后端
 */
import { Modal, Form, Input, Select, InputNumber, Row, Col, Checkbox, Space, Alert } from 'antd';
import { useBatchUpdateSwitch, type BatchUpdateSwitchResult } from '@/services/switch';
import { SSH_PROTOCOL_OPTIONS } from '@/types/enums';
import {
  getAuthMethodOptions,
  getNetworkLayerOptions,
  getSwitchDeviceTypeOptions,
  getSwitchRoleOptions
} from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { Switch } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { useState } from 'react';

const EDITABLE_FIELDS = [
  'port',
  'protocol',
  'username',
  'password',
  'device_type',
  'switch_role',
  'layer',
  'authentication_method'
] as const;

type EditableField = (typeof EDITABLE_FIELDS)[number];

type BatchFieldLabelKey =
  | 'switch.batchField.port'
  | 'switch.batchField.protocol'
  | 'switch.batchField.username'
  | 'switch.batchField.password'
  | 'switch.batchField.deviceType'
  | 'switch.batchField.switchRole'
  | 'switch.batchField.layer'
  | 'switch.batchField.authenticationMethod';

const FIELD_LABELS: Record<EditableField, BatchFieldLabelKey> = {
  port: 'switch.batchField.port',
  protocol: 'switch.batchField.protocol',
  username: 'switch.batchField.username',
  password: 'switch.batchField.password',
  device_type: 'switch.batchField.deviceType',
  switch_role: 'switch.batchField.switchRole',
  layer: 'switch.batchField.layer',
  authentication_method: 'switch.batchField.authenticationMethod'
};

interface BatchUpdateSwitchModalProps {
  open: boolean;
  selectedSwitches: Switch[];
  onClose: () => void;
}

function BatchUpdateSwitchModal({ open, selectedSwitches, onClose }: BatchUpdateSwitchModalProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const [form] = Form.useForm();
  const message = useMessage();
  const batchUpdate = useBatchUpdateSwitch();
  const [checkedFields, setCheckedFields] = useState<Set<EditableField>>(new Set());
  const [partialResult, setPartialResult] = useState<BatchUpdateSwitchResult | null>(null);

  const handleCheckChange = (field: EditableField, checked: boolean) => {
    setCheckedFields((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(field);
      } else {
        next.delete(field);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (checkedFields.size === 0) {
      message.warning(td('switch.batchUpdate.selectFieldRequired'));
      return;
    }

    try {
      const values = await form.validateFields();
      const deviceIds = selectedSwitches.map((s) => s.device_id);

      const updates: Record<string, unknown> = {};
      for (const field of checkedFields) {
        if (field === 'port') {
          const protocol = values.protocol ?? 'ssh';
          updates.port = values.port ?? (protocol === 'telnet' ? 23 : 22);
        } else if (field === 'password') {
          if (values.password) {
            updates.password = values.password;
          } else {
            message.warning(td('switch.batchUpdate.passwordEmptySkipped'));
          }
        } else {
          updates[field] = values[field];
        }
      }

      const result = await batchUpdate.mutateAsync({ device_ids: deviceIds, updates });

      if (result.failed_count > 0) {
        setPartialResult(result);
        message.warning(
          td('switch.batchUpdate.partialSuccess', {
            success: result.success_count,
            failed: result.failed_count
          })
        );
      } else {
        message.success(
          td('switch.batchUpdate.success', { count: result.success_count })
        );
        handleClose();
      }
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const handleClose = () => {
    form.resetFields();
    setCheckedFields(new Set());
    setPartialResult(null);
    onClose();
  };

  return (
    <Modal
      title={td('switch.batchUpdate.title', { count: selectedSwitches.length })}
      open={open}
      onOk={handleSubmit}
      onCancel={handleClose}
      confirmLoading={batchUpdate.isPending}
      destroyOnHidden
      width={720}
    >
      {partialResult && partialResult.failed_count > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={td('switch.batchUpdate.resultSummary', {
            success: partialResult.success_count,
            failed: partialResult.failed_count
          })}
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {partialResult.failed_items.map((item) => (
                <li key={item.device_id}>
                  {td('switch.batchUpdate.failedItem', {
                    id: item.device_id,
                    error: item.error
                  })}
                </li>
              ))}
            </ul>
          }
          closable
          onClose={() => setPartialResult(null)}
        />
      )}

      <Form form={form} layout="vertical">
        <Row gutter={24}>
          {/* 端口号 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('port')}
                    onChange={(e) => handleCheckChange('port', e.target.checked)}
                  />
                  {td(FIELD_LABELS.port)}
                </Space>
              }
            >
              <Form.Item name="port" noStyle>
                <InputNumber
                  min={1}
                  max={65535}
                  style={{ width: '100%' }}
                  placeholder={td('switch.form.portPlaceholder')}
                  disabled={!checkedFields.has('port')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 协议 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('protocol')}
                    onChange={(e) => handleCheckChange('protocol', e.target.checked)}
                  />
                  {td(FIELD_LABELS.protocol)}
                </Space>
              }
            >
              <Form.Item
                name="protocol"
                noStyle
                rules={
                  checkedFields.has('protocol')
                    ? [{ required: true, message: td('switch.form.protocolRequired') }]
                    : []
                }
              >
                <Select
                  placeholder={tc('message.selectRequired')}
                  options={SSH_PROTOCOL_OPTIONS}
                  disabled={!checkedFields.has('protocol')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 用户名 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('username')}
                    onChange={(e) => handleCheckChange('username', e.target.checked)}
                  />
                  {td(FIELD_LABELS.username)}
                </Space>
              }
            >
              <Form.Item
                name="username"
                noStyle
                rules={
                  checkedFields.has('username')
                    ? [{ required: true, message: td('switch.form.usernameRequired') }]
                    : []
                }
              >
                <Input
                  placeholder={td('switch.form.usernamePlaceholder')}
                  disabled={!checkedFields.has('username')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 密码 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('password')}
                    onChange={(e) => handleCheckChange('password', e.target.checked)}
                  />
                  {td(FIELD_LABELS.password)}
                </Space>
              }
            >
              <Form.Item name="password" noStyle>
                <Input.Password
                  placeholder={td('switch.form.passwordPlaceholder')}
                  disabled={!checkedFields.has('password')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 设备类型 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('device_type')}
                    onChange={(e) => handleCheckChange('device_type', e.target.checked)}
                  />
                  {td(FIELD_LABELS.device_type)}
                </Space>
              }
            >
              <Form.Item
                name="device_type"
                noStyle
                rules={
                  checkedFields.has('device_type')
                    ? [{ required: true, message: td('switch.form.deviceTypeRequired') }]
                    : []
                }
              >
                <Select
                  placeholder={tc('message.selectRequired')}
                  options={getSwitchDeviceTypeOptions(td)}
                  disabled={!checkedFields.has('device_type')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 交换机类型 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('switch_role')}
                    onChange={(e) => handleCheckChange('switch_role', e.target.checked)}
                  />
                  {td(FIELD_LABELS.switch_role)}
                </Space>
              }
            >
              <Form.Item
                name="switch_role"
                noStyle
                rules={
                  checkedFields.has('switch_role')
                    ? [{ required: true, message: td('switch.form.switchRoleRequired') }]
                    : []
                }
              >
                <Select
                  placeholder={tc('message.selectRequired')}
                  options={getSwitchRoleOptions(td)}
                  disabled={!checkedFields.has('switch_role')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 网络层级 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('layer')}
                    onChange={(e) => handleCheckChange('layer', e.target.checked)}
                  />
                  {td(FIELD_LABELS.layer)}
                </Space>
              }
            >
              <Form.Item
                name="layer"
                noStyle
                rules={
                  checkedFields.has('layer')
                    ? [{ required: true, message: td('switch.form.networkLayerRequired') }]
                    : []
                }
              >
                <Select
                  placeholder={tc('message.selectRequired')}
                  options={getNetworkLayerOptions(td)}
                  disabled={!checkedFields.has('layer')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {/* 认证方法 */}
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('authentication_method')}
                    onChange={(e) => handleCheckChange('authentication_method', e.target.checked)}
                  />
                  {td(FIELD_LABELS.authentication_method)}
                </Space>
              }
            >
              <Form.Item
                name="authentication_method"
                noStyle
                rules={
                  checkedFields.has('authentication_method')
                    ? [{ required: true, message: td('switch.form.authMethodRequired') }]
                    : []
                }
              >
                <Select
                  placeholder={tc('message.selectRequired')}
                  options={getAuthMethodOptions(td)}
                  disabled={!checkedFields.has('authentication_method')}
                />
              </Form.Item>
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

export default BatchUpdateSwitchModal;
