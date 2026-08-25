
import { DeviceType, DeviceSubtype } from '@/types/enums';
import type { Device } from '@/types/models';

export type CategoryKey = DeviceType;

export type TabKey =
  | 'basic'
  | 'nics'
  | 'ports'
  | 'vlans'
  | 'lag'
  | 'connections'
  | 'storage'
  | 'asset'
  | 'nodes'
  | 'credentials'
  | 'metrics';

export type FormSectionKey =
  | 'basicInfo'
  | 'location'
  | 'hardware'
  | 'chassis'
  | 'nodeAssoc'
  | 'switchConfig'
  | 'portGeneration'
  | 'nicConfig';

export interface TabSpec {
  key: TabKey;
  label: string;
  when?: (d: Pick<Device, 'is_chassis'>) => boolean;
}

export interface ServerSubtypeSections {
  hardware: boolean;
  nodeAssoc: boolean;
  chassis: boolean;
}

export interface CategoryConfig {
  key: DeviceType;
  label: string;
  deviceType: DeviceType;
  detailTabs: TabSpec[];
  serverSubtypeSections?: Partial<Record<DeviceSubtype, ServerSubtypeSections>>;
  formSections: FormSectionKey[];
}

const T = (key: TabKey, label: string, when?: TabSpec['when']): TabSpec => ({ key, label, when });

export const CATEGORY_LIST: CategoryConfig[] = [
  {
    key: DeviceType.SERVER,
    label: '服务器',
    deviceType: DeviceType.SERVER,
    detailTabs: [
      T('basic', '基本信息'),
      T('nics', '网卡', (d) => !d.is_chassis),
      T('connections', '连接', (d) => !d.is_chassis),
      T('storage', '存储', (d) => !d.is_chassis),
      T('asset', '资产信息'),
      T('nodes', '子节点', (d) => !!d.is_chassis),
      T('metrics', '监控数据'),
      T('credentials', '监控凭据', (d) => !d.is_chassis)
    ],
    serverSubtypeSections: {
      [DeviceSubtype.STANDALONE]: { hardware: true, nodeAssoc: false, chassis: false },
      [DeviceSubtype.NODE]: { hardware: true, nodeAssoc: true, chassis: false },
      [DeviceSubtype.STORAGE]: { hardware: true, nodeAssoc: false, chassis: false },
      [DeviceSubtype.GPU]: { hardware: true, nodeAssoc: false, chassis: false },
      [DeviceSubtype.CHASSIS]: { hardware: false, nodeAssoc: false, chassis: true }
    },
    formSections: ['basicInfo', 'location', 'hardware', 'chassis', 'nodeAssoc', 'nicConfig']
  },
  {
    key: DeviceType.NETWORK,
    label: '网络设备',
    deviceType: DeviceType.NETWORK,
    detailTabs: [
      T('basic', '基本信息'),
      T('ports', '端口'),
      T('vlans', 'VLAN'),
      T('lag', '链路聚合'),
      T('connections', '连接'),
      T('storage', '存储'),
      T('asset', '资产信息'),
      T('metrics', '监控数据'),
      T('credentials', '监控凭据')
    ],
    formSections: ['basicInfo', 'location', 'switchConfig', 'portGeneration']
  },
  {
    key: DeviceType.OTHER,
    label: '其他设备',
    deviceType: DeviceType.OTHER,
    detailTabs: [
      T('basic', '基本信息'),
      T('nics', '网卡'),
      T('connections', '连接'),
      T('storage', '存储'),
      T('asset', '资产信息'),
      T('metrics', '监控数据'),
      T('credentials', '监控凭据')
    ],
    formSections: ['basicInfo', 'location']
  }
];

const BY_DEVICE_TYPE: Record<DeviceType, CategoryConfig> = {
  [DeviceType.SERVER]: CATEGORY_LIST[0],
  [DeviceType.NETWORK]: CATEGORY_LIST[1],
  [DeviceType.OTHER]: CATEGORY_LIST[2]
};

export function getCategoryConfig(deviceType: DeviceType): CategoryConfig {
  return BY_DEVICE_TYPE[deviceType] ?? CATEGORY_LIST[2]; // 兜底 other
}

export function categoryFromDeviceType(deviceType: DeviceType): CategoryKey {
  return getCategoryConfig(deviceType).key;
}
