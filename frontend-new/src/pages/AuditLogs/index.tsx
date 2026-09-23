import { useMemo } from 'react';
import { Space } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AuditLogTable from '@/components/AuditLogTable';

const ACTION_OPTIONS = [
  { labelKey: 'audit.actionType.create', value: 'create' },
  { labelKey: 'audit.actionType.update', value: 'update' },
  { labelKey: 'audit.actionType.delete', value: 'delete' },
  { labelKey: 'audit.actionType.login', value: 'login' },
  { labelKey: 'audit.actionType.logout', value: 'logout' },
  { labelKey: 'audit.actionType.import', value: 'import' },
  { labelKey: 'audit.actionType.export', value: 'export' }
] as const;

const RESOURCE_OPTIONS = [
  { labelKey: 'audit.resourceType.device', value: 'device' },
  { labelKey: 'audit.resourceType.cabinet', value: 'cabinet' },
  { labelKey: 'audit.resourceType.room', value: 'room' },
  { labelKey: 'audit.resourceType.ip', value: 'ip' },
  { labelKey: 'audit.resourceType.network', value: 'network' },
  { labelKey: 'audit.resourceType.switch', value: 'switch' },
  { labelKey: 'audit.resourceType.customer', value: 'customer' },
  { labelKey: 'audit.resourceType.user', value: 'user' },
  { labelKey: 'audit.resourceType.vlan', value: 'vlan' },
  { labelKey: 'audit.resourceType.role', value: 'role' }
] as const;

const ACTION_COLOR_MAP: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  login: 'cyan',
  logout: 'default',
  import: 'purple',
  export: 'orange'
};

function AuditLogs() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');

  const actionOptions = useMemo(
    () => ACTION_OPTIONS.map((o) => ({ label: t(o.labelKey), value: o.value })),
    [t]
  );

  const resourceOptions = useMemo(
    () => RESOURCE_OPTIONS.map((o) => ({ label: t(o.labelKey), value: o.value })),
    [t]
  );

  return (
    <AuditLogTable
      title={
        <Space>
          <AuditOutlined />
          <span>{tc('menu.auditLogs')}</span>
        </Space>
      }
      actionOptions={actionOptions}
      resourceOptions={resourceOptions}
      actionColorMap={ACTION_COLOR_MAP}
    />
  );
}

export default AuditLogs;
