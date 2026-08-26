import { confirm } from '@/utils/confirm';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { Button, Space, Tag, Dropdown, Tooltip, Badge, Modal } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  ToolOutlined,
  EyeOutlined,
  WarningOutlined,
  EyeInvisibleOutlined
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import DeviceForm from './DeviceForm';
import AddDevicesModal from './AddDevicesModal';
import BatchUpdateAssetModal from './BatchUpdateAssetModal';
import BatchUpdateConfigModal from './BatchUpdateConfigModal';
import BatchUpdateMonitorModal from './BatchUpdateMonitorModal';
import {
  useDeviceList,
  useDeleteDevice,
  useBatchDeleteDevices,
  useBatchUpdateDeviceStatus,
  useBatchResetDeviceAsset
} from '@/services/device';
import { useMessage, useModal } from '@/hooks/useMessage';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import { BatchActionBar } from '@/components/BatchActionBar';
import { useRoomOptions } from '@/services/room';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useCabinetOptions } from '@/services/cabinet';
import { useVendorBrands } from '@/services/monitor';
import type { Device } from '@/types/models';
import {
  DEVICE_STATUS_MAP,
  DeviceStatusCode,
  DEVICE_TYPE_MAP,
  DEVICE_SUBTYPE_MAP,
  DEVICE_SUBTYPE_LABELS,
  DEVICE_SUBTYPE_COLORS,
  DeviceType,
  DeviceSubtype
} from '@/types/enums';
import { useTable } from '@/hooks/useTable';


type ShowFor = (DeviceType | 'default')[] | undefined;
type ColumnDef = any & { showFor?: ShowFor };

