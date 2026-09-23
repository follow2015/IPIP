import { useConfirm } from '@/utils/confirm';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Space, Tag, Popover, Segmented, Collapse, Card, Input, Typography } from 'antd';
import {
  PlusOutlined,
  CopyOutlined,
  ExportOutlined,
  SearchOutlined,
  ReloadOutlined,
  EditOutlined
} from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import DataTable from '@/components/DataTable';
import { BatchActionBar } from '@/components/BatchActionBar';
import FilterBar from '@/components/FilterBar';
import SearchInput from '@/components/SearchInput';
import SwitchForm from './SwitchForm';
import BatchUpdateSwitchModal from './BatchUpdateSwitchModal';
import DeviceForm from '@/pages/Devices/DeviceForm';
import { useSwitchList, useDeleteSwitch, useScanRoom } from '@/services/switch';
import { useRoomOptions } from '@/services/room';
import type { Switch } from '@/types/models';
import type { Device } from '@/types/models';
import { DeviceType } from '@/types/enums';
import {
  getSwitchDeviceTypeOptions,
  getSwitchRoleMeta,
  getSwitchRoleOptions
} from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection, scopeViolationMessage } from '@/hooks/useBatchSelection';
import { useMessage } from '@/hooks/useMessage';
import { useGlobalEventListener, type GlobalEvent } from '@/hooks/useGlobalEvents';

const SCAN_TIMEOUT = 5 * 60_000;

const { Text } = Typography;

