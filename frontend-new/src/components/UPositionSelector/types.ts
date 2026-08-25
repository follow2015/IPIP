

export type RackDeviceType = 'server' | 'switch' | 'storage' | 'multinode' | 'pdu' | 'kvm';
export type NodeStatus = 'active' | 'inactive' | 'fault';

export interface DeviceNode {
  id: string;
  label: string;
  status: NodeStatus;
  ip?: string;
  ipmiAddress?: string;
  row?: number;
  col?: number;
}

export interface OccupiedPosition {
  uPosition: number;
  uSize: number;
  deviceId: number;
  deviceName: string;
  deviceType?: RackDeviceType;
  power?: number;
  ip?: string;
  ipmiAddress?: string;
  sn?: string;
  vendor?: string;
  model?: string;
  nodes?: DeviceNode[];
  nodeRows?: number;
  nodeCols?: number;
}

export interface UPositionSelectorProps {
  totalU?: number;
  ratedPower?: number;
  occupiedPositions: OccupiedPosition[];
  readOnly?: boolean;
  onPositionChange?: (deviceId: number, newUPos: number) => void;
  
  onNodeReorder?: (chassisId: number, newOrderedNodeIds: string[]) => void;
  onSelect?: (device: OccupiedPosition | null) => void;
}