function buildColumns(
  handlers: {
    onDetail: (r: Device) => void;
    onEdit: (r: Device) => void;
    onDelete: (r: Device) => void;
    onClone: (r: Device) => void;
  },
  getVendorLabel: (enterpriseNo: string | null | undefined) => string
): ColumnDef[] {
  return [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
      render: (id: number) => (id != null ? id : '-')
    },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      width: 180,
      render: (name: string, record: Device) => (
        <Button type="link" size="small" onClick={() => handlers.onDetail(record)}>
          {name}
        </Button>
      )
    },
    {
      title: '类型',
      key: 'type',
      width: 160,
      render: (_: unknown, record: Device) => {
        const sub = record.device_subtype as DeviceSubtype | null;
        if (sub && DEVICE_SUBTYPE_LABELS[sub]) {
          return <Tag color={DEVICE_SUBTYPE_COLORS[sub]}>{DEVICE_SUBTYPE_LABELS[sub]}</Tag>;
        }
        const mainType = record.device_type as DeviceType;
        const mainLabel = DEVICE_TYPE_MAP[mainType]?.label ?? record.device_type;
        return <Tag>{mainLabel}</Tag>;
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: number) => {
        const info = DEVICE_STATUS_MAP[v as DeviceStatusCode];
        return <Tag color={info?.color}>{info?.label ?? '未知'}</Tag>;
      }
    },
    {
      title: '监控',
      key: 'monitor_summary',
      width: 120,
      render: (_: unknown, record: Device) => {
        const m = record.monitor_summary;
        const pingDot = (() => {
          if (!m || m.ping_reachable === null) {
            return (
              <Tooltip title="未 ping 探测">
                <span
                  style={{
                    display: 'inline-block',
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: '#d9d9d9',
                    marginRight: 6
                  }}
                />
              </Tooltip>
            );
          }
          if (m.ping_reachable) {
            return (
              <Tooltip title="管理 IP 可 ping 通">
                <span
                  style={{
                    display: 'inline-block',
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: '#52c41a',
                    marginRight: 6
                  }}
                />
              </Tooltip>
            );
          }
          return (
            <Tooltip title="管理 IP 不可 ping 通">
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: '#d9d9d9',
                  marginRight: 6,
                  border: '1px solid #bfbfbf'
                }}
              />
            </Tooltip>
          );
        })();

        const monitorTag = (() => {
          if (!m) {
            return <Tag color="default">未配置</Tag>;
          }
          if (!m.has_monitor_credential) {
            return <Tag color="default">未配置</Tag>;
          }
          if (m.monitor_interrupted) {
            return (
              <Tooltip title="监控中断：长时间未探测到">
                <Tag color="orange" icon={<EyeInvisibleOutlined />}>
                  中断
                </Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === false) {
            return (
              <Tooltip title={`不可达（协议: ${m.monitor_protocol ?? '-'}）`}>
                <Tag color="red">不可达</Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === true && m.active_metric_alerts > 0) {
            const color = m.max_alert_severity >= 3 ? 'magenta' : 'volcano';
            return (
              <Tooltip title={`可达但 ${m.active_metric_alerts} 项指标告警`}>
                <Tag color={color} icon={<WarningOutlined />}>
                  告警 {m.active_metric_alerts}
                </Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === true) {
            return (
              <Tooltip title={`可达（协议: ${m.monitor_protocol ?? '-'}）`}>
                <Tag color="green">可达</Tag>
              </Tooltip>
            );
          }
          return (
            <Tooltip title="已配置凭据，等待首次探测">
              <Tag color="blue">待探测</Tag>
            </Tooltip>
          );
        })();

        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {pingDot}
            {monitorTag}
          </span>
        );
      }
    },
    {
      title: '管理IP',
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      showFor: ['default', DeviceType.SERVER, DeviceType.NETWORK],
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '品牌/型号',
      key: 'brand_model',
      width: 160,
      showFor: [DeviceType.SERVER, DeviceType.NETWORK, DeviceType.OTHER],
      render: (_: unknown, r: Device) => {
        const brandLabel = getVendorLabel(r.brand);
        const parts = [brandLabel, r.device_model].filter(Boolean);
        return parts.length ? parts.join(' / ') : '-';
      }
    },
    {
      title: 'CPU',
      dataIndex: 'cpu',
      key: 'cpu',
      width: 140,
      showFor: [DeviceType.SERVER],
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '内存',
      key: 'memory',
      width: 100,
      showFor: [DeviceType.SERVER],
      render: (_: unknown, r: Device) =>
        r.memory
          ? `${r.memory}${r.memory_dimm_count ? ` ×${r.memory_dimm_count}` : ''}`
          : r.memory_size_gb
            ? `${r.memory_size_gb}GB`
            : '-'
    },
    {
      title: 'GPU',
      key: 'gpu',
      width: 140,
      showFor: [DeviceType.SERVER],
      render: (_: unknown, r: Device) =>
        r.gpu ? `${r.gpu}${r.gpu_count ? ` ×${r.gpu_count}` : ''}` : '-'
    },
    {
      title: '功率',
      dataIndex: 'power',
      key: 'power',
      width: 80,
      showFor: [DeviceType.OTHER],
      render: (v: number | null) => (v ? `${v}W` : '-')
    },
    {
      title: '机柜',
      dataIndex: 'cabinet_number',
      key: 'cabinet_number',
      width: 100,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: 'U位',
      key: 'u_position',
      width: 70,
      render: (_: unknown, r: Device) => {
        const u = r.parent_u_position ?? r.u_position;
        return u ? `U${u}` : '-';
      }
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '端口概览',
      dataIndex: 'port_summary',
      key: 'port_summary',
      width: 120,
      showFor: [DeviceType.NETWORK],
      render: (_: unknown, record: Device) => {
        if (record.device_type !== DeviceType.NETWORK) return '-';
        const ps = record.port_summary;
        if (!ps) return `${record.switch_credential?.port_num || '?'}口`;
        return (
          <Tooltip title={`已用: ${ps.used}, 空闲: ${ps.free}`}>
            <Tag color="blue">
              {ps.total}口({ps.used}用/{ps.free}空)
            </Tag>
          </Tooltip>
        );
      }
    },
    {
      title: 'SSH',
      key: 'ssh_status',
      width: 60,
      showFor: [DeviceType.NETWORK],
      render: (_: unknown, record: Device) => {
        if (record.device_type !== DeviceType.NETWORK) return '-';
        const hasSsh = record.switch_credential?.has_ssh;
        return hasSsh ? (
          <Tooltip title="有管理权限">
            <Badge status="success" />
          </Tooltip>
        ) : (
          <Tooltip title="仅记录">
            <Badge status="default" />
          </Tooltip>
        );
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 210,
      render: (_: unknown, record: Device) => (
        <Space>
          <Button type="link" size="small" onClick={() => handlers.onDetail(record)}>
            详情
          </Button>
          <Button type="link" size="small" onClick={() => handlers.onEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => handlers.onClone(record)}>
            克隆
          </Button>
          <Button type="link" size="small" danger onClick={() => handlers.onDelete(record)}>
            删除
          </Button>
        </Space>
      )
    }
  ];
}

