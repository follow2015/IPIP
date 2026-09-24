import { useConfirm } from '@/utils/confirm';
import { useState, useEffect, useCallback } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
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
import { useSwitchOptions } from '@/services/switch';
import type { IPAddress, PingResult, IPScanResult } from '@/types/models';
import { IPStatusCode } from '@/types/enums';
import { getIPStatusMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
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
  const { t: td } = useTranslation('device');
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
  const table = useTable();
  const [urlParams] = useSearchParams();
  const editModal = useDisclosure();
  const detailModal = useDisclosure();
  const batchBan = useDisclosure();
  const batchEdit = useDisclosure();
  const [batchEditMode, setBatchEditMode] = useState<'customer' | 'notes'>('customer');
  const stats = useDisclosure();
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
  const { data: switchOptions } = useSwitchOptions(
    table.filters.room_id ? Number(table.filters.room_id) : undefined
  );

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
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    customer_id: table.filters.customer_id ? Number(table.filters.customer_id) : undefined,
    switch_id: table.filters.switch_id ? Number(table.filters.switch_id) : undefined
  });

  const batch = useBatchSelection<IPAddress>({
    dataSource: data?.items ?? [],
    getRowKey: (r) => `${r.ip_address}|${r.room_id ?? ''}|${r.id ?? ''}`
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
    editModal.open();
  };

  const handleDetail = (record: IPAddress) => {
    setDetailAddress(record.ip_address);
    detailModal.open();
  };

  const handleBan = (record: IPAddress) => {
    confirm({
      title: t('ip.confirm.banTitle'),
      content: t('ip.confirm.banContent', { address: record.ip_address }),
      okType: 'danger',
      onOk: async () => {
        try {
          const result = await banIP.mutateAsync({
            ip_address: record.ip_address
          });
          msg.success(
            result.message || t('ip.message.banned', { address: result.data.ip_address })
          );
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : t('ip.message.banFailed'));
        }
      }
    });
  };

  const handleUnban = (record: IPAddress) => {
    confirm({
      title: t('ip.confirm.unbanTitle'),
      content: t('ip.confirm.unbanContent', { address: record.ip_address }),
      onOk: async () => {
        try {
          const result = await unbanIP.mutateAsync({
            ip_address: record.ip_address,
            room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
          });
          msg.success(
            result.message || t('ip.message.unbanned', { address: result.data.ip_address })
          );
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : t('ip.message.unbanFailed'));
        }
      }
    });
  };

  const handleBatchBanSubmit = async (ips: string[]) => {
    if (!ips.length) {
      msg.warning(t('ip.message.inputIpRequired'));
      return;
    }
    try {
      await batchBanIP.mutateAsync({ ip_list: ips });
      msg.info(t('ip.message.batchBanSubmitted'));
      batchBan.close();
      refetch();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : t('ip.message.batchBanFailed'));
    }
  };

  const handleBatchBanSelected = () => {
    if (!batch.count) {
      msg.warning(t('ip.message.selectIpFirst'));
      return;
    }
    confirm({
      title: t('ip.confirm.batchBanTitle'),
      content: t('ip.confirm.batchBanContent', { count: batch.count }),
      okType: 'danger',
      onOk: async () => {
        try {
          await batchBanIP.mutateAsync({
            ip_list: batch.selectedKeys.map((k) => String(k).split('|')[0])
          });
          msg.info(t('ip.message.batchBanSubmitted'));
          batch.clear();
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : t('ip.message.batchBanFailed'));
        }
      }
    });
  };

  const handleBatchUnbanSelected = () => {
    if (!batch.count) {
      msg.warning(t('ip.message.selectIpFirst'));
      return;
    }
    confirm({
      title: t('ip.confirm.batchUnbanTitle'),
      content: t('ip.confirm.batchUnbanContent', { count: batch.count }),
      onOk: async () => {
        try {
          await batchUnbanIP.mutateAsync({
            ip_list: batch.selectedKeys.map((k) => String(k).split('|')[0]),
            room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined
          });
          msg.info(t('ip.message.batchUnbanSubmitted'));
          batch.clear();
          refetch();
        } catch (err) {
          msg.error(err instanceof Error ? err.message : t('ip.message.batchUnbanFailed'));
        }
      }
    });
  };

  const openBatchEdit = (mode: 'customer' | 'notes') => {
    if (!batch.count) {
      msg.warning(t('ip.message.selectIpFirst'));
      return;
    }
    setBatchEditMode(mode);
    batchEdit.open();
  };

  const handleBatchEditSubmit = async (values: { customer_id?: number | null; notes?: string }) => {
    const keys = batch.selectedKeys.map(String);
    const groups = new Map<number, string[]>();
    for (const k of keys) {
      const [ip, rid] = k.split('|');
      const roomId = !rid ? NaN : Number(rid);
      if (!groups.has(roomId)) groups.set(roomId, []);
      groups.get(roomId)!.push(ip);
    }
    const viewRoomId = table.filters.room_id ? Number(table.filters.room_id) : undefined;
    try {
      if (values.customer_id !== undefined) {
        for (const [roomId, ips] of groups) {
          await batchUpdateIPCustomer.mutateAsync({
            ip_list: ips,
            customer_id: values.customer_id,
            room_id: viewRoomId ?? (Number.isNaN(roomId) ? undefined : roomId)
          });
        }
        msg.success(t('ip.message.batchCustomerAssigned', { count: keys.length }));
      } else if (values.notes !== undefined) {
        for (const [roomId, ips] of groups) {
          await batchUpdateIPNotes.mutateAsync({
            ip_list: ips,
            notes: values.notes,
            room_id: viewRoomId ?? (Number.isNaN(roomId) ? undefined : roomId)
          });
        }
        msg.success(t('ip.message.batchNotesUpdated', { count: keys.length }));
      }
      batchEdit.close();
      batch.clear();
      refetch();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : t('ip.message.batchUpdateFailed'));
    }
  };

  const handlePing = async (record: IPAddress) => {
    try {
      const result = await pingIP.mutateAsync(record.ip_address);
      const r = result.data as unknown as PingResult;
      if (r?.reachable) {
        msg.success(t('ip.message.pingReachable', { address: record.ip_address }));
      } else {
        msg.warning(t('ip.message.pingUnreachable', { address: record.ip_address }));
      }
    } catch {
      msg.error(t('ip.message.pingFailed'));
    }
  };

  const handleScan = async (record: IPAddress) => {
    try {
      const result = await scanIP.mutateAsync(record.ip_address);
      const r = result.data as unknown as IPScanResult;
      Modal.info({
        title: t('ip.scanResult.title', { address: record.ip_address }),
        content: (
          <p>
            {t('ip.scanResult.openPorts', {
              ports: r?.open_ports?.join(', ') || t('ip.scanResult.none')
            })}
          </p>
        ),
        width: 480
      });
    } catch {
      msg.error(t('ip.message.scanFailed'));
    }
  };

  const handleCopy = (record: IPAddress) => {
    const text = [
      t('ip.copy.ip', { value: record.ip_address }),
      t('ip.copy.mac', { value: record.mac_address ?? 'N/A' }),
      t('ip.copy.switch', { value: record.switch_name ?? '-' }),
      t('ip.copy.port', { value: record.port ?? '-' }),
      t('ip.copy.room', { value: record.room_name ?? '-' }),
      t('ip.copy.customer', { value: record.customer_name ?? '-' }),
      t('ip.copy.status', {
        value: getIPStatusMeta(record.status, td)?.label ?? record.status
      })
    ].join('\n');
    copyInfo(text);
  };

  const handleExport = () => {
    const items = data?.items ?? [];
    if (!items.length) {
      msg.warning(t('ip.message.noDataToExport'));
      return;
    }
    const headers = [
      t('ip.field.ipAddress'),
      t('ip.field.macAddress'),
      t('ip.field.switch'),
      t('ip.field.port'),
      t('ip.field.room'),
      t('ip.field.customer'),
      t('ip.field.status'),
      t('ip.field.notes')
    ];
    const rows = items.map((r) => [
      r.ip_address,
      r.mac_address ?? '',
      r.switch_name ?? '',
      r.port ?? '',
      r.room_name ?? '',
      r.customer_name ?? '',
      getIPStatusMeta(r.status, td)?.label ?? String(r.status),
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
          data: { customer_id: values.customer_id, room_id: selectedIP.room_id ?? undefined }
        });
      }
      if (values.notes !== undefined) {
        await updateIPNotes.mutateAsync({
          address: selectedIP.ip_address,
          notes: values.notes,
          room_id: selectedIP.room_id ?? undefined
        });
      }
      msg.success(tc('message.updateSuccess'));
      editModal.close();
      refetch();
    } catch (err) {
      if (err instanceof Error) msg.error(err.message);
    }
  };

  const handleScanNetwork = () => {
    if (!table.filters.room_id) {
      msg.warning(t('ip.message.selectRoomFirst'));
      return;
    }
    if (!table.search) {
      msg.warning(t('ip.message.inputNetworkFirst'));
      return;
    }
    if (isPrivateNetwork(table.search)) {
      msg.warning(t('ip.message.privateNetworkUnreachable'));
      return;
    }
    confirm({
      title: t('ip.confirm.scanNetworkTitle'),
      content: t('ip.confirm.scanNetworkContent', { network: table.search }),
      onOk: async () => {
        try {
          await scanNetwork.mutateAsync({
            ipNetwork: table.search,
            roomId: Number(table.filters.room_id)
          });
          msg.info(t('ip.message.scanNetworkSubmitted'));
        } catch {
          msg.error(t('ip.message.scanNetworkFailed'));
        }
      }
    });
  };

  const columns = [
    { title: t('ip.field.ipAddress'), dataIndex: 'ip_address', key: 'ip_address' },
    {
      title: t('ip.field.status'),
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => {
        const info = getIPStatusMeta(v, td);
        return <Tag color={info?.color}>{info?.label ?? tc('field.unknown')}</Tag>;
      }
    },
    {
      title: t('ip.field.switch'),
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('ip.field.port'),
      dataIndex: 'port',
      key: 'port',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('ip.field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('ip.field.room'),
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('ip.field.macAddress'),
      dataIndex: 'mac_address',
      key: 'mac_address',
      render: (v: string) => (v === 'N/A' ? '-' : v)
    },
    {
      title: t('ip.field.notes'),
      dataIndex: 'notes',
      key: 'notes',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('ip.field.actions'),
      key: 'action',
      render: (_: unknown, record: IPAddress) => {
        const isPrivate = isPrivateIPv4(record.ip_address);
        return (
          <Space wrap>
            <Button type="link" size="small" onClick={() => handleDetail(record)}>
              {t('ip.action.detail')}
            </Button>
            <Button type="link" size="small" onClick={() => handleEdit(record)}>
              {t('ip.action.edit')}
            </Button>
            {isPrivate ? (
              <Tooltip title={t('ip.tooltip.privateUnreachable')}>
                <Button type="link" size="small" disabled>
                  Ping
                </Button>
              </Tooltip>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => handlePing(record)}
                loading={pingIP.isPending && pingIP.variables === record.ip_address}
              >
                Ping
              </Button>
            )}
            {isPrivate ? (
              <Tooltip title={t('ip.tooltip.privateUnreachable')}>
                <Button type="link" size="small" disabled>
                  {t('ip.action.scan')}
                </Button>
              </Tooltip>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => handleScan(record)}
                loading={scanIP.isPending && scanIP.variables === record.ip_address}
              >
                {t('ip.action.scan')}
              </Button>
            )}
            {record.status === IPStatusCode.BANNED ? (
              <Tooltip title={t('ip.tooltip.unban')}>
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
                  record.status === IPStatusCode.PENDING_BAN
                    ? t('ip.tooltip.banning')
                    : t('ip.tooltip.unbanning')
                }
              >
                <Button type="link" size="small" icon={<StopOutlined />} disabled />
              </Tooltip>
            ) : (
              <Tooltip title={t('ip.tooltip.ban')}>
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
      <BatchActionBar count={batch.count} unit={t('ip.unit')} onClear={batch.clear}>
        <Button
          size="small"
          danger
          icon={<StopOutlined />}
          onClick={handleBatchBanSelected}
          loading={batchBanIP.isPending}
        >
          {t('ip.action.batchBan')}
        </Button>
        <Button
          size="small"
          icon={<CheckCircleOutlined />}
          style={{ color: '#52c41a', borderColor: '#b7eb8f' }}
          onClick={handleBatchUnbanSelected}
          loading={batchUnbanIP.isPending}
        >
          {t('ip.action.batchUnban')}
        </Button>
        <Button
          size="small"
          icon={<TeamOutlined />}
          onClick={() => openBatchEdit('customer')}
          loading={batchUpdateIPCustomer.isPending}
        >
          {t('ip.action.batchAssignCustomer')}
        </Button>
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => openBatchEdit('notes')}
          loading={batchUpdateIPNotes.isPending}
        >
          {t('ip.action.batchEditNotes')}
        </Button>
      </BatchActionBar>

      <DataTable<IPAddress>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(r) => `${r.ip_address}|${r.room_id ?? ''}|${r.id ?? ''}`}
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
        searchPlaceholder={t('ip.searchPlaceholder')}
        toolbar={
          <IPTableToolbar
            table={table}
            roomOptions={roomOptions ?? []}
            customerOptions={customerOptions ?? []}
            switchOptions={switchOptions ?? []}
            scanNetworkPending={scanNetwork.isPending}
            onOpenBatchBan={() => {
              batchBan.open();
            }}
            onOpenStats={() => stats.open()}
            onExport={handleExport}
            onScanNetwork={handleScanNetwork}
          />
        }
        rowSelection={batch.rowSelection}
      />

      <IPEditModal
        open={editModal.isOpen}
        onClose={() => editModal.close()}
        ip={selectedIP}
        customerOptions={customerOptions ?? []}
        submitting={updateIPCustomer.isPending || updateIPNotes.isPending}
        onSubmit={handleEditSubmit}
      />

      <IPDetailModal
        open={detailModal.isOpen}
        onClose={() => detailModal.close()}
        detailAddress={detailAddress}
        loading={loadingDetail}
        detail={ipDetail}
      />

      <IPBatchBanModal
        open={batchBan.isOpen}
        onClose={() => batchBan.close()}
        submitting={batchBanIP.isPending}
        onSubmit={handleBatchBanSubmit}
      />

      <IPStatsModal
        open={stats.isOpen}
        onClose={() => stats.close()}
        stats={ipStats}
        scopeLabel={
          table.search || table.filters.room_id
            ? t('ip.stats.scopeLabel', {
                scope: `${table.filters.room_id ? t('ip.stats.scopeRoom') : ''}${table.search ? t('ip.stats.scopeSearch', { value: table.search }) : t('ip.stats.scopeAll')}`
              })
            : undefined
        }
      />

      <IPBatchEditModal
        open={batchEdit.isOpen}
        mode={batchEditMode}
        count={batch.count}
        customerOptions={customerOptions ?? []}
        submitting={batchUpdateIPCustomer.isPending || batchUpdateIPNotes.isPending}
        onClose={() => batchEdit.close()}
        onSubmit={handleBatchEditSubmit}
      />
    </>
  );
}

export default IP;
