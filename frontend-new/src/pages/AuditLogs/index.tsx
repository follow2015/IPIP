import { Space } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import AuditLogTable from '@/components/AuditLogTable';

const ACTION_OPTIONS = [
  { label: '创建', value: 'create' },
  { label: '更新', value: 'update' },
  { label: '删除', value: 'delete' },
  { label: '登录', value: 'login' },
  { label: '登出', value: 'logout' },
  { label: '导入', value: 'import' },
  { label: '导出', value: 'export' },
];

const RESOURCE_OPTIONS = [
  { label: '设备', value: 'device' },
  { label: '机柜', value: 'cabinet' },
  { label: '机房', value: 'room' },
  { label: 'IP', value: 'ip' },
  { label: '网段', value: 'network' },
  { label: '交换机', value: 'switch' },
  { label: '客户', value: 'customer' },
  { label: '用户', value: 'user' },
  { label: 'VLAN', value: 'vlan' },
  { label: '角色', value: 'role' },
];

const ACTION_COLOR_MAP: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  login: 'cyan',
  logout: 'default',
  import: 'purple',
  export: 'orange',
};

function AuditLogs() {
  return (
    <AuditLogTable
      title={
        <Space>
          <AuditOutlined />
          <span>审计日志</span>
        </Space>
      }
      actionOptions={ACTION_OPTIONS}
      resourceOptions={RESOURCE_OPTIONS}
      actionColorMap={ACTION_COLOR_MAP}
    />
  );
}

export default AuditLogs;
