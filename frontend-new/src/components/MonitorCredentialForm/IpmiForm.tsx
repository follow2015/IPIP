/**
 * IPMI 凭据子表单（Redfish 已停用，BMC 兜底统一走 IPMI）。
 * 仅渲染 Form.Item，依赖父级 <Form> 上下文。
 */
import { Form, Input, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
const { Password } = Input;

export default function IpmiForm({ mode }: { mode: 'create' | 'edit' }) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const isEdit = mode === 'edit';
  const required = isEdit ? [] : [{ required: true, message: tCommon('validation.required') }];

  return (
    <>
      <Form.Item label={t('credential.form.username')} name="username" rules={required}>
        <Input />
      </Form.Item>
      <Form.Item label={t('credential.form.password')} name="password" rules={required}>
        <Password placeholder={isEdit ? t('credential.form.keepUnchanged') : undefined} />
      </Form.Item>
      <Form.Item
        label={t('credential.form.verifySslIpmi')}
        name="verify_ssl"
        valuePropName="checked"
        tooltip={t('credential.form.verifySslTooltip')}
      >
        <Switch />
      </Form.Item>
    </>
  );
}
