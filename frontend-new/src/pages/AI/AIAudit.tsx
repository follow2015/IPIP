import { Space } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AuditLogTable from '@/components/AuditLogTable';

type AuditResourceLabelKey =
  | 'audit.resource.ai'
  | 'audit.resource.device'
  | 'audit.resource.rag'
  | 'audit.resource.skill'
  | 'audit.resource.config'
  | 'audit.resource.circuit';

const RESOURCE_OPTIONS: { labelKey: AuditResourceLabelKey; value: string }[] = [
  { labelKey: 'audit.resource.ai', value: 'ai' },
  { labelKey: 'audit.resource.device', value: 'device' },
  { labelKey: 'audit.resource.rag', value: 'ai_rag' },
  { labelKey: 'audit.resource.skill', value: 'ai_skill' },
  { labelKey: 'audit.resource.config', value: 'ai_config' },
  { labelKey: 'audit.resource.circuit', value: 'ai_circuit' }
];

const ACTION_COLOR_MAP: Record<string, string> = {
  'ai.nlq': 'blue',
  'ai.rag': 'cyan',
  'ai.alert': 'orange',
  'ai.remedial.execute': 'red',
  'ai.remedial.rollback': 'volcano',
  'ai.skill.create': 'green',
  'ai.skill.update': 'geekblue',
  'ai.skill.delete': 'magenta',
  'ai.skill.toggle': 'purple',
  'ai.config.update': 'gold',
  'ai.circuit.reset': 'lime'
};

export default function AIAudit() {
  const { t } = useTranslation('ai');
  return (
    <AuditLogTable
      title={
        <Space>
          <AuditOutlined />
          <span>{t('audit.title')}</span>
        </Space>
      }
      actionPrefix="ai."
      resourceOptions={RESOURCE_OPTIONS.map(({ labelKey, value }) => ({
        label: t(labelKey),
        value
      }))}
      actionColorMap={ACTION_COLOR_MAP}
    />
  );
}
