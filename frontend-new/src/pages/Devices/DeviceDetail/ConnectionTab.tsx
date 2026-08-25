import { confirm } from '@/utils/confirm';

import { useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Table, Button, Form, Tag, Alert } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import ConnectionFormModal from './ConnectionFormModal';
import ConnectionEditModal from './ConnectionEditModal';
import {
  useDeviceConnections,
  usePortLinks,
  useSwitchConnections,
  useCreateConnection,
  useDeleteConnection,
  useDisconnectPortLink,
  useUpdatePortLink,
  useUpdateConnection
} from '@/services/device-connection';
import type { PortLink, PortLinkUpdateRequest } from '@/services/device-connection';
import { useDeviceNics } from '@/services/device-nic';
import { useNetworkPorts } from '@/services/network-port';
import { useDeviceList } from '@/services/device';
import { useRoomOptions, useRoomCabinets } from '@/services/room';
import { useVLANsByDevice } from '@/services/vlan';
import { useLinkAggregationGroups } from '@/services/link-aggregation';
import { useMessage } from '@/hooks/useMessage';
import { useDeviceEvents } from '@/hooks/useDeviceEvents';
import { useD2NConnectionSync } from '@/hooks/useD2NConnectionSync';
import { LinkType, DeviceType, CONNECTION_STATUS_MAP } from '@/types/enums';
import StatusTag from '@/components/StatusTag';
import type {
  Device,
  SwitchPort,
  DeviceNicPort,
  DeviceConnection,
  VLAN,
  LinkAggregationGroup
} from '@/types/models';
import { isPhysicalPort } from '@/utils/portType';


const CONNECTION_TYPE_OPTIONS = [
  { label: '以太网', value: 'ethernet' },
  { label: '光纤', value: 'fiber' },
  { label: '管理口', value: 'management' },
  { label: '串口', value: 'serial' },
  { label: '其他', value: 'other' }
];

const CONNECTION_TYPE_LABEL_MAP: Record<string, string> = Object.fromEntries(
  CONNECTION_TYPE_OPTIONS.map(({ label, value }) => [value, label])
);
interface ConnectionTabProps {
  device: Device;
}


