import { confirm } from '@/utils/confirm';

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Form, Input, Row, Col, Modal } from 'antd';
import dayjs from 'dayjs';
import {
  useCreateDevice,
  useUpdateDevice,
  useDeviceList,
  useDeviceDetail
} from '@/services/device';
import { useMessage } from '@/hooks/useMessage';
import { useRoomOptions } from '@/services/room';
import {
  useCabinetOptions,
  useCabinetAvailableUPositions,
  useCabinetLayout
} from '@/services/cabinet';
import { useAllocatableCustomerOptions } from '@/services/customer';
import { useUserOptions } from '@/services/user';
import { useUpdateSwitch } from '@/services/switch';
import { usePortLinks } from '@/services/device-connection';
import { useComponentTemplates } from '@/services/component-template';
import HardwareConfigFields, { buildStorageSummary } from '@/components/HardwareConfigFields';
import NicConfigFields from '@/components/NicConfigFields';
import {
  DeviceType,
  DeviceSubtype,
  DEVICE_SUBTYPE_MAP,
  DEVICE_SUBTYPE_LABELS,
  DEVICE_TYPE_MAP,
  DeviceStatusCode,
  DEVICE_STATUS_MAP
} from '@/types/enums';
import type { Device, DeviceNicPort } from '@/types/models';

import {
  generateDeviceName,
  parseStorageConfig,
  computeStorageSummary,
  type StorageItem
} from './deviceFormUtils';
import { PORT_TYPE_TEMPLATES } from '@/constants/ports';
import NetworkTopologyFields from './NetworkTopologyFields';
import BasicInfoFields from './BasicInfoFields';
import NetworkInfoFields from './NetworkInfoFields';
import SwitchConfigFields from './SwitchConfigFields';
import PortGenerationFields from './PortGenerationFields';
import ChassisConfigFields from './ChassisConfigFields';
import LocationInfoFields from './LocationInfoFields';
import { useDeviceSubmit } from './useDeviceSubmit';
import AssetInfoFields from '@/components/AssetInfoFields';
import { getCategoryConfig } from '../shared/categoryConfig';


const DEVICE_DATE_FIELDS: (keyof Device)[] = [
  'purchase_date',
  'warranty_start',
  'warranty_end',
  'online_date',
  'offline_date'
];


interface DeviceFormProps {
  open: boolean;
  editRecord: Device | null;
  onClose: () => void;
  
  defaultDeviceType?: string;
  
  editDeviceId?: number;
}


