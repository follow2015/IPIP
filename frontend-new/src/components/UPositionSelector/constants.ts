import type { RackDeviceType, NodeStatus } from './types';

export const ROW_GAP = 2;

export type RackTypeLabelKey =
  | 'uposition.type.server'
  | 'uposition.type.switch'
  | 'uposition.type.storage'
  | 'uposition.type.multinode'
  | 'uposition.type.pdu'
  | 'uposition.type.kvm';

export const TYPE_CONFIG: Record<
  RackDeviceType,
  {
    labelKey: RackTypeLabelKey;
    bg: string;
    border: string;
    accent: string;
    text: string;
    subText: string;
  }
> = {
  server: {
    labelKey: 'uposition.type.server',
    bg: '#E6F1FB',
    border: '#B5D4F4',
    accent: '#378ADD',
    text: '#0C447C',
    subText: '#185FA5'
  },
  switch: {
    labelKey: 'uposition.type.switch',
    bg: '#EAF3DE',
    border: '#C0DD97',
    accent: '#639922',
    text: '#27500A',
    subText: '#3B6D11'
  },
  storage: {
    labelKey: 'uposition.type.storage',
    bg: '#FAEEDA',
    border: '#FAC775',
    accent: '#BA7517',
    text: '#412402',
    subText: '#854F0B'
  },
  multinode: {
    labelKey: 'uposition.type.multinode',
    bg: '#E1F5EE',
    border: '#9FE1CB',
    accent: '#0F6E56',
    text: '#04342C',
    subText: '#085041'
  },
  pdu: {
    labelKey: 'uposition.type.pdu',
    bg: '#EEEDFE',
    border: '#CECBF6',
    accent: '#534AB7',
    text: '#26215C',
    subText: '#3C3489'
  },
  kvm: {
    labelKey: 'uposition.type.kvm',
    bg: '#FBEAF0',
    border: '#F4C0D1',
    accent: '#993556',
    text: '#4B1528',
    subText: '#72243E'
  }
};

export const NODE_STATUS_COLOR: Record<NodeStatus, string> = {
  active: '#1D9E75',
  inactive: '#C0C0C0',
  fault: '#E24B4A'
};

export function pctColor(pct: number): string {
  return pct > 85 ? '#E24B4A' : pct > 65 ? '#BA7517' : '#1D9E75';
}
