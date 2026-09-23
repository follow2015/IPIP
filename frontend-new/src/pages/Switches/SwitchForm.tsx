/**
 * 交换机表单（编辑 Modal - 简化版）
 * 仅用于有管理权限的交换机快速编辑，不含位置区域和拓扑字段
 * 拓扑字段（上行设备/核心交换机等）通过"完整编辑"按钮在 DeviceForm 中管理
 * 布局：两列并列，提升表单可读性和空间利用率
 */
import { useEffect } from 'react';
import { Modal, Form, Input, Select, InputNumber, Row, Col, Switch as AntSwitch } from 'antd';
import { useUpdateSwitch } from '@/services/switch';
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

interface SwitchFormProps {
  open: boolean;
  editRecord: Switch | null;
  onClose: () => void;
}

function SwitchForm({ open, editRecord, onClose }: SwitchFormProps) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const [form] = Form.useForm();
  const message = useMessage();
  const updateSwitch = useUpdateSwitch();

  useEffect(() => {
    if (open) {
      if (editRecord) {
        form.setFieldsValue({
          name: editRecord.name,
          ip: editRecord.ip_address,
          port: editRecord.port,
          protocol: editRecord.protocol,
          username: editRecord.username,
          device_type: editRecord.device_type,
          device_model: editRecord.device_model,
          switch_role: editRecord.switch_role,
          layer: editRecord.layer,
          authentication_method: editRecord.authentication_method,
          has_ssh: editRecord.has_ssh
        });
      } else {
        form.resetFields();
      }
    }
  }, [open, editRecord, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const protocol = values.protocol ?? 'ssh';
      const port = values.port ?? (protocol === 'telnet' ? 23 : 22);
      const payload = {
        ...values,
        port,
        switch_role: values.switch_role ?? 1,
        layer: values.layer ?? 2,
        authentication_method: values.authentication_method ?? 'password'
      };
      if (!values.password) {
        delete payload.password;
      } else {
        payload.password = values.password;
      }
      await updateSwitch.mutateAsync({ id: editRecord!.device_id, data: payload });
      message.success(tc('message.updateSuccess'));
      onClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal
      title={td('switch.form.editTitle')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={updateSwitch.isPending}
      destroyOnHidden
      width={720}
    >
      <Form form={form} layout="vertical">
        <Row gutter={24}>
          {/* 第一行：交换机名称 + 管理IP */}
          <Col xs={24} md={12}>
            <Form.Item
              name="name"
              label={td('switch.form.name')}
              rules={[{ required: true, message: td('switch.form.nameRequired') }]}
            >
              <Input placeholder={td('switch.form.name')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="ip"
              label={td('field.managementIp')}
              rules={[
                { required: true, message: td('switch.form.managementIpRequired') },
                {
                  pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
                  message: td('switch.form.ipFormatInvalid')
                }
              ]}
            >
              <Input placeholder={td('switch.form.managementIpPlaceholder')} />
            </Form.Item>
          </Col>

          {/* 第二行：端口号 + 协议 */}
          <Col xs={24} md={12}>
            <Form.Item
              name="port"
              label={td('switch.form.port')}
              extra={td('switch.form.portExtra')}
            >
              <InputNumber
                min={1}
                max={65535}
                style={{ width: '100%' }}
                placeholder={td('switch.form.portPlaceholder')}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="protocol"
              label={td('switch.field.protocol')}
              rules={[{ required: true, message: td('switch.form.protocolRequired') }]}
            >
              <Select placeholder={tc('message.selectRequired')} options={SSH_PROTOCOL_OPTIONS} />
            </Form.Item>
          </Col>

          {/* 第三行：用户名 + 密码 */}
          <Col xs={24} md={12}>
            <Form.Item
              name="username"
              label={td('credential.form.username')}
              rules={[{ required: true, message: td('switch.form.usernameRequired') }]}
            >
              <Input placeholder={td('switch.form.usernamePlaceholder')} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="password"
              label={td('switch.form.password')}
              extra={td('switch.form.passwordExtra')}
            >
              <Input.Password placeholder={td('switch.form.passwordPlaceholder')} />
            </Form.Item>
          </Col>

          {/* 第四行：设备类型 + 型号 */}
          <Col xs={24} md={12}>
            <Form.Item
              name="device_type"
              label={td('basic.field.deviceType')}
              rules={[{ required: true, message: td('switch.form.deviceTypeRequired') }]}
            >
              <Select placeholder={tc('message.selectRequired')} options={getSwitchDeviceTypeOptions(td)} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="device_model" label={td('basic.field.model')}>
              <Input placeholder={td('basic.field.model')} />
            </Form.Item>
          </Col>

          {/* 第五行：交换机类型 + 网络层级 */}
          <Col xs={24} md={12}>
            <Form.Item
              name="switch_role"
              label={td('switch.form.switchType')}
              rules={[{ required: true, message: td('switch.form.switchTypeRequired') }]}
            >
              <Select placeholder={tc('message.selectRequired')} options={getSwitchRoleOptions(td)} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="layer"
              label={td('switch.form.networkLayer')}
              rules={[{ required: true, message: td('switch.form.networkLayerRequired') }]}
              initialValue={2}
            >
              <Select placeholder={tc('message.selectRequired')} options={getNetworkLayerOptions(td)} />
            </Form.Item>
          </Col>

          {/* 第六行：认证方法 + has_ssh 管理权限开关 */}
          <Col xs={24} md={12}>
            <Form.Item
              name="authentication_method"
              label={td('switch.form.authMethod')}
              rules={[{ required: true, message: td('switch.form.authMethodRequired') }]}
            >
              <Select placeholder={tc('message.selectRequired')} options={getAuthMethodOptions(td)} />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="has_ssh"
              label={td('form.network.managementAccess.label')}
              valuePropName="checked"
              initialValue={false}
            >
              <AntSwitch
                checkedChildren={td('port.state.on')}
                unCheckedChildren={td('port.state.off')}
              />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

export default SwitchForm;
