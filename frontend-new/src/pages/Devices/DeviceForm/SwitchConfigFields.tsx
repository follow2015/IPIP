/**
 * SwitchConfigFields — 设备「交换机配置」表单区块（Card）
 *
 * 从原 DeviceForm.tsx 拆出。纯表单字段区块，复用父级 <Form> 上下文。
 * 仅网络设备且开启管理权限（has_ssh）时由父级条件渲染。
 */
import { Form, Input, InputNumber, Select, Card, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import { SSH_PROTOCOL_OPTIONS } from '@/types/enums';
import { getSwitchDeviceTypeOptions, getAuthMethodOptions } from '@/types/statusMeta';

interface SwitchConfigFieldsProps {
  isEdit: boolean;
}

export default function SwitchConfigFields({ isEdit }: SwitchConfigFieldsProps) {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  return (
    <Card
      title={t('form.section.switchConfig')}
      size="small"
      style={{ marginBottom: 16 }}
      styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
    >
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'ip']}
            label={t('field.managementIp')}
          >
            <Input placeholder={t('form.switchConfig.managementIp.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'port']}
            label={t('form.switchConfig.sshPort.label')}
            initialValue={22}
          >
            <InputNumber
              min={1}
              max={65535}
              style={{ width: '100%' }}
              placeholder={t('form.switchConfig.sshPort.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'protocol']}
            label={t('credential.protocol')}
            initialValue="ssh"
          >
            <Select placeholder={tCommon('message.selectRequired')} options={SSH_PROTOCOL_OPTIONS} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'username']}
            label={t('credential.form.username')}
          >
            <Input placeholder={t('form.switchConfig.username.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'password']}
            label={t('credential.form.password')}
            extra={isEdit ? t('form.switchConfig.password.keepUnchanged') : undefined}
          >
            <Input.Password
              placeholder={
                isEdit
                  ? t('form.switchConfig.password.keepUnchanged')
                  : t('form.switchConfig.password.placeholder')
              }
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'authentication_method']}
            label={t('form.switchConfig.authMethod.label')}
            initialValue="password"
          >
            <Select placeholder={tCommon('message.selectRequired')} options={getAuthMethodOptions(t)} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={['switch_config', 'device_type']}
            label={t('form.switchConfig.driver.label')}
          >
            <Select
              placeholder={tCommon('message.selectRequired')}
              allowClear
              options={getSwitchDeviceTypeOptions(t)}
            />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );
}
