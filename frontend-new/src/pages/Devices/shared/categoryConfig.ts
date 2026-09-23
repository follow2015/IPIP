
import { DeviceType, DeviceSubtype, type DeviceTypeKey } from '@/types/enums';
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

export type TabLabelKey =
  | 'tab.basic'
  | 'tab.nics'
  | 'tab.ports'
  | 'tab.vlans'
  | 'tab.lag'
  | 'tab.connections'
  | 'tab.storage'
  | 'tab.asset'
  | 'tab.nodes'
  | 'metric.title'
  | 'batchMonitor.credentialTitle';

export interface TabSpec {
  key: TabKey;
  labelKey: TabLabelKey;
  when?: (d: Pick<Device, 'is_chassis'>) => boolean;
}

export interface ServerSubtypeSections {
  hardware: boolean;
  nodeAssoc: boolean;
  chassis: boolean;
}

export interface CategoryConfig {
  key: DeviceType;
  labelKey: DeviceTypeKey;
  deviceType: DeviceType;
  detailTabs: TabSpec[];
  serverSubtypeSections?: Partial<Record<DeviceSubtype, ServerSubtypeSections>>;
  formSections: FormSectionKey[];
}

const T = (key: TabKey, labelKey: TabLabelKey, when?: TabSpec['when']): TabSpec => ({
  key,
  labelKey,
  when
});

export const CATEGORY_LIST: CategoryConfig[] = [
  {
    key: DeviceType.SERVER,
    labelKey: 'deviceType.SERVER',
    deviceType: DeviceType.SERVER,
    detailTabs: [
      T('basic', 'tab.basic'),
      T('nics', 'tab.nics', (d) => !d.is_chassis),
      T('connections', 'tab.connections', (d) => !d.is_chassis),
      T('storage', 'tab.storage', (d) => !d.is_chassis),
      T('asset', 'tab.asset'),
      T('nodes', 'tab.nodes', (d) => !!d.is_chassis),
      T('metrics', 'metric.title'),
      T('credentials', 'batchMonitor.credentialTitle', (d) => !d.is_chassis)
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
    labelKey: 'deviceType.NETWORK',
    deviceType: DeviceType.NETWORK,
    detailTabs: [
      T('basic', 'tab.basic'),
      T('ports', 'tab.ports'),
      T('vlans', 'tab.vlans'),
      T('lag', 'tab.lag'),
      T('connections', 'tab.connections'),
      T('storage', 'tab.storage'),
      T('asset', 'tab.asset'),
      T('metrics', 'metric.title'),
      T('credentials', 'batchMonitor.credentialTitle')
    ],
    formSections: ['basicInfo', 'location', 'switchConfig', 'portGeneration']
  },
  {
    key: DeviceType.OTHER,
    labelKey: 'deviceType.OTHER',
    deviceType: DeviceType.OTHER,
    detailTabs: [
      T('basic', 'tab.basic'),
      T('nics', 'tab.nics'),
      T('connections', 'tab.connections'),
      T('storage', 'tab.storage'),
      T('asset', 'tab.asset'),
      T('metrics', 'metric.title'),
      T('credentials', 'batchMonitor.credentialTitle')
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
