/**
 * 端口表格列定义工厂
 * - buildSshColumns：网管（SSH）模式，含链路状态 / IP 列表 / PortActions
 * - buildManualColumns：非网管模式，含端口信息 + 启用禁用/编辑/删除
 */
import type { TFunction } from 'i18next';
import type { TableProps } from 'antd';
import { Tag, Tooltip, Space, Button } from 'antd';
import { EditOutlined, DeleteOutlined, StopOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { SwitchPort } from '@/types/models';
import { getStatusLabel } from '@/utils/portStatus';
import { StatusTag } from '@/components/StatusTag';
import { PORT_USAGE_STATUS_MAP, LINK_STATUS_MAP } from '@/types/enums';
import type { SubmitActionFn, RenderPortActionsFn } from '@/types/port';

type ColumnType = TableProps<SwitchPort>['columns'];

interface ColumnT {
  d: TFunction<'device'>;
  c: TFunction<'common'>;
}

function renderUsageStatus(v: string) {
  return <StatusTag status={v} statusMap={PORT_USAGE_STATUS_MAP} />;
}

interface SshColumnDeps {
  deviceId: number;
  renderPortActions: RenderPortActionsFn;
  refetch: () => void;
  submitAction: SubmitActionFn;
  t: ColumnT;
}

export function buildSshColumns({
  deviceId,
  renderPortActions,
  refetch,
  submitAction,
  t
}: SshColumnDeps): ColumnType {
  return [
    { title: t.d('nic.column.portIndex'), dataIndex: 'port_name', key: 'port_name' },
    {
      title: t.d('port.column.usageStatus'),
      dataIndex: 'usage_status',
      key: 'usage_status',
      render: (v: string) => renderUsageStatus(v)
    },
    {
      title: t.d('port.column.linkStatus'),
      dataIndex: 'link_status',
      key: 'link_status',
      render: (v: string) => (
        <Tooltip title={getStatusLabel(v, t.d)}>
          <StatusTag status={v} statusMap={LINK_STATUS_MAP} />
        </Tooltip>
      )
    },
    {
      title: t.d('connection.column.vlan'),
      dataIndex: 'vlan',
      key: 'vlan',
      render: (v: number | null) => v ?? '-'
    },
    {
      title: t.d('nic.column.speed'),
      dataIndex: 'speed',
      key: 'speed',
      render: (v: string) => v || '-'
    },
    {
      title: t.d('form.network.macAddress.label'),
      dataIndex: 'mac',
      key: 'mac',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.d('port.column.ipAddress'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (_: unknown, record: SwitchPort) => {
        const ipList = record.ip_list;
        if (ipList && ipList.length > 0) {
          return (
            <div style={{ lineHeight: 1.6 }}>
              {ipList.map((ip, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Tag
                    color={ip.is_primary ? 'blue' : 'default'}
                    style={{ fontSize: 10, margin: 0, lineHeight: '16px' }}
                  >
                    {ip.is_primary ? t.d('port.ipRole.primary') : t.d('port.ipRole.secondary')}
                  </Tag>
                  <code style={{ fontSize: 12 }}>
                    {ip.ip_address}
                    {ip.subnet_mask ? `/${ip.subnet_mask}` : ''}
                  </code>
                </div>
              ))}
            </div>
          );
        }
        return record.ip_address || '-';
      }
    },
    {
      title: t.c('field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.c('field.remarks'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.c('field.actions'),
      key: 'action',
      render: (_: unknown, port: SwitchPort) => renderPortActions(port, { refetch, submitAction })
    }
  ];
}

interface ManualColumnDeps {
  onToggleUsageStatus: (port: SwitchPort) => void;
  onEdit: (port: SwitchPort) => void;
  onDelete: (port: SwitchPort) => void;
  t: ColumnT;
}

export function buildManualColumns({
  onToggleUsageStatus,
  onEdit,
  onDelete,
  t
}: ManualColumnDeps): ColumnType {
  return [
    { title: t.d('nic.column.portIndex'), dataIndex: 'port_name', key: 'port_name' },
    {
      title: t.d('port.column.usageStatus'),
      dataIndex: 'usage_status',
      key: 'usage_status',
      render: (v: string) => renderUsageStatus(v)
    },
    {
      title: t.d('connection.column.vlan'),
      dataIndex: 'vlan',
      key: 'vlan',
      render: (v: number | null) => v ?? '-'
    },
    {
      title: t.d('nic.column.speed'),
      dataIndex: 'speed',
      key: 'speed',
      render: (v: string) => v || '-'
    },
    {
      title: t.d('form.network.macAddress.label'),
      dataIndex: 'mac',
      key: 'mac',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.d('port.column.ipAddress'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.c('field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.c('field.remarks'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v || '-'
    },
    {
      title: t.c('field.actions'),
      key: 'action',
      width: 200,
      render: (_: unknown, record: SwitchPort) => (
        <Space>
          {record.usage_status === 'disabled' ? (
            <Button
              type="link"
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => onToggleUsageStatus(record)}
            >
              {t.c('action.enable')}
            </Button>
          ) : (
            <Button
              type="link"
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => onToggleUsageStatus(record)}
            >
              {t.c('action.disable')}
            </Button>
          )}
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>
            {t.c('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => onDelete(record)}
          >
            {t.c('action.delete')}
          </Button>
        </Space>
      )
    }
  ];
}
