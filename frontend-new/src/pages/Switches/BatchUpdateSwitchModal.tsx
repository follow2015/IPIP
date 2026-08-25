/**
 * 批量修改交换机远程信息弹窗
 * 支持批量修改：端口号、协议、用户名、密码、设备类型、交换机类型、网络层级、认证方法
 * 仅提交用户勾选的字段，未勾选的字段不会被发送到后端
 */
import { Modal, Form, Input, Select, InputNumber, Row, Col, Checkbox, Space, Alert } from 'antd';
import { useBatchUpdateSwitch, type BatchUpdateSwitchResult } from '@/services/switch';
import {
  SWITCH_ROLE_MAP,
  SWITCH_DEVICE_TYPE_OPTIONS,
  AUTH_METHOD_OPTIONS,
  SSH_PROTOCOL_OPTIONS,
  NETWORK_LAYER_OPTIONS
} from '@/types/enums';
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


const FIELD_LABELS: Record<EditableField, string> = {
  port: '端口号',
  protocol: '协议',
  username: '用户名',
  password: '密码',
  device_type: '设备类型',
  switch_role: '设备角色',
  layer: '网络层级',
  authentication_method: '认证方法'
};

interface BatchUpdateSwitchModalProps {
  open: boolean;
  selectedSwitches: Switch[];
  onClose: () => void;
}

function BatchUpdateSwitchModal({ open, selectedSwitches, onClose }: BatchUpdateSwitchModalProps) {
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
      message.warning('请至少勾选一个要修改的字段');
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
            message.warning('已勾选密码字段，但密码为空，将跳过密码更新');
          }
        } else {
          updates[field] = values[field];
        }
      }

      const result = await batchUpdate.mutateAsync({ device_ids: deviceIds, updates });

      if (result.failed_count > 0) {
        setPartialResult(result);
        message.warning(`部分更新成功：${result.success_count} 成功，${result.failed_count} 失败`);
      } else {
        message.success(`批量更新成功：${result.success_count} 台网络设备已更新`);
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
      title={`批量修改远程信息（已选 ${selectedSwitches.length} 台）`}
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
          message={`${partialResult.success_count} 台更新成功，${partialResult.failed_count} 台失败`}
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {partialResult.failed_items.map((item) => (
                <li key={item.device_id}>
                  设备ID {item.device_id}：{item.error}
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
          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('port')}
                    onChange={(e) => handleCheckChange('port', e.target.checked)}
                  />
                  {FIELD_LABELS.port}
                </Space>
              }
            >
              <Form.Item name="port" noStyle>
                <InputNumber
                  min={1}
                  max={65535}
                  style={{ width: '100%' }}
                  placeholder="默认按协议自动填充"
                  disabled={!checkedFields.has('port')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('protocol')}
                    onChange={(e) => handleCheckChange('protocol', e.target.checked)}
                  />
                  {FIELD_LABELS.protocol}
                </Space>
              }
            >
              <Form.Item
                name="protocol"
                noStyle
                rules={
                  checkedFields.has('protocol') ? [{ required: true, message: '请选择协议' }] : []
                }
              >
                <Select
                  placeholder="请选择"
                  options={SSH_PROTOCOL_OPTIONS}
                  disabled={!checkedFields.has('protocol')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('username')}
                    onChange={(e) => handleCheckChange('username', e.target.checked)}
                  />
                  {FIELD_LABELS.username}
                </Space>
              }
            >
              <Form.Item
                name="username"
                noStyle
                rules={
                  checkedFields.has('username') ? [{ required: true, message: '请输入用户名' }] : []
                }
              >
                <Input placeholder="登录用户名" disabled={!checkedFields.has('username')} />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('password')}
                    onChange={(e) => handleCheckChange('password', e.target.checked)}
                  />
                  {FIELD_LABELS.password}
                </Space>
              }
            >
              <Form.Item name="password" noStyle>
                <Input.Password
                  placeholder="留空则不修改"
                  disabled={!checkedFields.has('password')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('device_type')}
                    onChange={(e) => handleCheckChange('device_type', e.target.checked)}
                  />
                  {FIELD_LABELS.device_type}
                </Space>
              }
            >
              <Form.Item
                name="device_type"
                noStyle
                rules={
                  checkedFields.has('device_type')
                    ? [{ required: true, message: '请选择设备类型' }]
                    : []
                }
              >
                <Select
                  placeholder="请选择"
                  options={SWITCH_DEVICE_TYPE_OPTIONS}
                  disabled={!checkedFields.has('device_type')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('switch_role')}
                    onChange={(e) => handleCheckChange('switch_role', e.target.checked)}
                  />
                  {FIELD_LABELS.switch_role}
                </Space>
              }
            >
              <Form.Item
                name="switch_role"
                noStyle
                rules={
                  checkedFields.has('switch_role')
                    ? [{ required: true, message: '请选择设备角色' }]
                    : []
                }
              >
                <Select
                  placeholder="请选择"
                  options={Object.entries(SWITCH_ROLE_MAP).map(([k, v]) => ({
                    label: v.label,
                    value: Number(k)
                  }))}
                  disabled={!checkedFields.has('switch_role')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('layer')}
                    onChange={(e) => handleCheckChange('layer', e.target.checked)}
                  />
                  {FIELD_LABELS.layer}
                </Space>
              }
            >
              <Form.Item
                name="layer"
                noStyle
                rules={
                  checkedFields.has('layer') ? [{ required: true, message: '请选择网络层级' }] : []
                }
              >
                <Select
                  placeholder="请选择"
                  options={NETWORK_LAYER_OPTIONS}
                  disabled={!checkedFields.has('layer')}
                />
              </Form.Item>
            </Form.Item>
          </Col>

          {}
          <Col span={12}>
            <Form.Item
              label={
                <Space>
                  <Checkbox
                    checked={checkedFields.has('authentication_method')}
                    onChange={(e) => handleCheckChange('authentication_method', e.target.checked)}
                  />
                  {FIELD_LABELS.authentication_method}
                </Space>
              }
            >
              <Form.Item
                name="authentication_method"
                noStyle
                rules={
                  checkedFields.has('authentication_method')
                    ? [{ required: true, message: '请选择认证方法' }]
                    : []
                }
              >
                <Select
                  placeholder="请选择"
                  options={[...AUTH_METHOD_OPTIONS]}
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
