/**
 * SNMP 凭据子表单（v2c / v3 动态切换）。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文（Form.useWatch 取 snmp_version）。
 */
import { Form, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
const { Password } = Input;

export default function SnmpForm({ mode }: { mode: 'create' | 'edit' }) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const snmpVersion = (Form.useWatch('snmp_version') as string) || 'v2c';
  const isEdit = mode === 'edit';
  const keepPlaceholder = t('credential.form.keepUnchanged');
  const required = isEdit ? [] : [{ required: true, message: tCommon('validation.required') }];

  return (
    <>
      <Form.Item label={t('credential.form.snmpVersion')} name="snmp_version">
        <Select
          options={[
            { value: 'v2c', label: 'v2c' },
            { value: 'v3', label: 'v3' }
          ]}
        />
      </Form.Item>

      {snmpVersion === 'v2c' ? (
        <Form.Item label="Community" name="community" rules={required}>
          <Password placeholder={isEdit ? keepPlaceholder : 'public'} />
        </Form.Item>
      ) : (
        <>
          <Form.Item label={t('credential.form.username')} name="username" rules={required}>
            <Input />
          </Form.Item>
          <Form.Item label={t('credential.form.authKey')} name="auth_key" rules={required}>
            <Password placeholder={isEdit ? keepPlaceholder : undefined} />
          </Form.Item>
          <Form.Item label={t('credential.form.authProtocol')} name="auth_protocol">
            <Select
              options={[
                { value: 'sha', label: 'SHA' },
                { value: 'sha256', label: 'SHA-256' },
                { value: 'sha512', label: 'SHA-512' },
                { value: 'md5', label: 'MD5' },
                { value: 'none', label: t('credential.form.none') }
              ]}
            />
          </Form.Item>
          <Form.Item label={t('credential.form.privKey')} name="priv_key">
            <Password
              placeholder={
                isEdit ? keepPlaceholder : t('credential.form.privKeyPlaceholder')
              }
            />
          </Form.Item>
          <Form.Item label={t('credential.form.privProtocol')} name="priv_protocol">
            <Select
              options={[
                { value: 'aes', label: 'AES' },
                { value: 'aes256', label: 'AES-256' },
                { value: 'des', label: 'DES' },
                { value: '3des', label: '3DES' },
                { value: 'none', label: t('credential.form.none') }
              ]}
            />
          </Form.Item>
        </>
      )}
    </>
  );
}