function DeviceForm({
  open,
  editRecord: editRecordProp,
  onClose,
  defaultDeviceType,
  editDeviceId
}: DeviceFormProps) {
  const [form] = Form.useForm();
  const message = useMessage();
  const createDevice = useCreateDevice();
  const updateDevice = useUpdateDevice();
  const updateSwitch = useUpdateSwitch();
  const { data: roomOptions } = useRoomOptions();
  const { data: customerOptions } = useAllocatableCustomerOptions();
  const { data: userOptions } = useUserOptions();

  
  const customerId = Form.useWatch('customer_id', form);

  
  const { data: cpuTemplates = [] } = useComponentTemplates('cpu', customerId);
  const { data: memoryTemplates = [] } = useComponentTemplates('memory', customerId);
  const { data: diskTemplates = [] } = useComponentTemplates('disk', customerId);
  const { data: nicComponentTemplates = [], isLoading: nicTplLoading } = useComponentTemplates(
    'nic',
    customerId
  );

  const isEdit = !!editRecordProp || !!editDeviceId;

  
  const { data: fetchedDevice } = useDeviceDetail(editDeviceId ?? 0);
  
  const editRecord = editRecordProp ?? (editDeviceId ? (fetchedDevice ?? null) : null);

  
  const prevDeviceType = useRef<string | undefined>(undefined);

  
  const prevRoomId = useRef<number | undefined>(undefined);

  
  const prevChassisId = useRef<number | undefined>(undefined);

  
  const deviceType = Form.useWatch('device_type', form);
  const deviceSubtype = Form.useWatch('device_subtype', form);
  const selectedRoomId = Form.useWatch('room_id', form);
  const selectedCabinetId = Form.useWatch('cabinet_id', form);
  const selectedChassisId = Form.useWatch('parent_device_id', form);
  
  const watchedNodePosition = Form.useWatch('node_position', form);
  
  const watchedUPosition = Form.useWatch('u_position', form);
  const watchedHeightU = Form.useWatch('height_u', form);

  
  const [generateNodes, setGenerateNodes] = useState(false);

  
  const { data: cabinetOptions } = useCabinetOptions(selectedRoomId, false, [1, 2]);

  
  const { data: availableUPositions } = useCabinetAvailableUPositions(selectedCabinetId ?? 0);

  
  const { data: cabinetLayout } = useCabinetLayout(selectedCabinetId ?? 0);

  
  const { data: chassisData } = useDeviceList({
    device_type: DeviceType.SERVER,
    device_subtype: DeviceSubtype.CHASSIS,
    room_id: selectedRoomId ?? undefined,
    per_page: 999
  });

  
  const { data: allChassisNodesData } = useDeviceList({
    device_type: DeviceType.SERVER,
    device_subtype: DeviceSubtype.NODE,
    room_id: selectedRoomId ?? undefined,
    per_page: 999
  });

  
  const { data: chassisNodesData } = useDeviceList({
    parent_device_id: selectedChassisId ?? undefined,
    per_page: 999
  });

  
  const [storageValidation, setStorageValidation] = useState<{
    valid: boolean;
    preview: string;
    items: StorageItem[];
    errors: string[];
  }>({ valid: true, preview: '', items: [], errors: [] });

  
  const subtypeOptions = deviceType
    ? (DEVICE_SUBTYPE_MAP[deviceType as DeviceType] ?? []).map((st) => ({
        label: DEVICE_SUBTYPE_LABELS[st],
        value: st
      }))
    : [];

  
  const serverCfg = getCategoryConfig(deviceType as DeviceType);
  const serverRegions =
    deviceType === DeviceType.SERVER
      ? (serverCfg.serverSubtypeSections?.[deviceSubtype as DeviceSubtype] ?? {
          hardware: true,
          nodeAssoc: false,
          chassis: false
        })
      : undefined;

  const showHardware = serverRegions?.hardware ?? false;
  const showChassisConfig = serverRegions?.chassis ?? false;
  const showNodeAssoc = serverRegions?.nodeAssoc ?? false;

  
  const showLocation = !showNodeAssoc;

  
  const isNetwork = deviceType === DeviceType.NETWORK;

  
  const hasSsh = Form.useWatch(['switch_config', 'has_ssh'], form);

  
  const isUnmanagedNetwork = isNetwork && !hasSsh;

  
  const showSwitchConfig = isNetwork && hasSsh;

  
  const portGroups = Form.useWatch('port_groups', form);

  
  const portPreview = useMemo(() => {
    if (!portGroups || portGroups.length === 0) return [];
    const allPorts: string[] = [];
    for (const group of portGroups) {
      const { template, slot, card, start, end, custom_prefix } = group ?? {};
      if (!template || !start || !end || start > end) continue;
      const tpl = PORT_TYPE_TEMPLATES.find((t) => t.value === template);
      const prefix = template === 'custom' ? (custom_prefix ?? '') : (tpl?.prefix ?? '');
      if (!prefix) continue;
      const s = slot ?? 0;
      const c = card ?? 0;
      for (let i = start; i <= end; i++) {
        allPorts.push(`${prefix}${s}/${c}/${i}`);
      }
    }
    return allPorts.slice(0, 500);
  }, [portGroups]);

  
  const showNicConfig = showHardware || (showChassisConfig && generateNodes);

  
  const chassisOptions = useMemo(() => {
    const chassisList = chassisData?.items ?? [];
    const allNodes = allChassisNodesData?.items ?? [];
    return chassisList
      .filter((chassis) => {
        const nodeCount = allNodes.filter(
          (n) => n.parent_device_id === chassis.id && n.id !== editRecord?.id
        ).length;
        if (chassis.total_nodes && nodeCount >= chassis.total_nodes) return false;
        return true;
      })
      .map((chassis) => {
        const currentNodeCount = allNodes.filter((n) => n.parent_device_id === chassis.id).length;
        const maxNodes = chassis.total_nodes ?? '∞';
        return {
          label: `${chassis.device_name} (${currentNodeCount}/${maxNodes}节点)`,
          value: chassis.id
        };
      });
  }, [chassisData, allChassisNodesData, editRecord]);

  
  const availablePositions = useMemo(() => {
    if (!selectedChassisId) return [];
    const chassis = chassisData?.items?.find((c) => c.id === selectedChassisId);
    if (!chassis) return [];

    const maxNodes = chassis.total_nodes ?? 0;
    if (!maxNodes) return [];

    const occupiedPositions = new Set(
      (chassisNodesData?.items ?? [])
        .filter((n) => n.id !== editRecord?.id)
        .map((n) => n.node_position)
        .filter((p): p is number => p !== null && p !== undefined)
    );

    const positions: number[] = [];
    for (let i = 1; i <= maxNodes; i++) {
      if (!occupiedPositions.has(i)) positions.push(i);
    }
    return positions;
  }, [selectedChassisId, chassisData, chassisNodesData, editRecord]);

  
  const uPositionStatus = useMemo(() => {
    const uPos = form.getFieldValue('u_position');
    const heightU = form.getFieldValue('height_u') ?? 1;
    if (!selectedCabinetId || !uPos || !availableUPositions) return null;

    const conflicts: number[] = [];
    for (let i = uPos; i < uPos + heightU; i++) {
      if (!availableUPositions.includes(i)) {
        if (!isEdit || !editRecord?.u_position || !editRecord?.height_u) {
          conflicts.push(i);
        } else {
          const myStart = editRecord.u_position;
          const myEnd = editRecord.u_position + editRecord.height_u - 1;
          if (i < myStart || i > myEnd) {
            conflicts.push(i);
          }
        }
      }
    }
    return conflicts.length > 0 ? conflicts : null;
  }, [
    selectedCabinetId,
    form.getFieldValue('u_position'),
    form.getFieldValue('height_u'),
    availableUPositions,
    isEdit,
    editRecord
  ]);

  
  const handleAutoAssignUPosition = useCallback(() => {
    if (!availableUPositions || availableUPositions.length === 0) {
      message.warning('当前机柜无可用U位');
      return;
    }
    const heightU = form.getFieldValue('height_u') ?? 1;
    const gap = form.getFieldValue('device_gap') ?? 0;

    const sorted = [...availableUPositions].sort((a, b) => a - b);

    
    let candidatePositions = sorted;
    if (isEdit && editRecord?.u_position) {
      const myPositions: number[] = [];
      for (
        let i = editRecord.u_position;
        i < editRecord.u_position + (editRecord.height_u || 1);
        i++
      ) {
        myPositions.push(i);
      }
      candidatePositions = [...myPositions, ...sorted].sort((a, b) => a - b);
    }

    const needed = heightU + gap;
    for (let i = 0; i <= candidatePositions.length - needed; i++) {
      const start = candidatePositions[i];
      let continuous = true;
      for (let j = 1; j < needed; j++) {
        if (candidatePositions[i + j] !== start + j) {
          continuous = false;
          break;
        }
      }
      if (continuous) {
        form.setFieldValue('u_position', start);
        message.success(`已分配U${start}~U${start + heightU - 1}`);
        return;
      }
    }
    message.warning(`无连续${needed}个U位可用`);
  }, [availableUPositions, form, message, isEdit, editRecord]);

  
  useEffect(() => {
    if (prevDeviceType.current !== undefined && prevDeviceType.current !== deviceType) {
      form.setFieldValue('device_subtype', undefined);
    }
    prevDeviceType.current = deviceType;
  }, [deviceType, form]);

  
  useEffect(() => {
    if (prevRoomId.current !== undefined && prevRoomId.current !== selectedRoomId) {
      form.setFieldValue('cabinet_id', undefined);
      form.setFieldValue('parent_device_id', undefined);
      form.setFieldValue('node_position', undefined);
      form.setFieldValue('u_position', undefined);
    }
    prevRoomId.current = selectedRoomId;
  }, [selectedRoomId, form]);

  
  useEffect(() => {
    if (prevChassisId.current !== undefined && prevChassisId.current !== selectedChassisId) {
      form.setFieldValue('node_position', undefined);
    }
    prevChassisId.current = selectedChassisId;
  }, [selectedChassisId, form]);

  
  useEffect(() => {
    if (!showNodeAssoc || !selectedChassisId || !watchedNodePosition) return;
    const chassis = chassisData?.items?.find((c) => c.id === selectedChassisId);
    if (!chassis) return;
    
    const pattern = chassis.node_naming_pattern || '{chassis}-Node{pos}';
    const newName = pattern
      .replace('{chassis}', chassis.device_name)
      .replace('{pos}', String(watchedNodePosition))
      .replace('{row}', String(Math.ceil(watchedNodePosition / (chassis.node_cols || 1))))
      .replace('{col}', String(((watchedNodePosition - 1) % (chassis.node_cols || 1)) + 1));
    form.setFieldValue('device_name', newName);
    form.setFieldValue('notes', `${chassis.device_name} 节点 ${watchedNodePosition}`);
  }, [showNodeAssoc, selectedChassisId, watchedNodePosition, chassisData, form]);

  
  useEffect(() => {
    if (open) {
      setGenerateNodes(false);
      if (editRecord) {
        
        prevDeviceType.current = undefined;
        prevRoomId.current = undefined;
        prevChassisId.current = undefined;

        
        const editValues = { ...editRecord };
        for (const f of DEVICE_DATE_FIELDS) {
          const v = editValues[f];
          if (typeof v === 'string' && v) {
            (editValues as Record<string, unknown>)[f] = dayjs(v);
          }
        }

        
        form.setFieldsValue({
          ...editValues,
          room_id: editRecord.room_id,
          responsible_person: editRecord.responsible_person
            ? Number(editRecord.responsible_person)
            : undefined
        });

        
        if (editRecord.device_type === DeviceType.NETWORK && editRecord.switch_credential) {
          const sc = editRecord.switch_credential;
          form.setFieldsValue({
            switch_config: {
              ip: sc.ip,
              port: sc.port_num ?? undefined,
              protocol: sc.protocol || (sc.has_ssh ? 'ssh' : 'telnet'),
              username: sc.username ?? undefined,
              device_type: sc.device_type || undefined,
              switch_role: sc.switch_role,
              layer: sc.layer ?? undefined,
              authentication_method: sc.authentication_method ?? undefined,
              
              has_ssh: sc.has_ssh,
              uplink_device_id: sc.uplink_device_id ?? undefined,
              uplink_port_ids: sc.uplink_port_ids ?? undefined,
              core_device_id: sc.core_device_id ?? undefined,
              port_num: sc.port_num ?? undefined
            }
          });
        }

        
        setTimeout(() => {
          prevDeviceType.current = editRecord.device_type;
          prevRoomId.current = editRecord.room_id ?? undefined;
          prevChassisId.current = editRecord.parent_device_id ?? undefined;
        }, 0);

        
        if (editRecord.storage_summary) {
          const result = parseStorageConfig(editRecord.storage_summary);
          if (result.items.length > 0) {
            form.setFieldValue(
              'storage_items',
              result.items.map((it) => ({
                count: it.count,
                template_id: undefined,
                capacity: it.capacity,
                storage_type: it.storage_type,
                interface_type: it.interface_type ?? undefined
              }))
            );
          }
        }

        
        if (editRecord.cpu_template_id) {
          form.setFieldValue('cpu_template_id', editRecord.cpu_template_id);
        }
        if (editRecord.memory_template_id) {
          form.setFieldValue('memory_template_id', editRecord.memory_template_id);
        }
        if (editRecord.memory_dimm_count) {
          form.setFieldValue('memory_dimm_count', editRecord.memory_dimm_count);
        }

        
        const nicPorts = editRecord.nic_ports;
        if (nicPorts?.length) {
          const nicGroups: Record<number, DeviceNicPort[]> = {};
          for (const p of nicPorts) {
            const num = p.nic_number ?? 1;
            if (!nicGroups[num]) nicGroups[num] = [];
            nicGroups[num].push(p);
          }
          const nicPortsFormValue = Object.entries(nicGroups).map(([, ports]) => ({
            template_id: ports[0]?.template_id || undefined,
            nic_number: ports[0]?.nic_number ?? 1
          }));
          form.setFieldValue('nic_ports', nicPortsFormValue);
        }

        
        const storageItemsData = editRecord.storage_items;
        if (storageItemsData?.length) {
          const storageItemsFormValue = storageItemsData.map((s) => ({
            template_id: s.template_id || undefined,
            storage_type: s.storage_type || undefined,
            capacity: s.capacity || undefined,
            interface_type: s.interface_type || undefined,
            count: 1,
            slot_number: s.slot_number
          }));
          form.setFieldValue('storage_items', storageItemsFormValue);
        }
      } else {
        form.resetFields();
        setStorageValidation({ valid: true, preview: '', items: [], errors: [] });
        form.setFieldValue('status', DeviceStatusCode.ONLINE);
        form.setFieldValue('height_u', 1);
        form.setFieldValue('device_gap', 2);
        
        if (defaultDeviceType) {
          form.setFieldValue('device_type', defaultDeviceType);
        }
        
        prevDeviceType.current = undefined;
        prevRoomId.current = undefined;
        prevChassisId.current = undefined;
      }
    }
  }, [open, editRecord, form]);

  
  const handleGenerateDeviceName = useCallback(() => {
    const name = generateDeviceName(deviceType);
    form.setFieldValue('device_name', name);
  }, [deviceType, form]);

  
  const handleStorageChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const text = e.target.value;
      const result = parseStorageConfig(text);
      setStorageValidation(result);
      if (result.valid && result.items.length > 0) {
        form.setFieldValue('storage_summary', buildStorageSummary(result.items));
      } else if (!text.trim()) {
        form.setFieldValue('storage_summary', undefined);
      }
    },
    [form]
  );

  
  const handleGenerateNodesChange = useCallback((checked: boolean) => {
    setGenerateNodes(checked);
    if (checked) {
      confirm({
        title: '生成子节点',
        content:
          '勾选后，保存时将自动创建所有子节点（包括已经存在的子节点），并使用下方输入的硬件配置统一设置所有子节点。确定？',
        okText: '确定',
        cancelText: '取消',
        onOk: () => {},
        onCancel: () => setGenerateNodes(false)
      });
    }
  }, []);

  
  const currentDeviceId = editRecord?.id;

  
  const { data: portLinks } = usePortLinks(currentDeviceId!);

  
  useEffect(() => {
    if (!isEdit || !currentDeviceId || !portLinks?.length) return;
    
    const uplinkDevId =
      form.getFieldValue(['switch_config', 'uplink_device_id']) ??
      editRecord?.switch_credential?.uplink_device_id;
    if (!uplinkDevId) return;
    
    const uplinkConns = portLinks.filter(
      (link: any) => link.peer_device_id === uplinkDevId || link.local_device_id === uplinkDevId
    );
    if (uplinkConns.length > 0) {
      
      
      const peerPortIds = uplinkConns.map((link: any) =>
        link.peer_device_id === uplinkDevId ? link.peer_port_id : link.local_port_id
      );
      form.setFieldValue(['switch_config', 'peer_port_ids'], peerPortIds);
    }
  }, [isEdit, currentDeviceId, portLinks]); 

  
  const { handleSubmit } = useDeviceSubmit({
    form,
    isEdit,
    editRecord,
    generateNodes,
    nicComponentTemplates,
    createDevice,
    updateDevice,
    message,
    onClose
  });

  
  const typeOptions = Object.entries(DEVICE_TYPE_MAP).map(([key, val]) => ({
    label: val.label,
    value: key
  }));

  
  const statusOptions = Object.entries(DEVICE_STATUS_MAP).map(([key, val]) => ({
    label: val.label,
    value: Number(key)
  }));

  return (
    <Modal
      title={isEdit ? '编辑设备' : '新增设备'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={createDevice.isPending || updateDevice.isPending}
      width={800}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" autoComplete="off">
        <BasicInfoFields
          typeOptions={typeOptions}
          subtypeOptions={subtypeOptions}
          statusOptions={statusOptions}
          userOptions={userOptions}
          customerOptions={customerOptions}
          roomOptions={roomOptions}
          chassisOptions={chassisOptions}
          availablePositions={availablePositions}
          selectedRoomId={selectedRoomId}
          selectedChassisId={selectedChassisId}
          showNodeAssoc={showNodeAssoc}
          onGenerateName={handleGenerateDeviceName}
        />
        {}
        {showHardware && <HardwareConfigFields form={form} customerId={customerId} showIpmi />}

        {}
        {showHardware && <NicConfigFields form={form} customerId={customerId} />}

        {}
        <NetworkInfoFields isNetwork={isNetwork} />

        {}
        {isNetwork && <NetworkTopologyFields form={form} isEdit={isEdit} editRecord={editRecord} />}

        {}
        {showSwitchConfig && <SwitchConfigFields isEdit={isEdit} />}

        {}
        {isUnmanagedNetwork && !isEdit && <PortGenerationFields portPreview={portPreview} />}

        {}
        {showChassisConfig && (
          <ChassisConfigFields
            form={form}
            customerId={customerId}
            generateNodes={generateNodes}
            onGenerateNodesChange={handleGenerateNodesChange}
            isEdit={isEdit}
          />
        )}

        {}
        {showLocation && (
          <LocationInfoFields
            roomOptions={roomOptions}
            cabinetOptions={cabinetOptions}
            uPositionStatus={uPositionStatus}
            selectedCabinetId={selectedCabinetId}
            availableUPositions={availableUPositions}
            onAutoAssignUPosition={handleAutoAssignUPosition}
            cabinetLayout={cabinetLayout}
            watchedUPosition={watchedUPosition}
            watchedHeightU={watchedHeightU}
          />
        )}

        {}
        <AssetInfoFields form={form} assetNumberMode="manual" defaultOnlineDateNow={!isEdit} />

        {}
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item name="notes" label="备注">
              <Input.TextArea rows={2} placeholder="备注信息" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

export default DeviceForm;
