import { confirm } from '@/utils/confirm';
import { useConfirmAction } from '@/hooks/useConfirmAction';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Button,
  Space,
  Tag,
  Select,
  Input,
  Form,
  Tooltip,
  Table,
  Progress,
  Modal,
  Radio
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
  useFullScanStatus
} from '@/services/network';
import { queryKeys } from '@/services/query-keys';
import { useRoomOptions } from '@/services/room';
import { useCustomerOptions, useAllocatableCustomerOptions } from '@/services/customer';
import { ROUTE_NOTES_MAP } from '@/types/enums';
import { useCopyInfo } from '@/utils/clipboard';
import { useTable } from '@/hooks/useTable';
import { useMessage } from '@/hooks/useMessage';
import { useGlobalEventListener } from '@/hooks/useGlobalEvents';
import type { GlobalEvent } from '@/hooks/useGlobalEvents';


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


const PHASE_LABEL: Record<string, string> = {
  准备中: '准备中',
  collecting: '采集数据',
  phase0_port_info: '端口采集',
  phase0b_device_info: '设备信息',
  phase1_route_sync: '路由同步',
  phase2_mac_index: 'MAC索引',
  phase3_arp_sync: 'ARP同步',
  phase3b_location_verify: '定位校验',
  phase4_nexthop: '路由推断',
  phase5_degrade: '降级处理',
  phase6_ip_reconcile: 'IP对账',
  phase7_supplement_detect: '补充探测',
  完成: '完成'
};


function parseScanProgress(progress: {
  phase?: string;
  total?: number;
  completed?: number;
  failed?: number;
}) {
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

  const label = PHASE_LABEL[basePhase] || basePhase;
  const subText = subMatch
    ? `${subMatch[2]}/${subMatch[3]}`
    : (progress.total ?? 0) > 0
      ? `${progress.completed ?? 0}/${progress.total}`
      : '';

  return { pct, label, subText, failed: progress.failed ?? 0 };
}
import { exportCSV } from '@/utils/csv';
import type { IPNetwork } from '@/types/models';


const DEFAULT_ROUTE = '0.0.0.0/0';


function isDefaultRoute(ipNetwork: string): boolean {
  return ipNetwork === DEFAULT_ROUTE;
}


