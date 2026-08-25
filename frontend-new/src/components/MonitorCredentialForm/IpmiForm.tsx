/**
 * IPMI 凭据子表单（Redfish 已停用，BMC 兜底统一走 IPMI）。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文。
 */
import { Form, Input, Switch } from 'antd';
const { Password } = Input;

const KEEP_PLACEHOLDER = '留空保持不变';

export default function IpmiForm({ mode }: { mode: 'create' | 'edit' }) {
  const isEdit = mode === 'edit';
  const required = isEdit ? [] : [{ required: true, message: '此项必填' }];

  return (
    <>
      <Form.Item label="用户名" name="username" rules={required}>
        <Input />
      </Form.Item>
      <Form.Item label="密码" name="password" rules={required}>
        <Password placeholder={isEdit ? KEEP_PLACEHOLDER : undefined} />
      </Form.Item>
      <Form.Item
        label="验证SSL证书"
        name="verify_ssl"
        valuePropName="checked"
        tooltip="BMC通常使用自签名证书，默认关闭"
      >
        <Switch />
      </Form.Item>
    </>
  );
}