function filterColumns(columns: ColumnDef[], typeFilter: string | undefined): ColumnDef[] {
  return columns.filter((col) => {
    if (!col.showFor) return true;
    if (!typeFilter) return col.showFor.includes('default');
    return col.showFor.includes(typeFilter as DeviceType);
  });
}


const TYPE_FILTER_OPTIONS = Object.entries(DEVICE_TYPE_MAP).map(([k, v]) => ({
  label: v.label,
  value: k
}));

function getSubtypeOptions(mainType: string | undefined) {
  if (!mainType) return [];
  const subtypes = DEVICE_SUBTYPE_MAP[mainType as DeviceType] ?? [];
  return subtypes.map((s) => ({ label: DEVICE_SUBTYPE_LABELS[s], value: s }));
}

const BATCH_STATUS_MENU = Object.entries(DEVICE_STATUS_MAP).map(([k, v]) => ({
  key: k,
  label: v.label
}));


function Devices() {
  const table = useTable({
    filterResets: {
      device_type: ['device_subtype', 'has_ssh'],
      room_id: ['cabinet_id']
    }
  });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [formOpen, setFormOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<Device | null>(null);

  const [addDevicesOpen, setAddDevicesOpen] = useState(false);
  const [addDevicesDefaultTab, setAddDevicesDefaultTab] = useState<'batch' | 'clone'>('batch');
  const [cloneTemplateId, setCloneTemplateId] = useState<number | undefined>();
  const [batchAssetOpen, setBatchAssetOpen] = useState(false);
  const [batchConfigOpen, setBatchConfigOpen] = useState(false);
  const [batchMonitorOpen, setBatchMonitorOpen] = useState(false);

  const deleteDevice = useDeleteDevice();
  const batchDelete = useBatchDeleteDevices();
  const batchUpdateStatus = useBatchUpdateDeviceStatus();
  const batchResetAsset = useBatchResetDeviceAsset();
  const message = useMessage();
  const modal = useModal();
  const { data: roomOptions } = useRoomOptions();
  const { data: customerOptions } = useAllocatableCustomerOptions();

  const urlCabinetId = searchParams.get('cabinetId');
  const urlRoomId = searchParams.get('roomId');
  useEffect(() => {
    if (urlCabinetId) table.updateFilter('cabinet_id', Number(urlCabinetId));
    if (urlRoomId) table.updateFilter('room_id', Number(urlRoomId));
  }, [urlCabinetId, urlRoomId]);

  const { data: cabinetOptions } = useCabinetOptions(
    table.filters.room_id ? Number(table.filters.room_id) : undefined,
    true
  );

  const { data, isLoading, refetch } = useDeviceList({
    page: table.page,
    per_page: table.perPage,
    search: table.search || undefined,
    device_type:
      typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined,
    device_subtype:
      typeof table.filters.device_subtype === 'string' ? table.filters.device_subtype : undefined,
    status: table.filters.status ? Number(table.filters.status) : undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    cabinet_id: table.filters.cabinet_id ? Number(table.filters.cabinet_id) : undefined,
    customer_id: table.filters.customer_id ? Number(table.filters.customer_id) : undefined,
    has_ssh:
      table.filters.has_ssh === 'true'
        ? true
        : table.filters.has_ssh === 'false'
          ? false
          : undefined
  });

  const { data: vendorBrands } = useVendorBrands();
  const vendorLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const v of vendorBrands?.items ?? []) {
      if (v.enabled && !map.has(v.enterprise_no)) map.set(v.enterprise_no, v.label);
    }
    return map;
  }, [vendorBrands]);
  const getVendorLabel = useCallback(
    (en: string | null | undefined) => (en ? (vendorLabelMap.get(en) ?? en) : '-'),
    [vendorLabelMap]
  );

  const batch = useBatchSelection<Device>({
    dataSource: data?.items ?? [],
    getRowKey: (r) => String(r.id ?? '')
  });

  const handleAdd = () => {
    setEditRecord(null);
    setFormOpen(true);
  };
  const handleEdit = (record: Device) => {
    setEditRecord(record);
    setFormOpen(true);
  };

  const handleDelete = (record: Device) => {
    confirm({
      title: '确认删除',
      content: `确定要删除设备「${record.device_name}」吗？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(record.id);
          message.success('删除成功');
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : '删除失败');
        }
      }
    });
  };

  const handleDetail = (record: Device) => {
    if (record.device_type === DeviceType.NETWORK) {
      navigate(`/switches/${record.id}`);
    } else {
      navigate(`/devices/${record.id}`);
    }
  };

  const handleClone = (record: Device) => {
    setCloneTemplateId(record.id);
    setAddDevicesDefaultTab('clone');
    setAddDevicesOpen(true);
  };

  const openAddDevices = (tab: 'batch' | 'clone') => {
    setCloneTemplateId(undefined);
    setAddDevicesDefaultTab(tab);
    setAddDevicesOpen(true);
  };

  const handleAddDevicesClose = (refresh?: boolean) => {
    setAddDevicesOpen(false);
    setCloneTemplateId(undefined);
    if (refresh) refetch();
  };

  const handleBatchDelete = () => {
    confirm({
      title: '批量删除',
      content: `确定要删除选中的 ${batch.count} 台设备吗？此操作不可恢复。`,
      okText: '确定删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await batchDelete.mutateAsync(batch.selectedKeys.map(Number));
          message.success(`成功删除 ${batch.count} 台设备`);
          batch.clear();
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : '批量删除失败');
        }
      }
    });
  };

  const handleBatchStatusChange = async (status: number) => {
    const statusLabel = DEVICE_STATUS_MAP[status as DeviceStatusCode]?.label ?? status;
    confirm({
      title: '批量变更状态',
      content: `确定要将选中的 ${batch.count} 台设备状态变更为「${statusLabel}」吗？`,
      onOk: async () => {
        try {
          await batchUpdateStatus.mutateAsync({ ids: batch.selectedKeys.map(Number), status });
          message.success(`已变更 ${batch.count} 台设备状态`);
          batch.clear();
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : '批量状态变更失败');
        }
      }
    });
  };

  const handleBatchConfig = () => {
    const devs = batch.selectedRows;
    if (devs.length === 0) {
      message.error('未找到所选设备，请重新勾选');
      return;
    }
    const subtypes = new Set(devs.map((d) => d.device_subtype));
    if (subtypes.size > 1) {
      message.error('批量修改配置要求所选设备的子类型必须一致');
      return;
    }
    setBatchConfigOpen(true);
  };

  const handleBatchMonitor = () => {
    const devs = batch.selectedRows;
    if (devs.length === 0) {
      message.error('未找到所选设备，请重新勾选');
      return;
    }
    const subtypes = new Set(devs.map((d) => d.device_subtype));
    if (subtypes.size > 1) {
      message.error('批量修改监控要求所选设备的子类型必须一致');
      return;
    }
    setBatchMonitorOpen(true);
  };

  const selectedDevices = batch.selectedRows;

  const handlers = useMemo(
    () => ({
      onDetail: handleDetail,
      onEdit: handleEdit,
      onDelete: handleDelete,
      onClone: handleClone
    }),
    []
  );

  const allColumns = useMemo(
    () => buildColumns(handlers, getVendorLabel),
    [handlers, getVendorLabel]
  );
  const columns = useMemo(
    () =>
      filterColumns(
        allColumns,
        typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined
      ),
    [allColumns, table.filters.device_type]
  );
  const subtypeOptions = useMemo(
    () =>
      getSubtypeOptions(
        typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined
      ),
    [table.filters.device_type]
  );

  const rowSelection = batch.rowSelection;

  const filterBar = (
    <FilterBar
      filters={[
        {
          key: 'device_type',
          label: '主类型',
          type: 'select',
          options: TYPE_FILTER_OPTIONS,
          width: 130
        },
        {
          key: 'device_subtype',
          label: '子类型',
          type: 'select',
          options: subtypeOptions,
          width: 130,
          visible: (filters) => !!filters.device_type
        },
        {
          key: 'has_ssh',
          label: '管理权限',
          type: 'select',
          width: 120,
          visible: (filters) => filters.device_type === DeviceType.NETWORK,
          options: [
            { value: true, label: '有管理权限' },
            { value: false, label: '仅记录' }
          ]
        },
        {
          key: 'status',
          label: '按状态筛选',
          type: 'select',
          width: 130,
          options: Object.entries(DEVICE_STATUS_MAP).map(([k, v]) => ({
            label: v.label,
            value: Number(k)
          }))
        },
        {
          key: 'room_id',
          label: '按机房筛选',
          type: 'select',
          options: roomOptions ?? [],
          width: 150
        },
        {
          key: 'customer_id',
          label: '按客户筛选',
          type: 'select',
          options: customerOptions ?? [],
          width: 150
        },
        {
          key: 'cabinet_id',
          label: '按机柜筛选',
          type: 'select',
          options: cabinetOptions ?? [],
          width: 170
        }
      ]}
      table={table}
      extra={
        <>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增设备
          </Button>
          <Dropdown
            menu={{
              items: [
                { key: 'batch', label: '手动批量添加', icon: <PlusOutlined /> },
                { key: 'clone', label: '克隆复制', icon: <ThunderboltOutlined /> }
              ],
              onClick: ({ key }) => openAddDevices(key as 'batch' | 'clone')
            }}
          >
            <Button icon={<ThunderboltOutlined />}>批量添加</Button>
          </Dropdown>
        </>
      }
    />
  );

  return (
    <div>
      <BatchActionBar count={batch.count} unit="台设备" onClear={batch.clear}>
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={handleBatchDelete}
          loading={batchDelete.isPending}
        >
          批量删除
        </Button>
        <Dropdown
          menu={{
            items: BATCH_STATUS_MENU,
            onClick: ({ key }) => handleBatchStatusChange(Number(key))
          }}
        >
          <Button size="small" icon={<SwapOutlined />}>
            批量变更状态
          </Button>
        </Dropdown>
        <Button size="small" icon={<DollarOutlined />} onClick={() => setBatchAssetOpen(true)}>
          批量修改资产信息
        </Button>
        <Button size="small" icon={<ToolOutlined />} onClick={handleBatchConfig}>
          批量修改配置
        </Button>
        <Button size="small" icon={<EyeOutlined />} onClick={handleBatchMonitor}>
          批量修改监控
        </Button>
      </BatchActionBar>

      <DataTable<Device>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => String(r.id ?? '')}
        total={data?.total}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={() => refetch()}
        toolbar={filterBar}
        rowSelection={rowSelection}
      />

      <DeviceForm
        open={formOpen}
        editRecord={editRecord}
        onClose={() => {
          setFormOpen(false);
          setEditRecord(null);
          refetch();
        }}
      />

      {/* 统一批量添加入口 — 替代原来的 BatchAddDeviceModal + QuickCloneDeviceModal */}
      <AddDevicesModal
        open={addDevicesOpen}
        onClose={handleAddDevicesClose}
        templateDeviceId={cloneTemplateId}
        defaultTab={addDevicesDefaultTab}
      />

      <BatchUpdateAssetModal
        open={batchAssetOpen}
        deviceIds={batch.selectedKeys.map(Number)}
        onClose={(refresh) => {
          setBatchAssetOpen(false);
          if (refresh) {
            batch.clear();
            refetch();
          }
        }}
      />

      <BatchUpdateConfigModal
        open={batchConfigOpen}
        devices={selectedDevices}
        onClose={(refresh) => {
          setBatchConfigOpen(false);
          if (refresh) {
            batch.clear();
            refetch();
          }
        }}
      />

      <BatchUpdateMonitorModal
        open={batchMonitorOpen}
        devices={selectedDevices}
        onClose={(refresh) => {
          setBatchMonitorOpen(false);
          if (refresh) {
            batch.clear();
            refetch();
          }
        }}
      />
    </div>
  );
}

export default Devices;