function Network() {
  const table = useTable();
  const msg = useMessage();
  const copyInfo = useCopyInfo();
  const navigate = useNavigate();

  
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignRecord, setAssignRecord] = useState<IPNetwork | null>(null);
  const [routesOpen, setRoutesOpen] = useState(false);
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
    routesOpen
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
  const { data: customerOptions } = useCustomerOptions();
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
      msg.warning('缺少必要参数（room_id/switch_id/route_type/nexthop），无法删除');
      return;
    }
    confirmAction({
      title: '确认删除',
      content: `确定要删除网段 ${record.ip_network} 吗？`,
      okType: 'danger',
      successMessage: '删除成功',
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
    setAssignOpen(true);
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
      msg.success('客户分配成功');
      setAssignOpen(false);
      refetch();
    } catch (err) {
      if (err instanceof Error) msg.error(err.message);
    }
  };

  
  const handleCopy = (record: IPNetwork) => {
    const text = `网段: ${record.ip_network}\n交换机: ${record.switch_name ?? '-'}\n端口: ${record.port ?? '-'}\n机房: ${record.room_name ?? '-'}\n客户: ${record.customer_name ?? '-'}\n下一跳: ${record.nexthop ?? '-'}\n类型: ${record.route_type ?? '-'}\n备注: ${record.notes ?? '-'}`;
    copyInfo(text);
  };

  
  const handleExport = useCallback(() => {
    const items = data?.items ?? [];
    if (!items.length) {
      msg.warning('无数据可导出');
      return;
    }
    const headers = ['网段', '交换机', '端口', '机房', '客户', '下一跳', '备注', '更新时间'];
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
  }, [data]);

  
  const handleScanNetwork = (record: IPNetwork) => {
    if (isDefaultRoute(record.ip_network)) {
      msg.warning('默认路由网段（0.0.0.0/0）不可扫描');
      return;
    }
    if (isPrivateNetwork(record.ip_network)) {
      msg.warning('私网地址跨网不可达，状态由ARP表判断');
      return;
    }
    if (!record.room_id) {
      msg.warning('该网段缺少机房信息，无法扫描');
      return;
    }
    confirm({
      title: '确认扫描',
      content: `确定要扫描网段 ${record.ip_network} 吗？扫描将在后台执行，完成后自动刷新。`,
      onOk: async () => {
        try {
          await scanNetwork.mutateAsync({ ipNetwork: record.ip_network, roomId: record.room_id! });
          msg.info(`网段 ${record.ip_network} 扫描已提交，完成后将通过消息通知您`);
          
          setTimeout(() => refetch(), 30000);
        } catch {
          msg.error('扫描启动失败');
        }
      }
    });
  };

  
  const handleFullScan = () => {
    if (!table.filters.room_id) {
      msg.warning('请先选择机房，全量扫描需限定机房范围');
      return;
    }
    confirm({
      title: '全量扫描',
      content: `将对当前机房内所有交换机执行全量扫描（端口采集+路由同步+MAC索引+ARP同步+IP对账+补充探测），可能需要较长时间。扫描在后台执行，完成后自动刷新。`,
      onOk: async () => {
        try {
          
          queryClient.removeQueries({
            queryKey: [...queryKeys.networks.all, 'scan-status', Number(table.filters.room_id)]
          });
          lastCompletedPhaseRef.current = null;
          await triggerFullScan.mutateAsync(Number(table.filters.room_id));
          setScanningRoomId(Number(table.filters.room_id));
          msg.info('全量扫描已提交，完成后将通过消息通知您');
        } catch {
          msg.error('扫描启动失败');
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
    { title: '目标网段', dataIndex: 'destination', key: 'destination' },
    { title: '下一跳', dataIndex: 'nexthop', key: 'nexthop' },
    { title: '出接口', dataIndex: 'interface', key: 'interface' },
    {
      title: '路由类型',
      dataIndex: 'route_type',
      key: 'route_type',
      render: (v: number | null) => {
        if (v === null || v === undefined) return '-';
        const map = ROUTE_NOTES_MAP[v];
        return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
      }
    },
    { title: '备注', dataIndex: 'notes', key: 'notes', render: (v: string | null) => v || '-' }
  ];

  
  const networkColumns = [
    {
      title: '网段',
      dataIndex: 'ip_network',
      key: 'ip_network',
      render: (v: string, r: IPNetwork) => (
        <Button type="link" size="small" onClick={() => handleViewDetail(r)}>
          {v}
        </Button>
      )
    },
    {
      title: '交换机',
      dataIndex: 'switch_name',
      key: 'switch_name',
      render: (v: string | null) => v || '-'
    },
    { title: '端口', dataIndex: 'port', key: 'port', render: (v: string | null) => v || '-' },
    {
      title: '机房',
      dataIndex: 'room_name',
      key: 'room_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null) => v || '-'
    },
    {
      title: '类型',
      dataIndex: 'route_type',
      key: 'route_type',
      render: (v: number | string | null) => {
        if (v === null || v === undefined) return '-';
        const num = Number(v);
        const map = ROUTE_NOTES_MAP[num];
        return map ? <Tag color={map.color}>{map.label}</Tag> : String(v);
      }
    },
    { title: '下一跳', dataIndex: 'nexthop', key: 'nexthop', render: (v: string) => v || '-' },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-')
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: IPNetwork) => {
        const scanDisabled = isDefaultRoute(r.ip_network) || isPrivateNetwork(r.ip_network);
        const scanTooltip = isDefaultRoute(r.ip_network)
          ? '默认路由网段不可扫描'
          : isPrivateNetwork(r.ip_network)
            ? '私网地址跨网不可达，状态由ARP表判断'
            : '';
        return (
          <Space>
            <Button
              type="link"
              size="small"
              icon={<UserOutlined />}
              onClick={() => handleAssignOpen(r)}
            >
              分配
            </Button>
            {scanDisabled ? (
              <Tooltip title={scanTooltip}>
                <Button type="link" size="small" icon={<SearchOutlined />} disabled>
                  扫描
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
                扫描
              </Button>
            )}
            <Button
              type="link"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(r)}
            />
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(r)}
            >
              删除
            </Button>
          </Space>
        );
      }
    }
  ];

  
  const scanProgressIndicator =
    scanStatus &&
    scanStatus.phase !== 'unknown' &&
    scanStatus.phase !== '完成' &&
    scanStatus.phase !== 'failed' ? (
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
          const { pct, label, subText, failed } = parseScanProgress(scanStatus);
          return (
            <>
              <Progress type="circle" size={28} percent={pct} />
              <span style={{ fontSize: 12, color: '#52c41a' }}>
                {label} {subText}
                {failed ? <span style={{ color: '#ff4d4f' }}> (失败{failed})</span> : null}
              </span>
            </>
          );
        })()}
      </Space>
    ) : null;

  return (
    <>
      {}
      <DataTable<IPNetwork>
        columns={networkColumns}
        dataSource={data?.items ?? []}
        rowKey="id"
        loading={isLoading}
        searchable
        searchPlaceholder="搜索网段/交换机/客户..."
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
        toolbar={
          <FilterBar
            filters={[
              {
                key: 'room_id',
                label: '机房',
                type: 'select',
                options: roomOptions ?? [],
                width: 140
              },
              {
                key: 'route_type',
                label: '类型',
                type: 'select',
                width: 140,
                options: Object.entries(ROUTE_NOTES_MAP).map(([k, v]) => ({
                  label: v.label,
                  value: Number(k)
                }))
              },
              {
                key: 'customer_id',
                label: '客户',
                type: 'select',
                options: customerOptions ?? [],
                width: 140
              }
            ]}
            table={table}
            extra={
              <>
                <Button icon={<ApartmentOutlined />} onClick={() => setRoutesOpen(true)}>
                  路由列表
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  onClick={handleFullScan}
                  loading={triggerFullScan.isPending}
                >
                  全量扫描
                </Button>
                <Button icon={<ExportOutlined />} onClick={handleExport}>
                  导出CSV
                </Button>
                {scanProgressIndicator}
              </>
            }
          />
        }
      />

      {}
      <Modal
        title="分配客户"
        open={assignOpen}
        onOk={handleAssignSubmit}
        onCancel={() => setAssignOpen(false)}
        destroyOnHidden
      >
        <Form form={assignForm} layout="vertical" initialValues={{ force: 'null_only' }}>
          <Form.Item label="网段">
            <Input value={assignRecord?.ip_network} disabled />
          </Form.Item>
          <Form.Item name="customer_id" label="客户">
            <Select placeholder="选择客户" options={allocatableCustomerOptions} allowClear />
          </Form.Item>
          <Form.Item
            name="force"
            label="IP同步策略"
            tooltip="选择覆盖所有IP可一步完成换客户，会清空网段内所有IP的原客户归属"
          >
            <Radio.Group>
              <Radio value="null_only">仅填充未分配IP</Radio>
              <Radio value="all">覆盖所有IP</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {}
      <Modal
        title="路由列表"
        open={routesOpen}
        onCancel={() => setRoutesOpen(false)}
        footer={null}
        width={900}
        destroyOnHidden
      >
        <Table
          columns={routeColumns}
          dataSource={routesData ?? []}
          rowKey="id"
          loading={routesLoading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
        />
      </Modal>
    </>
  );
}

export default Network;
