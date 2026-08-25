/**
 * 机柜详情页
 * - 机柜基本信息（完整字段）
 * - U 位可视化（展示实际设备占用）
 * - 跳转查看该机柜下的设备
 */

import { useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Spin, Button, Tag, Result } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useCabinetSuspenseDetail, useCabinetWithDevices } from '@/services/cabinet';
import { useUpdateDevice } from '@/services/device';
import { useVendorBrands } from '@/services/monitor';
import { queryKeys } from '@/services/query-keys';
import UPositionSelector from '@/components/UPositionSelector';
import type {
  OccupiedPosition,
  RackDeviceType,
  DeviceNode,
  NodeStatus
} from '@/components/UPositionSelector/UPositionSelector';
import { formatDateTime } from '@/utils/format';
import { useMessage } from '@/hooks/useMessage';
import { CABINET_STATUS_MAP } from '@/types/enums';
import { DeviceStatusCode } from '@/types/status-codes.generated';
import type { Cabinet, Device } from '@/types/models';

function renderStatus(v: number) {
  const s = CABINET_STATUS_MAP[v as keyof typeof CABINET_STATUS_MAP];
  return s ? <Tag color={s.color}>{s.label}</Tag> : <Tag>{v}</Tag>;
}

function CabinetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const cabinetId = Number(id);

  if (Number.isNaN(cabinetId)) {
    return (
      <Result
        status="404"
        title="参数无效"
        subTitle="机柜 ID 无效"
        extra={<Button onClick={() => navigate(-1)}>返回</Button>}
      />
    );
  }

  return <CabinetDetailContent cabinetId={cabinetId} />;
}

function CabinetDetailContent({ cabinetId }: { cabinetId: number }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (cabinetId > 0) {
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.withDevices(cabinetId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.detail(cabinetId) });
    }
  }, [cabinetId, queryClient]);

  const { data: cabinet } = useCabinetSuspenseDetail(cabinetId);
  const { data: cabinetWithDevices } = useCabinetWithDevices(cabinetId);
  const updateDevice = useUpdateDevice();
  const { data: vendorBrands } = useVendorBrands();
  const message = useMessage();

  const vendorLabelMap = new Map<string, string>();
  for (const v of vendorBrands?.items ?? []) {
    if (!vendorLabelMap.has(v.enterprise_no)) vendorLabelMap.set(v.enterprise_no, v.label);
  }

  const handlePositionChange = useCallback(
    (deviceId: number, newUPos: number) => {
      updateDevice.mutate(
        { id: deviceId, u_position: newUPos } as Parameters<typeof updateDevice.mutate>[0],
        {
          onSuccess: () => {
            message.success('U位更新成功');
            queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.detail(cabinetId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.cabinets.withDevices(cabinetId) });
          },
          onError: () => message.error('U位更新失败')
        }
      );
    },
    [updateDevice, cabinetId, queryClient]
  );

  if (!cabinet) {
    return <div>机柜不存在</div>;
  }

  function mapDeviceType(d: Device): RackDeviceType {
    if (d.is_chassis) return 'multinode';
    const sub = d.device_subtype;
    if (sub === 'switch' || sub === 'router' || sub === 'firewall') return 'switch';
    if (sub === 'pdu') return 'pdu';
    if (sub === 'ups') return 'kvm';
    const main = d.device_type;
    if (main === 'network') return 'switch';
    return 'server';
  }

  function mapNodeStatus(status: number): NodeStatus {
    if (status === DeviceStatusCode.ONLINE) return 'active'; // 在线
    if (status === DeviceStatusCode.OFFLINE) return 'inactive'; // 离线
    if (status === DeviceStatusCode.MAINTENANCE) return 'fault'; // 故障/维护
    return 'inactive';
  }

  const allDevices = ((cabinetWithDevices as { devices?: Device[] })?.devices ?? []) as Device[];

  const topDevices = allDevices.filter((d) => !d.parent_device_id);

  const occupiedPositions: OccupiedPosition[] = topDevices.map((d) => {
    let nodes: DeviceNode[] | undefined;
    if (d.is_chassis) {
      const childDevices = allDevices.filter((c) => c.parent_device_id === d.id);
      if (childDevices.length > 0) {
        nodes = childDevices.map((child) => ({
          id: String(child.id),
          label: child.device_name,
          status: mapNodeStatus(child.status),
          ip: child.management_ip || child.ip_address || undefined,
          ipmiAddress: (child as Device & { ipmi_address?: string }).ipmi_address || undefined,
          row: child.node_row ?? undefined,
          col: child.node_col ?? undefined
        }));
      }
    }

    return {
      uPosition: d.u_position ?? 0,
      uSize: d.height_u || 1,
      deviceName: d.device_name,
      deviceId: d.id,
      deviceType: mapDeviceType(d),
      power: d.power ?? undefined,
      ip: d.management_ip || d.ip_address || undefined,
      ipmiAddress: (d as Device & { ipmi_address?: string }).ipmi_address || undefined,
      sn: d.serial_number || undefined,
      vendor: (d.brand && vendorLabelMap.get(d.brand)) || undefined,
      model: d.device_model || undefined,
      nodes,
      nodeRows: d.is_chassis ? (d.node_rows ?? undefined) : undefined,
      nodeCols: d.is_chassis ? (d.node_cols ?? undefined) : undefined
    };
  });

  const c = cabinet as Cabinet;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/cabinets')}>
          返回列表
        </Button>
        <Button type="primary" onClick={() => navigate(`/devices?cabinetId=${cabinetId}`)}>
          查看设备
        </Button>
      </div>

      <Card title={`机柜详情 - ${c.cabinet_number}`}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="机柜编号">{c.cabinet_number}</Descriptions.Item>
          <Descriptions.Item label="状态">{renderStatus(c.status)}</Descriptions.Item>
          <Descriptions.Item label="所属机房">{c.room_name}</Descriptions.Item>
          <Descriptions.Item label="机房位置">{c.room_location ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="具体位置">{c.location ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="租赁客户">{c.customer_name ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="U位容量">{c.total_u}U</Descriptions.Item>
          <Descriptions.Item label="已用U位">
            <Tag color={c.used_u > c.total_u * 0.8 ? 'red' : 'green'}>{c.used_u}U</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="可用U位">{c.available_u}U</Descriptions.Item>
          <Descriptions.Item label="U位利用率">{c.u_usage_rate}%</Descriptions.Item>
          <Descriptions.Item label="额定功率">
            {c.total_power ? `${c.total_power}W` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="已用功率">
            {c.total_power ? (
              <Tag color={c.power_usage_rate > 80 ? 'red' : 'green'}>{c.used_power}W</Tag>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="功率利用率">
            {c.total_power ? `${c.power_usage_rate}%` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="最大承重">
            {c.max_weight ? `${c.max_weight}KG` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="设备数">{c.device_count}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDateTime(c.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间" span={1}>
            {formatDateTime(c.updated_at)}
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={1}>
            {c.notes || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="U位布局" style={{ marginTop: 16 }}>
        <UPositionSelector
          totalU={c.total_u}
          ratedPower={c.total_power ?? undefined}
          occupiedPositions={occupiedPositions}
          readOnly={false}
          onPositionChange={handlePositionChange}
          onNodeReorder={(chassisId, newOrderedNodeIds) => {
            console.log('机箱子节点重排:', chassisId, newOrderedNodeIds);
          }}
          onSelect={() => {}}
        />
      </Card>
    </div>
  );
}

export default CabinetDetail;