function ConnectionTab({ device }: ConnectionTabProps) {
  const deviceId = device.id;
  
  const isNetworkDevice = device.device_type === DeviceType.NETWORK;
  
  const {
    data: deviceConnections,
    isLoading,
    isError
  } = useDeviceConnections(isNetworkDevice ? 0 : deviceId);
  const {
    data: portLinks,
    isLoading: isPortLinksLoading,
    isError: isPortLinksError
  } = usePortLinks(isNetworkDevice ? deviceId : 0);
  
  const {
    data: switchConnections,
    isLoading: isSwitchConnsLoading,
    isError: isSwitchConnsError
  } = useSwitchConnections(isNetworkDevice ? deviceId : 0);

  
  const connections = useMemo(() => {
    if (isNetworkDevice) {
      const n2n = (portLinks ?? []) as (DeviceConnection | PortLink)[];
      const d2n = (switchConnections ?? []) as (DeviceConnection | PortLink)[];
      return [...n2n, ...d2n];
    }
    return deviceConnections ?? [];
  }, [isNetworkDevice, portLinks, switchConnections, deviceConnections]);

  const isLoadingConnections = isNetworkDevice
    ? isPortLinksLoading || isSwitchConnsLoading
    : isLoading;
  
  const isErrorConnections = isNetworkDevice ? isPortLinksError || isSwitchConnsError : isError;
  const createConnection = useCreateConnection(deviceId);
  const deleteConnection = useDeleteConnection(deviceId);
  const disconnectPortLink = useDisconnectPortLink(deviceId);
  const updatePortLink = useUpdatePortLink(deviceId);
  const updateConnection = useUpdateConnection();
  const message = useMessage();

  
  useDeviceEvents(deviceId, 'connections');

  
  const d2nSwitchIds = useMemo(() => {
    if (isNetworkDevice) return [];
    return Array.from(
      new Set(
        (deviceConnections ?? [])
          .map((c) => (c as DeviceConnection).switch_device_id)
          .filter((id): id is number => Boolean(id))
      )
    );
  }, [isNetworkDevice, deviceConnections]);

  useD2NConnectionSync(deviceId, d2nSwitchIds);
  const [formOpen, setFormOpen] = useState(false);
  const [editFormOpen, setEditFormOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<DeviceConnection | PortLink | null>(null);
  const [editForm] = Form.useForm();
  const [form] = Form.useForm();

  
  const selectedRoomId = Form.useWatch('room_id', form);
  const selectedCabinetId = Form.useWatch('cabinet_id', form);
  const selectedSwitchId = Form.useWatch('switch_device_id', form);

  
  const { data: roomOptions } = useRoomOptions();

  
  const { data: cabinetList } = useRoomCabinets(selectedRoomId ?? 0);
  const cabinetOptions = useMemo(() => {
    const cabinets = cabinetList ?? [];
    return cabinets.map((c) => ({ label: c.cabinet_number, value: c.id }));
  }, [cabinetList]);

  
  const switchQueryParams = useMemo(() => {
    const params: Record<string, unknown> = { device_type: 'network', per_page: 999 };
    if (selectedRoomId) {
      params.room_id = selectedRoomId;
    }
    if (selectedCabinetId) {
      params.cabinet_id = selectedCabinetId;
    }
    return params;
  }, [selectedRoomId, selectedCabinetId]);
  const { data: switchData } = useDeviceList(switchQueryParams);

  
  const switchOptions = useMemo(() => {
    const devices = switchData?.items ?? [];
    return devices
      .filter((d) => d.id !== deviceId) 
      .map((d) => ({
        label: `${d.device_name} (${d.management_ip || d.device_model || '-'})`,
        value: d.id
      }));
  }, [switchData, deviceId]);

  
  const { data: peerPorts } = useNetworkPorts(selectedSwitchId ?? 0);

  
  const peerPortOptions = useMemo(() => {
    const ports: SwitchPort[] = peerPorts ?? [];
    return ports
      .filter((p) => isPhysicalPort(p.port_name))
      .map((p) => ({
        label: `${p.port_name} (${p.speed}${p.port_type ? `/${p.port_type}` : ''}${p.customer_name ? ` - ${p.customer_name}` : ''})`,
        value: p.id,
        port: p
      }));
  }, [peerPorts]);

  
  const { data: nics } = useDeviceNics(deviceId);

  
  const nicPortOptions = useMemo(() => {
    const ports: DeviceNicPort[] = nics ?? [];
    return ports
      .filter((p) => p.port_status === 'free' || !p.port_status)
      .map((p) => ({
        label: `${p.display_name || p.port_name} (${p.port_speed || '-'}${p.port_type ? `/${p.port_type}` : ''})`,
        value: p.id
      }));
  }, [nics]);

  
  const { data: localPorts } = useNetworkPorts(deviceId);

  
  const localPortOptions = useMemo(() => {
    const ports: SwitchPort[] = localPorts ?? [];
    return ports
      .filter((p) => isPhysicalPort(p.port_name))
      .map((p) => ({
        label: `${p.port_name} (${p.speed}${p.port_type ? `/${p.port_type}` : ''})`,
        value: p.id,
        port: p
      }));
  }, [localPorts]);

  
  const { data: deviceVlans } = useVLANsByDevice(deviceId);
  const vlanOptions = useMemo(
    () =>
      (deviceVlans ?? []).map((v: VLAN) => ({
        label: `${v.vlan_id} - ${v.name || '未命名'}`,
        value: v.vlan_id
      })),
    [deviceVlans]
  );

  
  const { data: deviceLags } = useLinkAggregationGroups(deviceId);
  const lagOptions = useMemo(
    () =>
      (deviceLags ?? []).map((l: LinkAggregationGroup) => ({
        label: l.lag_name || `LAG ${l.id}`,
        value: l.id
      })),
    [deviceLags]
  );

  
  const vlanMap = useMemo(
    () => new Map((deviceVlans ?? []).map((v: VLAN) => [v.vlan_id, v])),
    [deviceVlans]
  );
  const lagMap = useMemo(
    () => new Map((deviceLags ?? []).map((l: LinkAggregationGroup) => [l.id, l])),
    [deviceLags]
  );

  
  const linkTypeOptions = isNetworkDevice
    ? [{ label: '网络→网络', value: LinkType.NETWORK_TO_NETWORK }]
    : [{ label: '设备→网络', value: LinkType.DEVICE_TO_NETWORK }];

  
  const handleAdd = () => {
    form.resetFields();
    
    const defaultLinkType = isNetworkDevice
      ? LinkType.NETWORK_TO_NETWORK
      : LinkType.DEVICE_TO_NETWORK;
    form.setFieldsValue({
      link_type: defaultLinkType
    });
    setFormOpen(true);
  };

  
  const handleDelete = useCallback(
    (connId: number, switchDeviceId?: number) => {
      confirm({
        title: '确认删除',
        content: '确定要删除该连接吗？',
        onOk: async () => {
          try {
            await deleteConnection.mutateAsync({ connId, switchDeviceId });
            message.success('删除成功');
          } catch (err) {
            message.error(err instanceof Error ? err.message : '删除失败');
          }
        }
      });
    },
    [deleteConnection, message]
  );

  
  const handleDeletePortLink = useCallback(
    (portId: number) => {
      confirm({
        title: '确认断开',
        content: '确定要断开该端口互联吗？将双向释放端口。',
        onOk: async () => {
          try {
            await disconnectPortLink.mutateAsync(portId);
            message.success('断开成功');
          } catch (err) {
            message.error(err instanceof Error ? err.message : '断开失败');
          }
        }
      });
    },
    [disconnectPortLink, message]
  );

  
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      const { room_id, cabinet_id, ...payload } = values;
      await createConnection.mutateAsync(payload);
      message.success('创建成功');
      setFormOpen(false);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  
  const handleEdit = useCallback(
    (record: DeviceConnection | PortLink) => {
      setEditRecord(record);
      editForm.setFieldsValue({
        connection_type: record.connection_type ?? undefined,
        vlan_id: (record as PortLink).vlan_id ?? undefined,
        status: (record as PortLink).status ?? (record as DeviceConnection).status ?? undefined,
        notes: record.notes ?? undefined,
        bandwidth: (record as PortLink).bandwidth ?? undefined,
        description: (record as PortLink).description ?? undefined,
        lag_group_id: (record as PortLink).lag_group_id ?? undefined
      });
      setEditFormOpen(true);
    },
    [editForm]
  );

  
  const handleEditSubmit = async () => {
    if (!editRecord) return;
    try {
      const values = await editForm.validateFields();
      if (editRecord.link_type === 'network_to_network') {
        
        await updatePortLink.mutateAsync({
          connectionId: editRecord.id,
          data: values as PortLinkUpdateRequest
        });
      } else {
        
        await updateConnection.mutateAsync({
          connId: editRecord.id,
          data: {
            connection_type: values.connection_type,
            notes: values.notes
          }
        });
      }
      message.success('更新成功');
      setEditFormOpen(false);
      setEditRecord(null);
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: '连接类型',
        dataIndex: 'connection_type',
        key: 'connection_type',
        render: (v: string) => (v ? (CONNECTION_TYPE_LABEL_MAP[v] ?? v) : '-')
      },
      {
        title: '连接模式',
        dataIndex: 'link_type',
        key: 'link_type',
        render: (v: string) => (
          <Tag color={v === 'device_to_network' ? 'blue' : 'purple'}>
            {v === 'device_to_network' ? '设备→网络' : '网络→网络'}
          </Tag>
        )
      },
      {
        title: '本机端口',
        key: 'local_port',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          if (record.link_type === 'network_to_network') {
            return (
              ('port_name' in record
                ? (record as PortLink).port_name
                : (record as DeviceConnection).switch_port_name) || '-'
            );
          }
          
          if (isNetworkDevice) {
            return (record as DeviceConnection).switch_port_name || '-';
          }
          return (
            ('source_port_display' in record
              ? (record as DeviceConnection).source_port_display
              : '-') || '-'
          );
        }
      },
      {
        title: '对端设备',
        key: 'peer_device',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          if (record.link_type === 'network_to_network') {
            const displayName = record.peer_device_name || '-';
            const targetId = record.peer_device_id;
            if (targetId) {
              return <Link to={`/switches/${targetId}`}>{displayName}</Link>;
            }
            return displayName;
          }
          
          const d2n = record as DeviceConnection;
          if (isNetworkDevice) {
            const displayName = d2n.device_name || '-';
            if (d2n.device_id) {
              return <Link to={`/devices/${d2n.device_id}`}>{displayName}</Link>;
            }
            return displayName;
          }
          const displayName = d2n.switch_name || '-';
          if (d2n.switch_device_id) {
            return <Link to={`/switches/${d2n.switch_device_id}`}>{displayName}</Link>;
          }
          return displayName;
        }
      },
      {
        title: '对端端口',
        key: 'peer_port',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          if (record.link_type === 'network_to_network') {
            return record.peer_port_name || '-';
          }
          
          if (isNetworkDevice) {
            return (record as DeviceConnection).source_port_display || '-';
          }
          return (
            ('switch_port_name' in record ? (record as DeviceConnection).switch_port_name : '-') ||
            '-'
          );
        }
      },
      {
        title: '状态',
        key: 'status',
        render: (_: unknown, record: DeviceConnection | PortLink) => (
          <StatusTag status={record.status} statusMap={CONNECTION_STATUS_MAP} />
        )
      },
      {
        title: 'VLAN',
        key: 'vlan_id',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          const vid = (record as PortLink).vlan_id;
          if (!vid) return '-';
          const vlan = vlanMap.get(vid);
          return vlan ? `${vid} - ${vlan.name || '未命名'}` : String(vid);
        }
      },
      {
        title: '带宽',
        key: 'bandwidth',
        render: (_: unknown, record: DeviceConnection | PortLink) =>
          (record as PortLink).bandwidth ?? '-'
      },
      {
        title: 'LAG 组',
        key: 'lag_group_id',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          const lagId = (record as PortLink).lag_group_id;
          if (!lagId) return '-';
          const lag = lagMap.get(lagId);
          return lag ? lag.lag_name || `LAG ${lagId}` : String(lagId);
        }
      },
      { title: '备注', dataIndex: 'notes', key: 'notes', render: (v: string) => v || '-' },
      {
        title: '操作',
        key: 'action',
        render: (_: unknown, record: DeviceConnection | PortLink) => {
          
          if (record.link_type === 'network_to_network') {
            return (
              <>
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => handleEdit(record)}
                />
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleDeletePortLink(record.id)}
                />
              </>
            );
          }
          return (
            <>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEdit(record)}
              />
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() =>
                  handleDelete(
                    record.id,
                    (record as DeviceConnection).switch_device_id ?? undefined
                  )
                }
              />
            </>
          );
        }
      }
    ],
    [isNetworkDevice, vlanMap, lagMap, handleEdit, handleDelete, handleDeletePortLink]
  );

  return (
    <div>
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增连接
        </Button>
      </div>
      {isErrorConnections && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="连接数据加载失败"
          description="请检查网络后重试，或联系管理员。"
        />
      )}
      <Table
        columns={columns}
        dataSource={connections ?? []}
        rowKey="id"
        loading={isLoadingConnections}
        size="small"
      />

      <ConnectionFormModal
        open={formOpen}
        onOk={handleSubmit}
        onCancel={() => setFormOpen(false)}
        form={form}
        isNetworkDevice={isNetworkDevice}
        linkTypeOptions={linkTypeOptions}
        connectionTypeOptions={CONNECTION_TYPE_OPTIONS}
        roomOptions={roomOptions}
        cabinetOptions={cabinetOptions}
        switchOptions={switchOptions}
        peerPortOptions={peerPortOptions}
        localPortOptions={localPortOptions}
        nicPortOptions={nicPortOptions}
      />

      {}
      <ConnectionEditModal
        open={editFormOpen}
        onOk={handleEditSubmit}
        onCancel={() => {
          setEditFormOpen(false);
          setEditRecord(null);
        }}
        form={editForm}
        editRecord={editRecord}
        connectionTypeOptions={CONNECTION_TYPE_OPTIONS}
        vlanOptions={vlanOptions}
        lagOptions={lagOptions}
      />
    </div>
  );
}

export default ConnectionTab;
