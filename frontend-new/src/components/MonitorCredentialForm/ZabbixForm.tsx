/**
 * Zabbix 凭据子表单。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文。
 */
import { Form, Input, Select, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
const { Password } = Input;

export default function ZabbixForm({ mode }: { mode: 'create' | 'edit' }) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const isEdit = mode === 'edit';
  const keepPlaceholder = t('credential.form.keepUnchanged');
  const required = isEdit ? [] : [{ required: true, message: tCommon('validation.required') }];

  return (
    <>
      <Form.Item label={t('credential.form.apiUrl')} name="api_url" rules={required}>
        <Input placeholder="https://zabbix.example.com/api_jsonrpc.php" />
      </Form.Item>
      <Form.Item label={t('credential.form.apiToken')} name="api_token" rules={required}>
        <Password placeholder={isEdit ? keepPlaceholder : undefined} />
      </Form.Item>
      <Form.Item label={t('credential.form.verifySsl')} name="verify_ssl" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Form.Item label={t('credential.form.matchBy.label')} name="match_by">
        <Select
          allowClear
          placeholder={t('credential.form.matchBy.placeholder')}
          options={[
            { value: 'host', label: t('credential.form.matchBy.host') },
            { value: 'ip', label: t('credential.form.matchBy.ip') }
          ]}
        />
      </Form.Item>
    </>
  );
}