function Switches() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const table = useTable();
  const navigate = useNavigate();

  const form = useDisclosure();
  const [editRecord, setEditRecord] = useState<Switch | null>(null);
  const deviceForm = useDisclosure();
  const [deviceEditRecord, setDeviceEditRecord] = useState<Device | null>(null);
  const [groupMode, setGroupMode] = useState<'group' | 'flat'>('group');
  const batchUpdate = useDisclosure();
  const [batchUpdateTargets, setBatchUpdateTargets] = useState<Switch[]>([]);
  const deleteSwitch = useDeleteSwitch();
  const scanRoom = useScanRoom();
  const message = useMessage();
  const { data: roomOptions } = useRoomOptions();

  const { data, isLoading, refetch } = useSwitchList({
    page: table.page,
    per_page: table.perPage,
    search: table.search || undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    switch_role: table.filters.switch_role ? Number(table.filters.switch_role) : undefined,
    device_type:
      typeof table.filters.device_type === 'string' ? table.filters.device_type : undefined
  });

  const [scanningRoomId, setScanningRoomId] = useState<number | null>(null);

  const scanTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (scanTimeoutRef.current) clearTimeout(scanTimeoutRef.current);
    };
  }, []);

  const handleGlobalEvent = useCallback((event: GlobalEvent) => {
    if (event.event_type === 'room_scan_complete') {
      const payload = event.payload as Record<string, unknown>;
      const roomId = payload.room_id as number | undefined;
      if (roomId) {
        setScanningRoomId(null);
        if (scanTimeoutRef.current) {
          clearTimeout(scanTimeoutRef.current);
          scanTimeoutRef.current = null;
        }
      }
      return;
    }

    if (event.event_type !== 'scan_progress') return;

    const progress = event.payload as { room_id?: number; phase?: string };
    const roomId = progress.room_id;
    if (!roomId) return;

    if (progress.phase === 'failed' || progress.phase === '完成') {
      setScanningRoomId(null);
      if (scanTimeoutRef.current) {
        clearTimeout(scanTimeoutRef.current);
        scanTimeoutRef.current = null;
      }
    }
  }, []);

  useGlobalEventListener(handleGlobalEvent);

  const handleScanRoom = () => {
    const roomId = table.filters.room_id ? Number(table.filters.room_id) : undefined;
    if (!roomId) {
      message.warning(td('switch.message.selectRoomFirst'));
      return;
    }
    confirm({
      title: td('switch.action.scanRoom'),
      content: td('switch.confirm.scanRoomContent'),
      okText: tc('action.ok'),
      cancelText: tc('action.cancel'),
      onOk: async () => {
        try {
          await scanRoom.mutateAsync(roomId);
          setScanningRoomId(roomId);
          message.info(td('switch.message.scanSubmitted'));
          scanTimeoutRef.current = setTimeout(() => {
            scanTimeoutRef.current = null;
            setScanningRoomId(null);
          }, SCAN_TIMEOUT);
        } catch {
          message.error(td('switch.message.scanSubmitFailed'));
        }
      }
    });
  };

  const handleAdd = () => {
    setDeviceEditRecord(null);
    deviceForm.open();
  };
  const handleEdit = (r: Switch) => {
    setEditRecord(r);
    form.open();
  };
  const handleFullEdit = (r: Switch) => {
    setDeviceEditRecord({ id: r.device_id } as Device);
    deviceForm.open();
  };
  const handleDetail = (r: Switch) => navigate(`/switches/${r.device_id}`);
  const confirmAction = useConfirmAction();
  const handleDelete = (r: Switch) => {
    confirmAction({
      title: tc('confirm.deleteTitle'),
      content: td('switch.deleteContent', { name: r.name }),
      okType: 'danger',
      successMessage: tc('message.deleteSuccess'),
      onConfirm: () => deleteSwitch.mutateAsync(r.device_id),
      afterConfirm: refetch
    });
  };

  const handleCopy = (r: Switch) => {
    const text = [
      td('switch.copy.name', { value: r.name }),
      td('switch.copy.ip', { value: r.ip_address ?? '-' }),
      td('switch.copy.role', { value: getSwitchRoleMeta(r.switch_role, td)?.label ?? '-' }),
      td('switch.copy.deviceModel', { value: r.device_model ?? '-' }),
      td('switch.copy.room', { value: r.room_name ?? '-' }),
      td('switch.copy.protocol', { value: r.protocol ?? '-' }),
      td('switch.copy.deviceType', { value: r.device_type ?? '-' })
    ].join('\n');
    navigator.clipboard.writeText(text).then(() => message.success(td('switch.message.copied')));
  };

  const handleExport = useCallback(() => {
    const items = data?.items ?? [];
    if (!items.length) {
      message.warning(td('switch.message.noDataToExport'));
      return;
    }
    const headers = [
      tc('field.name'),
      td('field.managementIp'),
      tc('field.type'),
      td('basic.field.model'),
      td('basic.field.room'),
      td('switch.field.protocol'),
      td('basic.field.deviceType')
    ];
    const rows = items.map((r) => [
      r.name,
      r.ip_address,
      getSwitchRoleMeta(r.switch_role, td)?.label ?? String(r.switch_role),
      r.device_model ?? '',
      r.room_name ?? '',
      r.protocol ?? '',
      r.device_type ?? ''
    ]);
    const csv = [headers, ...rows].map((row) => row.map((c) => `"${c}"`).join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `switches_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [data, td]);

  const columns = [
    {
      title: tc('field.name'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r: Switch) => (
        <Button type="link" size="small" onClick={() => handleDetail(r)}>
          {v}
        </Button>
      )
    },
    { title: td('field.managementIp'), dataIndex: 'ip_address', key: 'ip_address' },
    {
      title: tc('field.type'),
      dataIndex: 'switch_role',
      key: 'switch_role',
      render: (v: number) => (
        <Tag color={getSwitchRoleMeta(v, td)?.color}>
          {getSwitchRoleMeta(v, td)?.label ?? '-'}
        </Tag>
      )
    },
    {
      title: td('switch.field.layer'),
      dataIndex: 'layer',
      key: 'layer',
      render: (v: number | null) =>
        v === 3 ? (
          <Tag color="blue">L3</Tag>
        ) : v === 2 ? (
          <Tag color="green">L2</Tag>
        ) : v === 1 ? (
          <Tag color="purple">L1</Tag>
        ) : (
          '-'
        )
    },
    {
      title: td('form.networkTopology.uplinkDevice.label'),
      dataIndex: 'uplink_device_name',
      key: 'uplink_device_name',
      width: 120,
      render: (v: string | null, r: Switch) =>
        v ? (
          <Tag color="blue">{v}</Tag>
        ) : r.uplink_device_id ? (
          <Tag color="blue">ID:{r.uplink_device_id}</Tag>
        ) : (
          '-'
        )
    },
    {
      title: td('form.networkTopology.uplinkPorts.label'),
      dataIndex: 'uplink_port_names',
      key: 'uplink_port_names',
      width: 120,
      render: (v: string[] | null) => (v?.length ? v.join(', ') : '-')
    },
    {
      title: td('basic.field.model'),
      dataIndex: 'device_model',
      key: 'device_model',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: td('basic.field.room'),
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: td('switch.field.protocol'),
      dataIndex: 'protocol',
      key: 'protocol',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: td('switch.field.connectedDevices'),
      dataIndex: 'connected_device_count',
      key: 'connected_device_count',
      width: 90,
      sorter: true,
      render: (count: number, record: Switch) => {
        if (!count) return <Tag>0</Tag>;
        return (
          <Popover
            content={
              <Link to={`/switches/${record.device_id}`}>{td('switch.action.viewDetail')}</Link>
            }
            title={td('switch.tooltip.connectedDevices', { name: record.name })}
          >
            <Tag color="blue" style={{ cursor: 'pointer' }}>
              {count}
            </Tag>
          </Popover>
        );
      }
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: Switch) => renderActions(r)
    }
  ];

  const renderActions = (r: Switch) => (
    <Space size="small" wrap>
      <Button type="link" size="small" onClick={() => handleDetail(r)}>
        {tc('action.detail')}
      </Button>
      {r.has_ssh && (
        <Button type="link" size="small" onClick={() => handleEdit(r)}>
          {td('switch.remoteInfo')}
        </Button>
      )}
      <Button type="link" size="small" onClick={() => handleFullEdit(r)}>
        {tc('action.edit')}
      </Button>
      <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(r)} />
      <Button type="link" size="small" danger onClick={() => handleDelete(r)}>
        {tc('action.delete')}
      </Button>
    </Space>
  );

  const renderSwitchCard = (r: Switch) => (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => handleDetail(r)}>
          <Text strong>{r.name}</Text>
        </Button>
        <Space size={4} wrap>
          <Tag color={getSwitchRoleMeta(r.switch_role, td)?.color}>
            {getSwitchRoleMeta(r.switch_role, td)?.label ?? '-'}
          </Tag>
          {r.layer != null && (
            <Tag color={r.layer === 3 ? 'blue' : r.layer === 2 ? 'green' : 'purple'}>
              L{r.layer}
            </Tag>
          )}
        </Space>
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {r.ip_address ?? '-'}
        {r.device_model ? ` · ${r.device_model}` : ''}
      </Text>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {r.room_name ?? '-'}
        {r.protocol ? ` · ${r.protocol}` : ''}
      </Text>
      {r.connected_device_count ? (
        <Link to={`/switches/${r.device_id}`}>
          <Tag color="blue">
            {td('switch.tag.connectedDevices', { count: r.connected_device_count })}
          </Tag>
        </Link>
      ) : null}
      {renderActions(r)}
    </Space>
  );

  const switchList = data?.items ?? [];

  const batch = useBatchSelection<Switch>({
    dataSource: switchList,
    getRowKey: (r) => String(r.id),
    preserveSelectedRowKeys: true
  });
  const managedSwitches = useMemo(() => switchList.filter((s) => s.has_ssh), [switchList]);
  const unmanagedSwitches = useMemo(() => switchList.filter((s) => !s.has_ssh), [switchList]);

  const handleBatchUpdate = () => {
    const targets = batch.completeSelectedRows;
    if (targets === null) {
      message.warning(
        scopeViolationMessage(td, batch, td('switch.action.batchUpdate'), td('batch.unit'))
      );
      return;
    }
    setBatchUpdateTargets(targets);
    batchUpdate.open();
  };

  const filterAndActions = (
    <FilterBar
      filters={[
        {
          key: 'room_id',
          label: td('filter.byRoom'),
          type: 'select',
          options: roomOptions ?? [],
          width: 160
        },
        {
          key: 'device_type',
          label: td('basic.field.deviceType'),
          type: 'select',
          options: getSwitchDeviceTypeOptions(td),
          width: 120
        },
        {
          key: 'switch_role',
          label: td('switch.batchField.switchRole'),
          type: 'select',
          width: 140,
          options: getSwitchRoleOptions(td)
        }
      ]}
      table={table}
      extra={
        <>
          <Segmented
            options={[
              { value: 'group', label: td('switch.view.group') },
              { value: 'flat', label: td('switch.view.flat') }
            ]}
            value={groupMode}
            onChange={(v) => setGroupMode(v as 'group' | 'flat')}
          />
          <Button icon={<SearchOutlined />} onClick={handleScanRoom} loading={scanRoom.isPending}>
            {td('switch.action.scanRoom')}
          </Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            {td('switch.action.exportCsv')}
          </Button>
          <Button icon={<EditOutlined />} disabled={batch.count === 0} onClick={handleBatchUpdate}>
            {td('switch.action.batchUpdate')}
            {batch.count > 0 ? `(${batch.count})` : ''}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {td('switch.action.add')}
          </Button>
        </>
      }
    />
  );

  const rowSelection = batch.rowSelection;

  return (
    <div>
      {groupMode === 'flat' ? (
        /* 平铺模式：DataTable 完整渲染（搜索+工具栏+表格+分页） */
        <DataTable<Switch>
          columns={columns}
          dataSource={switchList}
          loading={isLoading}
          rowKey={(r) => String(r.id)}
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
          toolbar={filterAndActions}
          rowSelection={rowSelection}
          mobileCardMode
          cardRender={renderSwitchCard}
        />
      ) : (
        /* 分组模式：手动渲染搜索栏+工具栏，表格替换为 Collapse 按 has_ssh 分组 */
        <Card>
          <div
            style={{
              marginBottom: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8
            }}
          >
            <Space wrap>
              <SearchInput
                value={table.search}
                onSearch={table.setSearch}
                placeholder={td('switch.search.placeholder')}
              />
              <Button
                icon={<ReloadOutlined />}
                onClick={() => refetch()}
                title={tc('action.refresh')}
              />
            </Space>
            <Space>{filterAndActions}</Space>
          </div>
          <Collapse
            defaultActiveKey={['managed']}
            ghost
            items={[
              {
                key: 'managed',
                label: `${td('switch.group.managed')} (${managedSwitches.length})`,
                children: (
                  <DataTable<Switch>
                    columns={columns}
                    dataSource={managedSwitches}
                    loading={isLoading}
                    rowKey={(r) => String(r.id)}
                    pagination={false}
                    rowSelection={rowSelection}
                    searchable={false}
                    showCard={false}
                  />
                )
              },
              {
                key: 'unmanaged',
                label: `${td('switch.group.unmanaged')} (${unmanagedSwitches.length})`,
                children: (
                  <DataTable<Switch>
                    columns={columns}
                    dataSource={unmanagedSwitches}
                    loading={isLoading}
                    rowKey={(r) => String(r.id)}
                    pagination={false}
                    rowSelection={rowSelection}
                    searchable={false}
                    showCard={false}
                  />
                )
              }
            ]}
          />
        </Card>
      )}
      <SwitchForm
        open={form.isOpen}
        editRecord={editRecord}
        onClose={() => {
          form.close();
          setEditRecord(null);
          refetch();
        }}
      />
      {/* DeviceForm：新增交换机 + 完整编辑 */}
      <DeviceForm
        open={deviceForm.isOpen}
        editRecord={null}
        editDeviceId={deviceEditRecord?.id}
        defaultDeviceType={deviceEditRecord ? undefined : DeviceType.NETWORK}
        onClose={() => {
          deviceForm.close();
          setDeviceEditRecord(null);
          refetch();
        }}
      />
      {/* 批量修改远程信息 */}
      <BatchUpdateSwitchModal
        open={batchUpdate.isOpen}
        selectedSwitches={batchUpdateTargets}
        onClose={() => {
          batchUpdate.close();
          batch.clear();
          refetch();
        }}
      />
    </div>
  );
}

export default Switches;
