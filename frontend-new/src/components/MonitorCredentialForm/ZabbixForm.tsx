/**
 * Zabbix 凭据子表单。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文。
 */
import { Form, Input, Select, Switch } from 'antd';
const { Password } = Input;

const KEEP_PLACEHOLDER = '留空保持不变';

export default function ZabbixForm({ mode }: { mode: 'create' | 'edit' }) {
  const isEdit = mode === 'edit';
  const required = isEdit ? [] : [{ required: true, message: '此项必填' }];

  return (
    <>
      <Form.Item label="API 地址" name="api_url" rules={required}>
        <Input placeholder="https://zabbix.example.com/api_jsonrpc.php" />
      </Form.Item>
      <Form.Item label="API Token" name="api_token" rules={required}>
        <Password placeholder={isEdit ? KEEP_PLACEHOLDER : undefined} />
      </Form.Item>
      <Form.Item label="验证 SSL" name="verify_ssl" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Form.Item label="匹配方式" name="match_by">
        <Select
          allowClear
          placeholder="默认按 host"
          options={[
            { value: 'host', label: '主机名' },
            { value: 'ip', label: 'IP 地址' }
          ]}
        />
      </Form.Item>
    </>
  );
}
