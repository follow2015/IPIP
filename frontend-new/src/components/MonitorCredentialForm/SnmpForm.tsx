/**
 * SNMP 凭据子表单（v2c / v3 动态切换）。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文（Form.useWatch 取 snmp_version）。
 */
import { Form, Input, Select } from 'antd';
const { Password } = Input;

const KEEP_PLACEHOLDER = '留空保持不变';

export default function SnmpForm({ mode }: { mode: 'create' | 'edit' }) {
  const snmpVersion = (Form.useWatch('snmp_version') as string) || 'v2c';
  const isEdit = mode === 'edit';
  const required = isEdit ? [] : [{ required: true, message: '此项必填' }];

  return (
    <>
      <Form.Item label="SNMP 版本" name="snmp_version">
        <Select
          options={[
            { value: 'v2c', label: 'v2c' },
            { value: 'v3', label: 'v3' }
          ]}
        />
      </Form.Item>

      {snmpVersion === 'v2c' ? (
        <Form.Item label="Community" name="community" rules={required}>
          <Password placeholder={isEdit ? KEEP_PLACEHOLDER : 'public'} />
        </Form.Item>
      ) : (
        <>
          <Form.Item label="用户名" name="username" rules={required}>
            <Input />
          </Form.Item>
          <Form.Item label="认证密钥 (Auth Key)" name="auth_key" rules={required}>
            <Password placeholder={isEdit ? KEEP_PLACEHOLDER : undefined} />
          </Form.Item>
          <Form.Item label="认证协议" name="auth_protocol">
            <Select
              options={[
                { value: 'sha', label: 'SHA' },
                { value: 'sha256', label: 'SHA-256' },
                { value: 'sha512', label: 'SHA-512' },
                { value: 'md5', label: 'MD5' },
                { value: 'none', label: '无' }
              ]}
            />
          </Form.Item>
          <Form.Item label="加密密钥 (Priv Key)" name="priv_key">
            <Password placeholder={isEdit ? KEEP_PLACEHOLDER : '无加密时留空'} />
          </Form.Item>
          <Form.Item label="加密协议" name="priv_protocol">
            <Select
              options={[
                { value: 'aes', label: 'AES' },
                { value: 'aes256', label: 'AES-256' },
                { value: 'des', label: 'DES' },
                { value: '3des', label: '3DES' },
                { value: 'none', label: '无' }
              ]}
            />
          </Form.Item>
        </>
      )}
    </>
  );
}
