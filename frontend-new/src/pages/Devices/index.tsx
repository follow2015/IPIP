import { useConfirm } from '@/utils/confirm';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
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
import { useBatchSelection, scopeViolationMessage } from '@/hooks/useBatchSelection';
import { BatchActionBar } from '@/components/BatchActionBar';
import { useRoomOptions } from '@/services/room';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useCabinetOptions } from '@/services/cabinet';
import { useVendorBrands } from '@/services/monitor';
import type { Device } from '@/types/models';
import { DEVICE_SUBTYPE_MAP, DEVICE_SUBTYPE_COLORS, DeviceType, DeviceSubtype } from '@/types/enums';
import {
  getDeviceStatusMeta,
  getDeviceStatusOptions,
  getDeviceSubtypeLabel,
  getDeviceSubtypeOptions,
  getDeviceTypeMeta,
  getDeviceTypeOptions
} from '@/types/statusMeta';
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
  getVendorLabel: (enterpriseNo: string | null | undefined) => string,
  t: { d: TFunction<'device'>; c: TFunction<'common'> }
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
      title: t.d('field.name'),
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
      title: t.c('field.type'),
      key: 'type',
      width: 160,
      render: (_: unknown, record: Device) => {
        const sub = record.device_subtype as DeviceSubtype | null;
        if (sub) {
          const subLabel = getDeviceSubtypeLabel(sub, t.d);
          if (subLabel) {
            return <Tag color={DEVICE_SUBTYPE_COLORS[sub]}>{subLabel}</Tag>;
          }
        }
        const mainType = record.device_type as DeviceType;
        const mainLabel = getDeviceTypeMeta(mainType, t.d)?.label ?? record.device_type;
        return <Tag>{mainLabel}</Tag>;
      }
    },
    {
      title: t.c('field.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: number) => {
        const info = getDeviceStatusMeta(v, t.d);
        return <Tag color={info?.color}>{info?.label ?? t.c('field.unknown')}</Tag>;
      }
    },
    {
      title: t.d('field.monitor'),
      key: 'monitor_summary',
      width: 120,
      render: (_: unknown, record: Device) => {
        const m = record.monitor_summary;
        const pingDot = (() => {
          if (!m || m.ping_reachable === null) {
            return (
              <Tooltip title={t.d('tooltip.notPinged')}>
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
              <Tooltip title={t.d('tooltip.pingOk')}>
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
            <Tooltip title={t.d('tooltip.pingFailed')}>
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
            return <Tag color="default">{t.d('status.notConfigured')}</Tag>;
          }
          if (!m.has_monitor_credential) {
            return <Tag color="default">{t.d('status.notConfigured')}</Tag>;
          }
          if (m.monitor_interrupted) {
            return (
              <Tooltip title={t.d('tooltip.interrupted')}>
                <Tag color="orange" icon={<EyeInvisibleOutlined />}>
                  {t.d('status.interrupted')}
                </Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === false) {
            return (
              <Tooltip title={t.d('tooltip.unreachable', { protocol: m.monitor_protocol ?? '-' })}>
                <Tag color="red">{t.d('status.unreachable')}</Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === true && m.active_metric_alerts > 0) {
            const color = m.max_alert_severity >= 3 ? 'magenta' : 'volcano';
            return (
              <Tooltip title={t.d('tooltip.alerting', { count: m.active_metric_alerts })}>
                <Tag color={color} icon={<WarningOutlined />}>
                  {t.d('status.alerting', { count: m.active_metric_alerts })}
                </Tag>
              </Tooltip>
            );
          }
          if (m.monitor_reachable === true) {
            return (
              <Tooltip title={t.d('tooltip.reachable', { protocol: m.monitor_protocol ?? '-' })}>
                <Tag color="green">{t.d('status.reachable')}</Tag>
              </Tooltip>
            );
          }
          return (
            <Tooltip title={t.d('tooltip.pending')}>
              <Tag color="blue">{t.d('status.pending')}</Tag>
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
      title: t.d('field.managementIp'),
      dataIndex: 'management_ip',
      key: 'management_ip',
      width: 140,
      showFor: ['default', DeviceType.SERVER, DeviceType.NETWORK],
      render: (v: string | null) => v ?? '-'
    },
    {
      title: t.d('field.brandModel'),
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
      title: t.d('field.memory'),
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
      title: t.d('field.power'),
      dataIndex: 'power',
      key: 'power',
      width: 80,
      showFor: [DeviceType.OTHER],
      render: (v: number | null) => (v ? `${v}W` : '-')
    },
    {
      title: t.d('field.cabinet'),
      dataIndex: 'cabinet_number',
      key: 'cabinet_number',
      width: 100,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: t.d('field.uPosition'),
      key: 'u_position',
      width: 70,
      render: (_: unknown, r: Device) => {
        const u = r.parent_u_position ?? r.u_position;
        return u ? `U${u}` : '-';
      }
    },
    {
      title: t.c('field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 120,
      render: (v: string | null) => v ?? '-'
    },
    {
      title: t.d('field.portOverview'),
      dataIndex: 'port_summary',
      key: 'port_summary',
      width: 120,
      showFor: [DeviceType.NETWORK],
      render: (_: unknown, record: Device) => {
        if (record.device_type !== DeviceType.NETWORK) return '-';
        const ps = record.port_summary;
        if (!ps) return t.d('port.unknown', { count: record.switch_credential?.port_num || '?' });
        return (
          <Tooltip title={t.d('tooltip.portUsage', { used: ps.used, free: ps.free })}>
            <Tag color="blue">
              {t.d('port.summary', { total: ps.total, used: ps.used, free: ps.free })}
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
          <Tooltip title={t.d('tooltip.hasCredential')}>
            <Badge status="success" />
          </Tooltip>
        ) : (
          <Tooltip title={t.d('tooltip.recordOnly')}>
            <Badge status="default" />
          </Tooltip>
        );
      }
    },
    {
      title: t.c('field.actions'),
      key: 'action',
      width: 210,
      render: (_: unknown, record: Device) => (
        <Space>
          <Button type="link" size="small" onClick={() => handlers.onDetail(record)}>
            {t.c('action.detail')}
          </Button>
          <Button type="link" size="small" onClick={() => handlers.onEdit(record)}>
            {t.c('action.edit')}
          </Button>
          <Button type="link" size="small" onClick={() => handlers.onClone(record)}>
            {t.d('action.clone')}
          </Button>
          <Button type="link" size="small" danger onClick={() => handlers.onDelete(record)}>
            {t.c('action.delete')}
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


function getSubtypeOptions(mainType: string | undefined, t: TFunction<'device'>) {
  if (!mainType) return [];
  const subtypes = DEVICE_SUBTYPE_MAP[mainType as DeviceType] ?? [];
  return getDeviceSubtypeOptions(subtypes, t);
}


const DEVICE_FILTER_RESETS = {
  device_type: ['device_subtype', 'has_ssh'],
  room_id: ['cabinet_id']
};

function Devices() {
  const confirm = useConfirm();
  const { t: tDevice } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const table = useTable({ filterResets: DEVICE_FILTER_RESETS });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const form = useDisclosure();
  const [editRecord, setEditRecord] = useState<Device | null>(null);

  const addDevices = useDisclosure();
  const [addDevicesDefaultTab, setAddDevicesDefaultTab] = useState<'batch' | 'clone'>('batch');
  const [cloneTemplateId, setCloneTemplateId] = useState<number | undefined>();
  const batchAsset = useDisclosure();
  const batchConfig = useDisclosure();
  const batchMonitor = useDisclosure();
  const [configTargets, setConfigTargets] = useState<Device[]>([]);
  const [monitorTargets, setMonitorTargets] = useState<Device[]>([]);

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
    form.open();
  };
  const handleEdit = (record: Device) => {
    setEditRecord(record);
    form.open();
  };

  const handleDelete = (record: Device) => {
    confirm({
      title: tCommon('confirm.deleteTitle'),
      content: tDevice('confirm.deleteContent', { name: record.device_name }),
      okText: tCommon('action.ok'),
      cancelText: tCommon('action.cancel'),
      onOk: async () => {
        try {
          await deleteDevice.mutateAsync(record.id);
          message.success(tCommon('message.deleteSuccess'));
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : tCommon('message.deleteFailed'));
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
    addDevices.open();
  };

  const openAddDevices = (tab: 'batch' | 'clone') => {
    setCloneTemplateId(undefined);
    setAddDevicesDefaultTab(tab);
    addDevices.open();
  };

  const handleAddDevicesClose = (refresh?: boolean) => {
    addDevices.close();
    setCloneTemplateId(undefined);
    if (refresh) refetch();
  };

  const handleBatchDelete = () => {
    confirm({
      title: tCommon('action.batchDelete'),
      content: tDevice('confirm.batchDeleteContent', { count: batch.count }),
      okText: tDevice('confirm.deleteOk'),
      cancelText: tCommon('action.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await batchDelete.mutateAsync(batch.selectedKeys.map(Number));
          message.success(tDevice('message.batchDeleteSuccess', { count: batch.count }));
          batch.clear();
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : tDevice('message.batchDeleteFailed'));
        }
      }
    });
  };

  const handleBatchStatusChange = async (status: number) => {
    const statusLabel = getDeviceStatusMeta(status, tDevice)?.label ?? String(status);
    confirm({
      title: tDevice('batch.changeStatus'),
      content: tDevice('confirm.batchStatusContent', { count: batch.count, status: statusLabel }),
      onOk: async () => {
        try {
          await batchUpdateStatus.mutateAsync({ ids: batch.selectedKeys.map(Number), status });
          message.success(tDevice('message.batchStatusSuccess', { count: batch.count }));
          batch.clear();
          refetch();
        } catch (err) {
          message.error(err instanceof Error ? err.message : tDevice('message.batchStatusFailed'));
        }
      }
    });
  };

  const handleBatchConfig = () => {
    const devs = batch.completeSelectedRows;
    if (devs === null) {
      message.warning(
        scopeViolationMessage(tDevice, batch, tDevice('batch.updateConfig'), tDevice('batch.unit'))
      );
      return;
    }
    if (devs.length === 0) {
      message.error(tDevice('message.noDeviceSelected'));
      return;
    }
    const subtypes = new Set(devs.map((d) => d.device_subtype));
    if (subtypes.size > 1) {
      message.error(tDevice('message.configSubtypeRequired'));
      return;
    }
    setConfigTargets(devs);
    batchConfig.open();
  };

  const handleBatchMonitor = () => {
    const devs = batch.completeSelectedRows;
    if (devs === null) {
      message.warning(
        scopeViolationMessage(tDevice, batch, tDevice('batch.updateMonitor'), tDevice('batch.unit'))
      );
      return;
    }
    if (devs.length === 0) {
      message.error(tDevice('message.noDeviceSelected'));
      return;
    }
    const subtypes = new Set(devs.map((d) => d.device_subtype));
    if (subtypes.size > 1) {
      message.error(tDevice('message.monitorSubtypeRequired'));
      return;
    }
    setMonitorTargets(devs);
    batchMonitor.open();
  };

  const selectedDeviceIds = batch.selectedKeys.map(Number);

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
    () => buildColumns(handlers, getVendorLabel, { d: tDevice, c: tCommon }),
    [handlers, getVendorLabel, tDevice, tCommon]
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
        typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined,
        tDevice
      ),
    [table.filters.device_type, tDevice]
  );

  const rowSelection = batch.rowSelection;

  const filterBar = (
    <FilterBar
      filters={[
        {
          key: 'device_type',
          label: tDevice('filter.mainType'),
          type: 'select',
          options: getDeviceTypeOptions(tDevice),
          width: 130
        },
        {
          key: 'device_subtype',
          label: tDevice('filter.subType'),
          type: 'select',
          options: subtypeOptions,
          width: 130,
          visible: (filters) => !!filters.device_type
        },
        {
          key: 'has_ssh',
          label: tDevice('filter.sshAccess'),
          type: 'select',
          width: 120,
          visible: (filters) => filters.device_type === DeviceType.NETWORK,
          options: [
            { value: true, label: tDevice('tooltip.hasCredential') },
            { value: false, label: tDevice('tooltip.recordOnly') }
          ]
        },
        {
          key: 'status',
          label: tDevice('filter.byStatus'),
          type: 'select',
          width: 130,
          options: getDeviceStatusOptions(tDevice)
        },
        {
          key: 'room_id',
          label: tDevice('filter.byRoom'),
          type: 'select',
          options: roomOptions ?? [],
          width: 150
        },
        {
          key: 'customer_id',
          label: tDevice('filter.byCustomer'),
          type: 'select',
          options: customerOptions ?? [],
          width: 150
        },
        {
          key: 'cabinet_id',
          label: tDevice('filter.byCabinet'),
          type: 'select',
          options: cabinetOptions ?? [],
          width: 170
        }
      ]}
      table={table}
      extra={
        <>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {tDevice('batch.addDevice')}
          </Button>
          <Dropdown
            menu={{
              items: [
                { key: 'batch', label: tDevice('batch.manualBatchAdd'), icon: <PlusOutlined /> },
                { key: 'clone', label: tDevice('batch.cloneCopy'), icon: <ThunderboltOutlined /> }
              ],
              onClick: ({ key }) => openAddDevices(key as 'batch' | 'clone')
            }}
          >
            <Button icon={<ThunderboltOutlined />}>{tDevice('batch.batchAdd')}</Button>
          </Dropdown>
        </>
      }
    />
  );

  return (
    <div>
      <BatchActionBar count={batch.count} unit={tDevice('batch.unit')} onClear={batch.clear}>
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={handleBatchDelete}
          loading={batchDelete.isPending}
        >
          {tCommon('action.batchDelete')}
        </Button>
        <Dropdown
          menu={{
            items: getDeviceStatusOptions(tDevice).map((o) => ({
              key: String(o.value),
              label: o.label
            })),
            onClick: ({ key }) => handleBatchStatusChange(Number(key))
          }}
        >
          <Button size="small" icon={<SwapOutlined />}>
            {tDevice('batch.changeStatus')}
          </Button>
        </Dropdown>
        <Button size="small" icon={<DollarOutlined />} onClick={() => batchAsset.open()}>
          {tDevice('batch.updateAsset')}
        </Button>
        <Button size="small" icon={<ToolOutlined />} onClick={handleBatchConfig}>
          {tDevice('batch.updateConfig')}
        </Button>
        <Button size="small" icon={<EyeOutlined />} onClick={handleBatchMonitor}>
          {tDevice('batch.updateMonitor')}
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
        open={form.isOpen}
        editRecord={editRecord}
        onClose={() => {
          form.close();
          setEditRecord(null);
          refetch();
        }}
      />

      {/* 统一批量添加入口 — 替代原来的 BatchAddDeviceModal + QuickCloneDeviceModal */}
      <AddDevicesModal
        open={addDevices.isOpen}
        onClose={handleAddDevicesClose}
        templateDeviceId={cloneTemplateId}
        defaultTab={addDevicesDefaultTab}
      />

      <BatchUpdateAssetModal
        open={batchAsset.isOpen}
        deviceIds={selectedDeviceIds}
        onClose={(refresh) => {
          batchAsset.close();
          if (refresh) {
            batch.clear();
            refetch();
          }
        }}
      />

      <BatchUpdateConfigModal
        open={batchConfig.isOpen}
        devices={configTargets}
        onClose={(refresh) => {
          batchConfig.close();
          if (refresh) {
            batch.clear();
            refetch();
          }
        }}
      />

      <BatchUpdateMonitorModal
        open={batchMonitor.isOpen}
        devices={monitorTargets}
        onClose={(refresh) => {
          batchMonitor.close();
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
