import { confirm } from '@/utils/confirm';
import { useConfirmAction } from '@/hooks/useConfirmAction';

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Button, Space, Tag, Popover, Segmented, Collapse, Table, Card, Input } from 'antd';
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
import {
  SWITCH_ROLE_MAP,
  SwitchRoleCode,
  DeviceType,
  SWITCH_DEVICE_TYPE_OPTIONS
} from '@/types/enums';
import { useTable } from '@/hooks/useTable';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import { useMessage } from '@/hooks/useMessage';
import { useGlobalEventListener, type GlobalEvent } from '@/hooks/useGlobalEvents';


const SCAN_TIMEOUT = 5 * 60_000;

function Switches() {
  const table = useTable();
  const navigate = useNavigate();

  const [formOpen, setFormOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<Switch | null>(null);
  
  const [deviceFormOpen, setDeviceFormOpen] = useState(false);
  const [deviceEditRecord, setDeviceEditRecord] = useState<Device | null>(null);
  
  const [groupMode, setGroupMode] = useState<'group' | 'flat'>('group');
  
  const [batchUpdateOpen, setBatchUpdateOpen] = useState(false);
  
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
      message.warning('请先选择机房');
      return;
    }
    confirm({
      title: '扫描机房',
      content: `将对机房内所有网络设备执行全量扫描，可能需要较长时间。`,
      onOk: async () => {
        try {
          await scanRoom.mutateAsync(roomId);
          setScanningRoomId(roomId);
          message.info('机房扫描已提交，完成后将通过消息通知您');
          
          scanTimeoutRef.current = setTimeout(() => {
            scanTimeoutRef.current = null;
            setScanningRoomId(null);
          }, SCAN_TIMEOUT);
        } catch {
          message.error('机房扫描提交失败');
        }
      }
    });
  };

  
  const handleAdd = () => {
    setDeviceEditRecord(null);
    setDeviceFormOpen(true);
  };
  
  const handleEdit = (r: Switch) => {
    setEditRecord(r);
    setFormOpen(true);
  };
  
  const handleFullEdit = (r: Switch) => {
    
    
    setDeviceEditRecord({ id: r.device_id } as Device);
    setDeviceFormOpen(true);
  };
  
  const handleDetail = (r: Switch) => navigate(`/switches/${r.device_id}`);
  
  const confirmAction = useConfirmAction();
  const handleDelete = (r: Switch) => {
    confirmAction({
      title: '确认删除',
      content: `确定要删除网络设备「${r.name}」吗？`,
      okType: 'danger',
      successMessage: '删除成功',
      onConfirm: () => deleteSwitch.mutateAsync(r.device_id),
      afterConfirm: refetch
    });
  };

  
  const handleCopy = (r: Switch) => {
    const text = `名称: ${r.name}\nIP: ${r.ip_address}\n类型: ${SWITCH_ROLE_MAP[r.switch_role as SwitchRoleCode]?.label ?? '-'}\n型号: ${r.device_model ?? '-'}\n机房: ${r.room_name ?? '-'}\n协议: ${r.protocol ?? '-'}\n设备类型: ${r.device_type ?? '-'}`;
    navigator.clipboard.writeText(text).then(() => message.success('已复制'));
  };

  
  const handleExport = useCallback(() => {
    const items = data?.items ?? [];
    if (!items.length) {
      message.warning('无数据可导出');
      return;
    }
    const headers = ['名称', '管理IP', '类型', '型号', '机房', '协议', '设备类型'];
    const rows = items.map((r) => [
      r.name,
      r.ip_address,
      SWITCH_ROLE_MAP[r.switch_role as SwitchRoleCode]?.label ?? String(r.switch_role),
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
  }, [data]);

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string, r: Switch) => (
        <Button type="link" size="small" onClick={() => handleDetail(r)}>
          {v}
        </Button>
      )
    },
    { title: '管理IP', dataIndex: 'ip_address', key: 'ip_address' },
    {
      title: '类型',
      dataIndex: 'switch_role',
      key: 'switch_role',
      render: (v: number) => (
        <Tag color={SWITCH_ROLE_MAP[v as SwitchRoleCode]?.color}>
          {SWITCH_ROLE_MAP[v as SwitchRoleCode]?.label ?? '-'}
        </Tag>
      )
    },
    {
      title: '层级',
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
      title: '上行设备',
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
      title: '上行端口',
      dataIndex: 'uplink_port_names',
      key: 'uplink_port_names',
      width: 120,
      render: (v: string[] | null) => (v?.length ? v.join(', ') : '-')
    },
    {
      title: '型号',
      dataIndex: 'device_model',
      key: 'device_model',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '机房',
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      render: (v: string | null) => v ?? '-'
    },
    
    {
      title: '关联设备',
      dataIndex: 'connected_device_count',
      key: 'connected_device_count',
      width: 90,
      sorter: true,
      render: (count: number, record: Switch) => {
        if (!count) return <Tag>0</Tag>;
        return (
          <Popover
            content={<Link to={`/switches/${record.device_id}`}>查看详情</Link>}
            title={`${record.name} 关联设备`}
          >
            <Tag color="blue" style={{ cursor: 'pointer' }}>
              {count}
            </Tag>
          </Popover>
        );
      }
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: Switch) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleDetail(r)}>
            详情
          </Button>
          {r.has_ssh && (
            <Button type="link" size="small" onClick={() => handleEdit(r)}>
              远程信息管理
            </Button>
          )}
          <Button type="link" size="small" onClick={() => handleFullEdit(r)}>
            编辑
          </Button>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(r)} />
          <Button type="link" size="small" danger onClick={() => handleDelete(r)}>
            删除
          </Button>
        </Space>
      )
    }
  ];

  
  const switchList = data?.items ?? [];

  const batch = useBatchSelection<Switch>({
    dataSource: switchList,
    getRowKey: (r) => String(r.id),
    preserveSelectedRowKeys: true
  });
  const managedSwitches = useMemo(() => switchList.filter((s) => s.has_ssh), [switchList]);
  const unmanagedSwitches = useMemo(() => switchList.filter((s) => !s.has_ssh), [switchList]);

  
  const filterAndActions = (
    <FilterBar
      filters={[
        {
          key: 'room_id',
          label: '按机房筛选',
          type: 'select',
          options: roomOptions ?? [],
          width: 160
        },
        {
          key: 'device_type',
          label: '设备类型',
          type: 'select',
          options: SWITCH_DEVICE_TYPE_OPTIONS,
          width: 120
        },
        {
          key: 'switch_role',
          label: '设备角色',
          type: 'select',
          width: 140,
          options: Object.entries(SWITCH_ROLE_MAP).map(([k, v]) => ({
            label: v.label,
            value: Number(k)
          }))
        }
      ]}
      table={table}
      extra={
        <>
          <Segmented
            options={[
              { value: 'group', label: '分组视图' },
              { value: 'flat', label: '平铺视图' }
            ]}
            value={groupMode}
            onChange={(v) => setGroupMode(v as 'group' | 'flat')}
          />
          <Button icon={<SearchOutlined />} onClick={handleScanRoom} loading={scanRoom.isPending}>
            扫描机房
          </Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            导出CSV
          </Button>
          <Button
            icon={<EditOutlined />}
            disabled={batch.count === 0}
            onClick={() => setBatchUpdateOpen(true)}
          >
            批量修改{batch.count > 0 ? `(${batch.count})` : ''}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增网络设备
          </Button>
        </>
      }
    />
  );

  
  const selectedSwitches = batch.selectedRows;

  
  const rowSelection = batch.rowSelection;

  return (
    <div>
      {groupMode === 'flat' ? (
        
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
        />
      ) : (
        
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
                placeholder="搜索网络设备..."
              />
              <Button icon={<ReloadOutlined />} onClick={() => refetch()} title="刷新" />
            </Space>
            <Space>{filterAndActions}</Space>
          </div>
          <Collapse
            defaultActiveKey={['managed']}
            ghost
            items={[
              {
                key: 'managed',
                label: `有管理权限 (${managedSwitches.length})`,
                children: (
                  <Table<Switch>
                    columns={columns}
                    dataSource={managedSwitches}
                    loading={isLoading}
                    rowKey={(r) => String(r.id)}
                    pagination={false}
                    scroll={{ x: 'max-content' }}
                    rowSelection={rowSelection}
                  />
                )
              },
              {
                key: 'unmanaged',
                label: `无管理权限 (${unmanagedSwitches.length})`,
                children: (
                  <Table<Switch>
                    columns={columns}
                    dataSource={unmanagedSwitches}
                    loading={isLoading}
                    rowKey={(r) => String(r.id)}
                    pagination={false}
                    scroll={{ x: 'max-content' }}
                    rowSelection={rowSelection}
                  />
                )
              }
            ]}
          />
        </Card>
      )}
      <SwitchForm
        open={formOpen}
        editRecord={editRecord}
        onClose={() => {
          setFormOpen(false);
          setEditRecord(null);
          refetch();
        }}
      />
      {}
      <DeviceForm
        open={deviceFormOpen}
        editRecord={null}
        editDeviceId={deviceEditRecord?.id}
        defaultDeviceType={deviceEditRecord ? undefined : DeviceType.NETWORK}
        onClose={() => {
          setDeviceFormOpen(false);
          setDeviceEditRecord(null);
          refetch();
        }}
      />
      {}
      <BatchUpdateSwitchModal
        open={batchUpdateOpen}
        selectedSwitches={selectedSwitches}
        onClose={() => {
          setBatchUpdateOpen(false);
          batch.clear();
          refetch();
        }}
      />
    </div>
  );
}

export default Switches;
