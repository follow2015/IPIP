/**
 * 交换机表单（编辑 Modal - 简化版）
 * 仅用于有管理权限的交换机快速编辑，不含位置区域和拓扑字段
 * 拓扑字段（上行设备/核心交换机等）通过"完整编辑"按钮在 DeviceForm 中管理
 * 布局：两列并列，提升表单可读性和空间利用率
 */
import { useEffect } from 'react';
import { Modal, Form, Input, Select, InputNumber, Row, Col, Switch as AntSwitch } from 'antd';
import { useUpdateSwitch } from '@/services/switch';
import {
  SWITCH_ROLE_MAP,
  SWITCH_DEVICE_TYPE_OPTIONS,
  AUTH_METHOD_OPTIONS,
  SSH_PROTOCOL_OPTIONS,
  NETWORK_LAYER_OPTIONS
} from '@/types/enums';
import type { Switch } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';

interface SwitchFormProps {
  open: boolean;
  editRecord: Switch | null;
  onClose: () => void;
}

function SwitchForm({ open, editRecord, onClose }: SwitchFormProps) {
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
      message.success('更新成功');
      onClose();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal
      title="编辑交换机"
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
          <Col span={12}>
            <Form.Item
              name="name"
              label="交换机名称"
              rules={[{ required: true, message: '请输入名称' }]}
            >
              <Input placeholder="交换机名称" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="ip"
              label="管理IP"
              rules={[
                { required: true, message: '请输入管理IP' },
                { pattern: /^(\d{1,3}\.){3}\d{1,3}$/, message: 'IP格式不正确' }
              ]}
            >
              <Input placeholder="管理IP地址" />
            </Form.Item>
          </Col>

          {/* 第二行：端口号 + 协议 */}
          <Col span={12}>
            <Form.Item name="port" label="端口号" extra="留空则按协议自动填充：SSH→22，Telnet→23">
              <InputNumber
                min={1}
                max={65535}
                style={{ width: '100%' }}
                placeholder="默认按协议自动填充"
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="protocol"
              label="协议"
              rules={[{ required: true, message: '请选择协议' }]}
            >
              <Select placeholder="请选择" options={SSH_PROTOCOL_OPTIONS} />
            </Form.Item>
          </Col>

          {/* 第三行：用户名 + 密码 */}
          <Col span={12}>
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input placeholder="登录用户名" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="password" label="密码" extra="留空则不修改密码">
              <Input.Password placeholder="留空则不修改" />
            </Form.Item>
          </Col>

          {/* 第四行：设备类型 + 型号 */}
          <Col span={12}>
            <Form.Item
              name="device_type"
              label="设备类型"
              rules={[{ required: true, message: '请选择设备类型' }]}
            >
              <Select placeholder="请选择" options={SWITCH_DEVICE_TYPE_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="device_model" label="型号">
              <Input placeholder="型号" />
            </Form.Item>
          </Col>

          {/* 第五行：交换机类型 + 网络层级 */}
          <Col span={12}>
            <Form.Item
              name="switch_role"
              label="交换机类型"
              rules={[{ required: true, message: '请选择交换机类型' }]}
            >
              <Select
                placeholder="请选择"
                options={Object.entries(SWITCH_ROLE_MAP).map(([k, v]) => ({
                  label: v.label,
                  value: Number(k)
                }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="layer"
              label="网络层级"
              rules={[{ required: true, message: '请选择网络层级' }]}
              initialValue={2}
            >
              <Select placeholder="请选择" options={NETWORK_LAYER_OPTIONS} />
            </Form.Item>
          </Col>

          {/* 第六行：认证方法 + has_ssh 管理权限开关 */}
          <Col span={12}>
            <Form.Item
              name="authentication_method"
              label="认证方法"
              rules={[{ required: true, message: '请选择认证方法' }]}
            >
              <Select placeholder="请选择" options={AUTH_METHOD_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="has_ssh" label="管理权限" valuePropName="checked" initialValue={false}>
              <AntSwitch checkedChildren="开" unCheckedChildren="关" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

export default SwitchForm;
