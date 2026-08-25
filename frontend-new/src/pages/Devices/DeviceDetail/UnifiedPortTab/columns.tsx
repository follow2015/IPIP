/**
 * 端口表格列定义工厂
 * - buildSshColumns：网管（SSH）模式，含链路状态 / IP 列表 / PortActions
 * - buildManualColumns：非网管模式，含端口信息 + 启用禁用/编辑/删除
 */
import type { TableProps } from 'antd';
import { Tag, Tooltip, Space, Button } from 'antd';
import { EditOutlined, DeleteOutlined, StopOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { SwitchPort } from '@/types/models';
import { getStatusLabel } from '@/utils/portStatus';
import { StatusTag } from '@/components/StatusTag';
import { PORT_USAGE_STATUS_MAP, LINK_STATUS_MAP } from '@/types/enums';
import type { SubmitActionFn, RenderPortActionsFn } from '@/types/port';

type ColumnType = TableProps<SwitchPort>['columns'];

function renderUsageStatus(v: string) {
  return <StatusTag status={v} statusMap={PORT_USAGE_STATUS_MAP} />;
}

interface SshColumnDeps {
  deviceId: number;
  renderPortActions: RenderPortActionsFn;
  refetch: () => void;
  submitAction: SubmitActionFn;
}

export function buildSshColumns({
  deviceId,
  renderPortActions,
  refetch,
  submitAction
}: SshColumnDeps): ColumnType {
  return [
    { title: '端口号', dataIndex: 'port_name', key: 'port_name' },
    {
      title: '占用状态',
      dataIndex: 'usage_status',
      key: 'usage_status',
      render: (v: string) => renderUsageStatus(v)
    },
    {
      title: '链路状态',
      dataIndex: 'link_status',
      key: 'link_status',
      render: (v: string) => (
        <Tooltip title={getStatusLabel(v)}>
          <StatusTag status={v} statusMap={LINK_STATUS_MAP} />
        </Tooltip>
      )
    },
    { title: 'VLAN', dataIndex: 'vlan', key: 'vlan', render: (v: number | null) => v ?? '-' },
    { title: '速率', dataIndex: 'speed', key: 'speed', render: (v: string) => v || '-' },
    {
      title: 'MAC地址',
      dataIndex: 'mac',
      key: 'mac',
      render: (v: string | null) => v || '-'
    },
    {
      title: 'IP地址',
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
                    {ip.is_primary ? '主' : '从'}
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
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '备注',
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v || '-'
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, port: SwitchPort) => renderPortActions(port, { refetch, submitAction })
    }
  ];
}

interface ManualColumnDeps {
  onToggleUsageStatus: (port: SwitchPort) => void;
  onEdit: (port: SwitchPort) => void;
  onDelete: (port: SwitchPort) => void;
}

export function buildManualColumns({
  onToggleUsageStatus,
  onEdit,
  onDelete
}: ManualColumnDeps): ColumnType {
  return [
    { title: '端口号', dataIndex: 'port_name', key: 'port_name' },
    {
      title: '占用状态',
      dataIndex: 'usage_status',
      key: 'usage_status',
      render: (v: string) => renderUsageStatus(v)
    },
    { title: 'VLAN', dataIndex: 'vlan', key: 'vlan', render: (v: number | null) => v ?? '-' },
    { title: '速率', dataIndex: 'speed', key: 'speed', render: (v: string) => v || '-' },
    {
      title: 'MAC地址',
      dataIndex: 'mac',
      key: 'mac',
      render: (v: string | null) => v || '-'
    },
    {
      title: 'IP地址',
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (v: string | null) => v || '-'
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '备注',
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v || '-'
    },
    {
      title: '操作',
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
              启用
            </Button>
          ) : (
            <Button
              type="link"
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => onToggleUsageStatus(record)}
            >
              禁用
            </Button>
          )}
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => onDelete(record)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];
}
