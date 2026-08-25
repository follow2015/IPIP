import { confirm } from '@/utils/confirm';
import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, Space, Tag, Tooltip, Modal } from 'antd';
import {
  CopyOutlined,
  StopOutlined,
  CheckCircleOutlined,
  TeamOutlined,
  EditOutlined
} from '@ant-design/icons';
import DataTable from '@/components/DataTable';
import { isPrivateIPv4, isPrivateNetwork } from '@/utils/ip';
import {
  useIPList,
  useIPDetail,
  useUpdateIPCustomer,
  useUpdateIPNotes,
  usePingIP,
  useScanIP,
  useBanIP,
  useUnbanIP,
  useBatchBanIP,
  useBatchUnbanIP,
  useBatchUpdateIPCustomer,
  useBatchUpdateIPNotes,
  useIPStatistics
} from '@/services/ip';
import { useScanNetwork } from '@/services/network';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useRoomOptions } from '@/services/room';
import type { IPAddress, PingResult, IPScanResult } from '@/types/models';
import { IP_STATUS_MAP, IPStatusCode } from '@/types/enums';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import { useCopyInfo } from '@/utils/clipboard';
import { exportCSV } from '@/utils/csv';
import { useGlobalEventListener } from '@/hooks/useGlobalEvents';
import type { GlobalEvent } from '@/hooks/useGlobalEvents';
import { useBatchSelection } from '@/hooks/useBatchSelection';
import { BatchActionBar } from '@/components/BatchActionBar';
import { IPEditModal } from './IPEditModal';
import { IPDetailModal } from './IPDetailModal';
import { IPBatchBanModal } from './IPBatchBanModal';
import { IPBatchEditModal } from './IPBatchEditModal';
import { IPStatsModal } from './IPStatsModal';
import { IPTableToolbar } from './IPTableToolbar';

