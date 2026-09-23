import { useConfirm } from '@/utils/confirm';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import { useState, useCallback, useEffect, useRef } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import {
  Button,
  Space,
  Tag,
  Select,
  Input,
  Form,
  Tooltip,
  Progress,
  Modal,
  Radio,
  Typography
} from 'antd';
import {
  DeleteOutlined,
  CopyOutlined,
  ExportOutlined,
  UserOutlined,
  SearchOutlined,
  CloudSyncOutlined,
  ApartmentOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import DataTable from '@/components/DataTable';
import FilterBar from '@/components/FilterBar';
import { isPrivateNetwork } from '@/utils/ip';
import { useQueryClient } from '@tanstack/react-query';
import {
  useNetworkList,
  useDeleteNetwork,
  useUpdateNetworkCustomer,
  useScanNetwork,
  useNetworkRoutes,
  useTriggerFullScan,
  useFullScanStatus,
  SCAN_TERMINAL_PHASES
} from '@/services/network';
import { queryKeys } from '@/services/query-keys';
import { useRoomOptions } from '@/services/room';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { getRouteNoteMeta, getRouteNoteOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useCopyInfo } from '@/utils/clipboard';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import { useGlobalEventListener } from '@/hooks/useGlobalEvents';
import type { GlobalEvent } from '@/hooks/useGlobalEvents';

type ScanPhaseKey =
  | 'networkList.scan.phase.preparing'
  | 'networkList.scan.phase.collecting'
  | 'networkList.scan.phase.portInfo'
  | 'networkList.scan.phase.deviceInfo'
  | 'networkList.scan.phase.routeSync'
  | 'networkList.scan.phase.macIndex'
  | 'networkList.scan.phase.arpSync'
  | 'networkList.scan.phase.locationVerify'
  | 'networkList.scan.phase.nexthopInfer'
  | 'networkList.scan.phase.degrade'
  | 'networkList.scan.phase.ipReconcile'
  | 'networkList.scan.phase.supplementDetect'
  | 'networkList.scan.phase.done';

const PHASE_WEIGHT: Record<string, number> = {
  准备中: 0,
  collecting: 0,
  phase0_port_info: 0.6,
  phase0b_device_info: 0.65,
  phase1_route_sync: 0.7,
  phase2_mac_index: 0.75,
  phase3_arp_sync: 0.8,
  phase3b_location_verify: 0.825,
  phase4_nexthop: 0.85,
  phase5_degrade: 0.88,
  phase6_ip_reconcile: 0.92,
  phase7_supplement_detect: 0.95,
  完成: 1.0
};

const PHASE_LABEL_KEY: Record<string, ScanPhaseKey> = {
  准备中: 'networkList.scan.phase.preparing',
  collecting: 'networkList.scan.phase.collecting',
  phase0_port_info: 'networkList.scan.phase.portInfo',
  phase0b_device_info: 'networkList.scan.phase.deviceInfo',
  phase1_route_sync: 'networkList.scan.phase.routeSync',
  phase2_mac_index: 'networkList.scan.phase.macIndex',
  phase3_arp_sync: 'networkList.scan.phase.arpSync',
  phase3b_location_verify: 'networkList.scan.phase.locationVerify',
  phase4_nexthop: 'networkList.scan.phase.nexthopInfer',
  phase5_degrade: 'networkList.scan.phase.degrade',
  phase6_ip_reconcile: 'networkList.scan.phase.ipReconcile',
  phase7_supplement_detect: 'networkList.scan.phase.supplementDetect',
  完成: 'networkList.scan.phase.done'
};

function parseScanProgress(
  progress: {
    phase?: string;
    total?: number;
    completed?: number;
    failed?: number;
  },
  t: TFunction<'network'>
) {
  const phaseStr = progress.phase || '';
  const subMatch = phaseStr.match(/^(phase7_supplement_detect):(\d+)\/(\d+)$/);
  const basePhase = subMatch ? subMatch[1] : phaseStr;

  let pct: number;
  if (phaseStr === '完成') {
    pct = 100;
  } else if (subMatch) {
    const probed = Number(subMatch[2]);
    const total = Number(subMatch[3]);
    pct = Math.round(95 + (probed / Math.max(total, 1)) * 4);
  } else {
    const basePct = (PHASE_WEIGHT[basePhase] ?? 0) * 100;
    const total = Math.max(progress.total ?? 0, 1);
    const collectPct = (((progress.completed ?? 0) + (progress.failed ?? 0)) / total) * 35;
    pct = Math.round(Math.max(basePct, collectPct));
  }

  const phaseKey = PHASE_LABEL_KEY[basePhase];
  const label = phaseKey ? t(phaseKey) : basePhase;
  const subText = subMatch
    ? `${subMatch[2]}/${subMatch[3]}`
    : (progress.total ?? 0) > 0
      ? `${progress.completed ?? 0}/${progress.total}`
      : '';

  return { pct, label, subText, failed: progress.failed ?? 0 };
}
import { exportCSV } from '@/utils/csv';
import type { IPNetwork } from '@/types/models';
import { formatDateTime } from '@/utils/format';

const DEFAULT_ROUTE = '0.0.0.0/0';

const { Text } = Typography;

function isDefaultRoute(ipNetwork: string): boolean {
  return ipNetwork === DEFAULT_ROUTE;
}

function Network() {
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const { t: td } = useTranslation('device');
  const confirm = useConfirm();
  const table = useTable();
  const msg = useMessage();
  const copyInfo = useCopyInfo();
  const navigate = useNavigate();

  const assign = useDisclosure();
  const [assignRecord, setAssignRecord] = useState<IPNetwork | null>(null);
  const routes = useDisclosure();
  const [assignForm] = Form.useForm();

  const [scanningRoomId, setScanningRoomId] = useState<number | null>(null);
  const triggerFullScan = useTriggerFullScan();
  const queryClient = useQueryClient();
  const { data: scanStatus } = useFullScanStatus(scanningRoomId ?? 0, scanningRoomId !== null);

  const { data, isLoading, refetch } = useNetworkList({
    page: table.page,
    per_page: table.perPage,
    search: table.search || undefined,
    room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined,
    route_type:
      table.filters.route_type !== undefined ? String(table.filters.route_type) : undefined,
    customer_id: table.filters.customer_id ? Number(table.filters.customer_id) : undefined
  });

  const { data: routesData, isLoading: routesLoading } = useNetworkRoutes(
    routes.isOpen
      ? { room_id: table.filters.room_id ? Number(table.filters.room_id) : undefined }
      : undefined
  );

  const lastCompletedPhaseRef = useRef<string | null>(null);

  useEffect(() => {
    if (!scanStatus) return;
    const phaseStr = scanStatus.phase || '';
    const subMatch = phaseStr.match(/^phase7_supplement_detect:(\d+)\/(\d+)$/);
    const phase7Complete = subMatch && Number(subMatch[1]) >= Number(subMatch[2]);
    const isComplete = phaseStr === '完成' || phase7Complete;
    const isFailed = phaseStr === 'failed';

    if (isComplete || isFailed) {
      if (lastCompletedPhaseRef.current === scanStatus.phase) return;
      lastCompletedPhaseRef.current = scanStatus.phase;

      setScanningRoomId(null);
      if (isComplete) {
        refetch();
      } else {
        refetch();
      }
    } else {
      lastCompletedPhaseRef.current = null;
    }
  }, [scanStatus, refetch]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refetch();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [refetch]);

  const deleteNetwork = useDeleteNetwork();
  const updateNetworkCustomer = useUpdateNetworkCustomer();
  const scanNetwork = useScanNetwork();
  const { data: roomOptions } = useRoomOptions();
  const { data: allocatableCustomerOptions } = useAllocatableCustomerOptions();


  const handleViewDetail = (record: IPNetwork) => {
    const params = new URLSearchParams();
    if (record.room_id) params.set('room_id', String(record.room_id));
    if (record.switch_id) params.set('switch_id', String(record.switch_id));
    const qs = params.toString();
    navigate(`/network/${encodeURIComponent(record.ip_network)}${qs ? `?${qs}` : ''}`);
  };

  const confirmAction = useConfirmAction();
  const handleDelete = (record: IPNetwork) => {
    if (
      !record.room_id ||
      !record.switch_id ||
      record.route_type === null ||
      record.route_type === undefined ||
      !record.nexthop
    ) {
      msg.warning(t('networkList.message.missingParams'));
      return;
    }
    confirmAction({
      title: tc('confirm.deleteTitle'),
      content: t('networkList.confirm.deleteContent', { network: record.ip_network }),
      okType: 'danger',
      successMessage: tc('message.deleteSuccess'),
      onConfirm: () =>
        deleteNetwork.mutateAsync({
          ipNetwork: record.ip_network,
          networkId: record.id
        }),
      afterConfirm: refetch
    });
  };

  const handleAssignOpen = (record: IPNetwork) => {
    setAssignRecord(record);
    assignForm.setFieldsValue({ customer_id: record.customer_id ?? undefined });
    assign.open();
  };

  const handleAssignSubmit = async () => {
    if (!assignRecord) return;
    try {
      const values = await assignForm.validateFields();
      await updateNetworkCustomer.mutateAsync({
        ipNetwork: assignRecord.ip_network,
        data: {
          network_id: assignRecord.id,
          customer_id: values.customer_id ?? null,
          room_id: assignRecord.room_id ?? undefined,
          force: values.force === 'all'
        }
      });
      msg.success(t('networkList.message.customerUpdated'));
      assign.close();
      refetch();
    } catch (err) {
      if (err instanceof Error) msg.error(err.message);
    }
  };

  const handleCopy = (record: IPNetwork) => {
    const lines = [
      `${t('networkList.field.network')}: ${record.ip_network}`,
      `${t('networkList.field.switch')}: ${record.switch_name ?? '-'}`,
      `${t('networkList.field.port')}: ${record.port ?? '-'}`,
      `${t('networkList.field.room')}: ${record.room_name ?? '-'}`,
      `${t('networkList.field.customer')}: ${record.customer_name ?? '-'}`,
      `${t('networkList.field.nexthop')}: ${record.nexthop ?? '-'}`,
      `${tc('field.type')}: ${record.route_type ?? '-'}`,
      `${t('networkList.field.notes')}: ${record.notes ?? '-'}`
    ];
    copyInfo(lines.join('\n'));
  };

  const handleExport = useCallback(() => {
    const items = data?.items ?? [];
    if (!items.length) {
      msg.warning(t('ip.message.noDataToExport'));
      return;
    }
    const headers = [
      t('networkList.field.network'),
      t('networkList.field.switch'),
      t('networkList.field.port'),
      t('networkList.field.room'),
      t('networkList.field.customer'),
      t('networkList.field.nexthop'),
      t('networkList.field.notes'),
      tc('field.updatedAt')
    ];
    const rows = items.map((r) => [
      r.ip_network,
      r.switch_name ?? '',
      r.port ?? '',
      r.room_name ?? '',
      r.customer_name ?? '',
      r.nexthop ?? '',
      r.notes ?? '',
      r.updated_at ?? ''
    ]);
    exportCSV(headers, rows, { filename: 'networks' });
  }, [data, t, tc]);

  const handleScanNetwork = (record: IPNetwork) => {
    if (isDefaultRoute(record.ip_network)) {
      msg.warning(t('networkList.tooltip.defaultRouteNotScannable', { route: DEFAULT_ROUTE }));
      return;
    }
    if (isPrivateNetwork(record.ip_network)) {
      msg.warning(t('ip.message.privateNetworkUnreachable'));
      return;
    }
    if (!record.room_id) {
      msg.warning(t('networkList.message.missingRoomForScan'));
      return;
    }
    confirm({
      title: t('networkList.confirm.scanTitle'),
      content: t('networkList.confirm.scanContent', { network: record.ip_network }),
      onOk: async () => {
        try {
          await scanNetwork.mutateAsync({ ipNetwork: record.ip_network, roomId: record.room_id! });
          msg.info(t('networkList.message.scanSubmitted', { network: record.ip_network }));
          setTimeout(() => refetch(), 30000);
        } catch {
          msg.error(t('ip.message.scanNetworkFailed'));
        }
      }
    });
  };

  const handleFullScan = () => {
    if (!table.filters.room_id) {
      msg.warning(t('networkList.message.fullScanRoomRequired'));
      return;
    }
    confirm({
      title: t('networkList.action.fullScan'),
      content: t('networkList.confirm.fullScanContent'),
      onOk: async () => {
        try {
          queryClient.removeQueries({
            queryKey: [...queryKeys.networks.all, 'scan-status', Number(table.filters.room_id)]
          });
          lastCompletedPhaseRef.current = null;
          await triggerFullScan.mutateAsync(Number(table.filters.room_id));
          setScanningRoomId(Number(table.filters.room_id));
          msg.info(t('networkList.message.fullScanSubmitted'));
        } catch {
          msg.error(t('ip.message.scanNetworkFailed'));
        }
      }
    });
  };

  useGlobalEventListener(
    useCallback(
      (event: GlobalEvent) => {
        if (event.event_type === 'room_scan_complete') {
          const payload = event.payload as Record<string, unknown>;
          const roomId = payload.room_id as number | undefined;
          if (roomId) {
            setScanningRoomId(null);
            refetch();
          }
          return;
        }

        if (event.event_type === 'ip_scan_complete') {
          refetch();
          return;
        }

        if (event.event_type === 'scan_failed') {
          setScanningRoomId(null);
          refetch();
          return;
        }

        if (event.event_type !== 'scan_progress') return;
        const progress = event.payload as Record<string, unknown>;
        const roomId = progress.room_id as number | undefined;
        if (!roomId) return;

        const phase = progress.phase as string;

        if (phase === 'failed') {
          setScanningRoomId(null);
          refetch();
          return;
        }

        if (phase === '完成') {
          setScanningRoomId(null);
          refetch();
          return;
        }

      },
      [refetch]
    )
  );


  const routeColumns = [
    { title: t('networkList.field.destination'), dataIndex: 'destination', key: 'destination' },
    { title: t('networkList.field.nexthop'), dataIndex: 'nexthop', key: 'nexthop' },
    { title: t('networkList.field.outInterface'), dataIndex: 'interface', key: 'interface' },
    {
      title: tc('field.type'),
      dataIndex: 'route_type',
      key: 'route_type',
      render: (v: number | null) => {
        if (v === null || v === undefined) return '-';
        const map = getRouteNoteMeta(v, td);
        return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
      }
    },
    {
      title: t('networkList.field.notes'),
      dataIndex: 'notes',
      key: 'notes',
      render: (v: string | null) => v || '-'
    }
  ];

  const networkColumns = [
    {
      title: t('networkList.field.network'),
      dataIndex: 'ip_network',
      key: 'ip_network',
      render: (v: string, r: IPNetwork) => (
        <Button type="link" size="small" onClick={() => handleViewDetail(r)}>
          {v}
        </Button>
      )
    },
    {
      title: t('networkList.field.switch'),
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.port'),
      dataIndex: 'port',
      key: 'port',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.room'),
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: t('networkList.field.customer'),
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: tc('field.type'),
      dataIndex: 'route_type',
      key: 'route_type',
      render: (v: number | string | null) => {
        if (v === null || v === undefined) return '-';
        const num = Number(v);
        const map = getRouteNoteMeta(num, td);
        return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
      }
    },
    {
      title: t('networkList.field.nexthop'),
      dataIndex: 'nexthop',
      key: 'nexthop',
      render: (v: string) => v || '-'
    },
    {
      title: tc('field.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string | null) => (v ? formatDateTime(v) : '-')
    },
    {
      title: t('networkList.field.actions'),
      key: 'action',
      render: (_: unknown, r: IPNetwork) => renderActions(r)
    }
  ];

  const renderActions = (r: IPNetwork) => {
    const scanDisabled = isDefaultRoute(r.ip_network) || isPrivateNetwork(r.ip_network);
    const scanTooltip = isDefaultRoute(r.ip_network)
      ? t('networkList.tooltip.defaultRouteNotScannable', { route: DEFAULT_ROUTE })
      : isPrivateNetwork(r.ip_network)
        ? t('ip.message.privateNetworkUnreachable')
        : '';
    return (
      <Space size="small" wrap>
        <Button
          type="link"
          size="small"
          icon={<UserOutlined />}
          onClick={() => handleAssignOpen(r)}
        >
          {td('switch.port.assign')}
        </Button>
        {scanDisabled ? (
          <Tooltip title={scanTooltip}>
            <Button type="link" size="small" icon={<SearchOutlined />} disabled>
              {t('ip.action.scan')}
            </Button>
          </Tooltip>
        ) : (
          <Button
            type="link"
            size="small"
            icon={<SearchOutlined />}
            onClick={() => handleScanNetwork(r)}
            loading={scanNetwork.isPending}
          >
            {t('ip.action.scan')}
          </Button>
        )}
        <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(r)} />
        <Button
          type="link"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDelete(r)}
        >
          {tc('action.delete')}
        </Button>
      </Space>
    );
  };

  const renderNetworkCard = (r: IPNetwork) => (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => handleViewDetail(r)}>
          <Text strong>{r.ip_network}</Text>
        </Button>
        {getRouteNoteMeta(r.route_type, td) ? (
          <Tag color={getRouteNoteMeta(r.route_type, td)?.color}>
            {getRouteNoteMeta(r.route_type, td)?.label}
          </Tag>
        ) : null}
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {[r.switch_name, r.port && `${t('networkList.field.port')} ${r.port}`]
          .filter(Boolean)
          .join(' · ') || '-'}
      </Text>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {[r.room_name, r.customer_name, r.nexthop && `${t('networkList.field.nexthop')} ${r.nexthop}`]
          .filter(Boolean)
          .join(' · ') || '-'}
      </Text>
      {renderActions(r)}
    </Space>
  );

  const scanProgressIndicator =
    scanStatus && !SCAN_TERMINAL_PHASES.has(scanStatus.phase) ? (
      <Space
        size={4}
        style={{
          background: '#f6ffed',
          padding: '4px 12px',
          borderRadius: 6,
          border: '1px solid #b7eb8f'
        }}
      >
        {(() => {
          const { pct, label, subText, failed } = parseScanProgress(scanStatus, t);
          return (
            <>
              <Progress type="circle" size={28} percent={pct} />
              <span style={{ fontSize: 12, color: '#52c41a' }}>
                {label} {subText}
                {failed ? (
                  <span style={{ color: '#ff4d4f' }}>
                    {' '}
                    ({t('networkList.scan.failed', { count: failed })})
                  </span>
                ) : null}
              </span>
            </>
          );
        })()}
      </Space>
    ) : null;

  return (
    <>
      {/* 网段列表 */}
      <DataTable<IPNetwork>
        columns={networkColumns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder={t('networkList.filter.searchPlaceholder')}
        searchValue={table.search}
        onSearch={table.setSearch}
        onRefresh={refetch}
        total={data?.total ?? 0}
        page={table.page}
        perPage={table.perPage}
        onPageChange={(p, ps) => {
          table.setPage(p);
          if (ps !== table.perPage) table.setPerPage(ps);
        }}
        mobileCardMode
        cardRender={renderNetworkCard}
        toolbar={
          <FilterBar
            filters={[
              {
                key: 'room_id',
                label: t('networkList.field.room'),
                type: 'select',
                options: roomOptions ?? [],
                width: 140
              },
              {
                key: 'route_type',
                label: tc('field.type'),
                type: 'select',
                width: 140,
                options: getRouteNoteOptions(td)
              },
              {
                key: 'customer_id',
                label: t('networkList.field.customer'),
                type: 'select',
                options: allocatableCustomerOptions ?? [],
                width: 140
              }
            ]}
            table={table}
            extra={
              <>
                <Button icon={<ApartmentOutlined />} onClick={() => routes.open()}>
                  {t('networkList.action.routeList')}
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  onClick={handleFullScan}
                  loading={triggerFullScan.isPending}
                >
                  {t('networkList.action.fullScan')}
                </Button>
                <Button icon={<ExportOutlined />} onClick={handleExport}>
                  {t('ip.action.exportCsv')}
                </Button>
                {scanProgressIndicator}
              </>
            }
          />
        }
      />

      {/* 分配客户弹窗 */}
      <Modal
        title={t('networkList.action.assignCustomer')}
        open={assign.isOpen}
        onOk={handleAssignSubmit}
        onCancel={() => assign.close()}
        destroyOnHidden
      >
        <Form form={assignForm} layout="vertical" initialValues={{ force: 'null_only' }}>
          <Form.Item label={t('networkList.field.network')}>
            <Input value={assignRecord?.ip_network} disabled />
          </Form.Item>
          <Form.Item name="customer_id" label={t('networkList.field.customer')}>
            <Select
              placeholder={t('ip.edit.selectCustomer')}
              options={allocatableCustomerOptions}
              allowClear
            />
          </Form.Item>
          <Form.Item
            name="force"
            label={t('networkList.form.ipSyncPolicy')}
            tooltip={t('networkList.form.ipSyncPolicyTooltip')}
          >
            <Radio.Group>
              <Radio value="null_only">{t('networkList.form.policyNullOnly')}</Radio>
              <Radio value="all">{t('networkList.form.policyAll')}</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* 路由列表弹窗 */}
      <Modal
        title={t('networkList.action.routeList')}
        open={routes.isOpen}
        onCancel={() => routes.close()}
        footer={null}
        width={900}
        destroyOnHidden
      >
        <DataTable
          columns={routeColumns}
          dataSource={routesData ?? []}
          rowKey="id"
          loading={routesLoading}
          size="small"
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (t) => tc('pagination.total', { count: t })
          }}
          searchable={false}
          showCard={false}
        />
      </Modal>
    </>
  );
}

export default Network;