function IP() {
  const table = useTable();
  const [urlParams] = useSearchParams();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [batchBanOpen, setBatchBanOpen] = useState(false);
  const [batchEditOpen, setBatchEditOpen] = useState(false);
  const [batchEditMode, setBatchEditMode] = useState<'customer' | 'notes'>('customer');
  const [statsOpen, setStatsOpen] = useState(false);
  const [selectedIP, setSelectedIP] = useState<IPAddress | null>(null);
  const [detailAddress, setDetailAddress] = useState('');

  useEffect(() => {
    const search = urlParams.get('search');
    const roomId = urlParams.get('room_id');
    if (search) table.setSearch(search);
    if (roomId) table.updateFilter('room_id', roomId);
  }, []);

  const updateIPCustomer = useUpdateIPCustomer();
  const updateIPNotes = useUpdateIPNotes();
  const pingIP = usePingIP();
  const scanIP = useScanIP();
  const scanNetwork = useScanNetwork();
  const banIP = useBanIP();
  const unbanIP = useUnbanIP();
  const batchBanIP = useBatchBanIP();
  const batchUnbanIP = useBatchUnbanIP();
  const batchUpdateIPCustomer = useBatchUpdateIPCustomer();
  const batchUpdateIPNotes = useBatchUpdateIPNotes();
  const msg = useMessage();
  const copyInfo = useCopyInfo();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const { data: roomOptions } = useRoomOptions();

  const { data: ipStats } = useIPStatistics(
    table.filters.room_id ? Number(table.filters.room_id) : undefined,
    table.search || undefined
  );

  const { data: ipDetail, isLoading: loadingDetail } = useIPDetail(detailAddress);

  const { data, isLoading, refetch } = useIPList({
    page: table.page,
    per_page: table.perPage,
    search: table.search || undefined,
    status: table.filters.status ? Number(table.filters.status) : undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
  });

  const batch = useBatchSelection<IPAddress>({
    dataSource: data?.items ?? [],
    getRowKey: (r) => r.ip_address
  });

  useGlobalEventListener(
    useCallback(
      (event: GlobalEvent) => {
        if (event.event_type === 'ip_scan_complete') {
          refetch();
          return;
        }
        if (event.event_type === 'scan_failed') {
          refetch();
          return;
        }
      },
      [refetch]
    )
  );

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refetch();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [refetch]);

  const handleEdit = (record: IPAddress) => {
    setSelectedIP(record);
    setEditModalOpen(true);
  };

  const handleDetail = (record: IPAddress) => {
    setDetailAddress(record.ip_address);
    setDetailModalOpen(true);
  };

  const handleBan = (record: IPAddress) => {
    confirm({
      title: '确认封禁',
      content: `确定要封禁 IP「${record.ip_address}」吗？将通过核心交换机下发黑洞路由。`,
      okType: 'danger',
      onOk: async () => {
        try {
          const result = await banIP.mutateAsync({
            ip_address: record.ip_address
          });
          msg.success(result.message || `IP ${result.data.ip_address} 已封禁`);
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : '封禁失败');
        }
      }
    });
  };

  const handleUnban = (record: IPAddress) => {
    confirm({
      title: '确认解封',
      content: `确定要解封 IP「${record.ip_address}」吗？将撤销封禁规则。`,
      onOk: async () => {
        try {
          const result = await unbanIP.mutateAsync({
            ip_address: record.ip_address,
            room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
          });
          msg.success(result.message || `IP ${result.data.ip_address} 已解封`);
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : '解封失败');
        }
      }
    });
  };

  const handleBatchBanSubmit = async (ips: string[]) => {
    if (!ips.length) {
      msg.warning('请输入IP地址');
      return;
    }
    try {
      await batchBanIP.mutateAsync({ ip_list: ips });
      msg.info('批量封禁已提交，完成后将通过消息通知您');
      setBatchBanOpen(false);
      refetch();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '批量封禁失败');
    }
  };

  const handleBatchBanSelected = () => {
    if (!batch.count) {
      msg.warning('请先选择IP');
      return;
    }
    confirm({
      title: '确认批量封禁',
      content: `确定要封禁选中的 ${batch.count} 个IP吗？将通过核心交换机下发黑洞路由。`,
      okType: 'danger',
      onOk: async () => {
        try {
          await batchBanIP.mutateAsync({
            ip_list: batch.selectedKeys.map(String)
          });
          msg.info(`批量封禁已提交，完成后将通过消息通知您`);
          batch.clear();
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : '批量封禁失败');
        }
      }
    });
  };

  const handleBatchUnbanSelected = () => {
    if (!batch.count) {
      msg.warning('请先选择IP');
      return;
    }
    confirm({
      title: '确认批量解封',
      content: `确定要解封选中的 ${batch.count} 个IP吗？将撤销封禁规则。`,
      onOk: async () => {
        try {
          await batchUnbanIP.mutateAsync({
            ip_list: batch.selectedKeys.map(String),
            room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
          });
          msg.info(`批量解封已提交，完成后将通过消息通知您`);
          batch.clear();
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : '批量解封失败');
        }
      }
    });
  };

  const openBatchEdit = (mode: 'customer' | 'notes') => {
    if (!batch.count) {
      msg.warning('请先选择IP');
      return;
    }
    setBatchEditMode(mode);
    setBatchEditOpen(true);
  };

  const handleBatchEditSubmit = async (values: { customer_id?: number | null; notes?: string }) => {
    const ip_list = batch.selectedKeys.map(String);
    const room_id = table.filters.room_id ? Number(table.filters.room_id) : undefined;
    try {
      if (values.customer_id !== undefined) {
        await batchUpdateIPCustomer.mutateAsync({
          ip_list,
          customer_id: values.customer_id,
          room_id
        });
        msg.success(`已为 ${ip_list.length} 个 IP 分配客户`);
      } else if (values.notes !== undefined) {
        await batchUpdateIPNotes.mutateAsync({ ip_list, notes: values.notes, room_id });
        msg.success(`已更新 ${ip_list.length} 个 IP 的备注`);
      }
      setBatchEditOpen(false);
      batch.clear();
      refetch();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '批量更新失败');
    }
  };

  const handlePing = async (record: IPAddress) => {
    try {
      const result = await pingIP.mutateAsync(record.ip_address);
      const r = result.data as unknown as PingResult;
      if (r?.reachable) {
        msg.success(`${record.ip_address} 可达`);
      } else {
        msg.warning(`${record.ip_address} 不可达`);
      }
    } catch {
      msg.error('Ping 失败');
    }
  };

  const handleScan = async (record: IPAddress) => {
    try {
      const result = await scanIP.mutateAsync(record.ip_address);
      const r = result.data as unknown as IPScanResult;
      Modal.info({
        title: `扫描结果 - ${record.ip_address}`,
        content: <p>开放端口: {r?.open_ports?.join(', ') || '无'}</p>,
        width: 480
      });
    } catch {
      msg.error('扫描失败');
    }
  };

  const handleCopy = (record: IPAddress) => {
    const text = `IP: ${record.ip_address}\nMAC: ${record.mac_address ?? 'N/A'}\n交换机: ${record.switch_name ?? '-'}\n端口: ${record.port ?? '-'}\n机房: ${record.room_name ?? '-'}\n客户: ${record.customer_name ?? '-'}\n状态: ${IP_STATUS_MAP[record.status as IPStatusCode]?.label ?? record.status}`;
    copyInfo(text);
  };

  const handleExport = () => {
    const items = data?.items ?? [];
    if (!items.length) {
      msg.warning('无数据可导出');
      return;
    }
    const headers = ['IP地址', 'MAC地址', '交换机', '端口', '机房', '客户', '状态', '备注'];
    const rows = items.map((r) => [
      r.ip_address,
      r.mac_address ?? '',
      r.switch_name ?? '',
      r.port ?? '',
      r.room_name ?? '',
      r.customer_name ?? '',
      IP_STATUS_MAP[r.status as IPStatusCode]?.label ?? String(r.status),
      r.notes ?? ''
    ]);
    exportCSV(headers, rows, { filename: 'ip_addresses' });
  };

  const handleEditSubmit = async (values: { customer_id?: number; notes?: string }) => {
    if (!selectedIP) return;
    try {
      if (values.customer_id !== undefined) {
        await updateIPCustomer.mutateAsync({
          address: selectedIP.ip_address,
          data: { customer_id: values.customer_id }
        });
      }
      if (values.notes !== undefined) {
        await updateIPNotes.mutateAsync({ address: selectedIP.ip_address, notes: values.notes });
      }
      msg.success('更新成功');
      setEditModalOpen(false);
      refetch();
    } catch (err) {
      if (err instanceof Error) msg.error(err.message);
    }
  };

  const handleScanNetwork = () => {
    if (!table.filters.room_id) {
      msg.warning('请先选择机房');
      return;
    }
    if (!table.search) {
      msg.warning('请先在搜索框输入网段地址（如 10.10.1.0/24）');
      return;
    }
    if (isPrivateNetwork(table.search)) {
      msg.warning('私网地址跨网不可达，状态由ARP表判断');
      return;
    }
    confirm({
      title: '扫描网段内所有IP',
      content: `将扫描网段 ${table.search} 内所有IP状态，扫描在后台执行，完成后自动刷新。`,
      onOk: async () => {
        try {
          await scanNetwork.mutateAsync({
            ipNetwork: table.search,
            roomId: Number(table.filters.room_id)
          });
          msg.info('网段扫描已提交，完成后将通过消息通知您');
        } catch {
          msg.error('扫描启动失败');
        }
      }
    });
  };

  const columns = [
    { title: 'IP地址', dataIndex: 'ip_address', key: 'ip_address' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => {
        const info = IP_STATUS_MAP[v as IPStatusCode];
        return <Tag color={info?.color}>{info?.label ?? '未知'}</Tag>;
      }
    },
    {
      title: '交换机',
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    { title: '端口', dataIndex: 'port', key: 'port', render: (v: string | null) => v || '-' },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '机房',
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: 'MAC地址',
      dataIndex: 'mac_address',
      key: 'mac_address',
      render: (v: string) => (v === 'N/A' ? '-' : v)
    },
    { title: '备注', dataIndex: 'notes', key: 'notes', render: (v: string | null) => v || '-' },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: IPAddress) => {
        const isPrivate = isPrivateIPv4(record.ip_address);
        return (
          <Space wrap>
            <Button type="link" size="small" onClick={() => handleDetail(record)}>
              详情
            </Button>
            <Button type="link" size="small" onClick={() => handleEdit(record)}>
              编辑
            </Button>
            {isPrivate ? (
              <Tooltip title="私网地址跨网不可达">
                <Button type="link" size="small" disabled>
                  Ping
                </Button>
              </Tooltip>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => handlePing(record)}
                loading={pingIP.isPending}
              >
                Ping
              </Button>
            )}
            {isPrivate ? (
              <Tooltip title="私网地址跨网不可达">
                <Button type="link" size="small" disabled>
                  扫描
                </Button>
              </Tooltip>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => handleScan(record)}
                loading={scanIP.isPending}
              >
                扫描
              </Button>
            )}
            {record.status === IPStatusCode.BANNED ? (
              <Tooltip title="解封IP">
                <Button
                  type="link"
                  size="small"
                  icon={<CheckCircleOutlined />}
                  onClick={() => handleUnban(record)}
                  style={{ color: '#52c41a' }}
                />
              </Tooltip>
            ) : record.status === IPStatusCode.PENDING_BAN ||
              record.status === IPStatusCode.PENDING_UNBAN ? (
              <Tooltip
                title={
                  record.status === IPStatusCode.PENDING_BAN ? '封禁中，请稍候' : '解封中，请稍候'
                }
              >
                <Button type="link" size="small" icon={<StopOutlined />} disabled />
              </Tooltip>
            ) : (
              <Tooltip title="封禁IP（黑洞路由）">
                <Button
                  type="link"
                  size="small"
                  icon={<StopOutlined />}
                  onClick={() => handleBan(record)}
                  danger
                />
              </Tooltip>
            )}
            <Button
              type="link"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(record)}
            />
          </Space>
        );
      }
    }
  ];

  return (
    <>
      <BatchActionBar count={batch.count} unit="个IP" onClear={batch.clear}>
        <Button
          size="small"
          danger
          icon={<StopOutlined />}
          onClick={handleBatchBanSelected}
          loading={batchBanIP.isPending}
        >
          批量封禁
        </Button>
        <Button
          size="small"
          icon={<CheckCircleOutlined />}
          style={{ color: '#52c41a', borderColor: '#b7eb8f' }}
          onClick={handleBatchUnbanSelected}
          loading={batchUnbanIP.isPending}
        >
          批量解封
        </Button>
        <Button
          size="small"
          icon={<TeamOutlined />}
          onClick={() => openBatchEdit('customer')}
          loading={batchUpdateIPCustomer.isPending}
        >
          批量分配客户
        </Button>
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => openBatchEdit('notes')}
          loading={batchUpdateIPNotes.isPending}
        >
          批量修改备注
        </Button>
      </BatchActionBar>

      <DataTable<IPAddress>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="ip_address"
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
        searchPlaceholder="按IP或MAC地址搜索"
        toolbar={
          <IPTableToolbar
            table={table}
            roomOptions={roomOptions ?? []}
            scanNetworkPending={scanNetwork.isPending}
            onOpenBatchBan={() => {
              setBatchBanOpen(true);
            }}
            onOpenStats={() => setStatsOpen(true)}
            onExport={handleExport}
            onScanNetwork={handleScanNetwork}
          />
        }
        rowSelection={batch.rowSelection}
      />

      <IPEditModal
        open={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        ip={selectedIP}
        customerOptions={customerOptions ?? []}
        submitting={updateIPCustomer.isPending || updateIPNotes.isPending}
        onSubmit={handleEditSubmit}
      />

      <IPDetailModal
        open={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        detailAddress={detailAddress}
        loading={loadingDetail}
        detail={ipDetail}
      />

      <IPBatchBanModal
        open={batchBanOpen}
        onClose={() => setBatchBanOpen(false)}
        submitting={batchBanIP.isPending}
        onSubmit={handleBatchBanSubmit}
      />

      <IPStatsModal
        open={statsOpen}
        onClose={() => setStatsOpen(false)}
        stats={ipStats}
        scopeLabel={
          table.search || table.filters.room_id
            ? `统计范围：${table.filters.room_id ? '机房筛选 + ' : ''}${table.search ? `搜索"${table.search}"` : '全部'}`
            : undefined
        }
      />

      <IPBatchEditModal
        open={batchEditOpen}
        mode={batchEditMode}
        count={batch.count}
        customerOptions={customerOptions ?? []}
        submitting={batchUpdateIPCustomer.isPending || batchUpdateIPNotes.isPending}
        onClose={() => setBatchEditOpen(false)}
        onSubmit={handleBatchEditSubmit}
      />
    </>
  );
}

export default IP;
