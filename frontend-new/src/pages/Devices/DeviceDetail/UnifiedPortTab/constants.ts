import type { DeviceT } from '@/types/statusMeta';

export const getUsageStatusFilterOptions = (t: DeviceT) => [
  { label: t('portUsage.FREE'), value: 'free' },
  { label: t('portUsage.OCCUPIED'), value: 'occupied' },
  { label: t('portUsage.DISABLED'), value: 'disabled' },
  { label: t('portUsage.ERROR'), value: 'error' }
];

export const getUsageStatusFormOptions = (t: DeviceT) => [
  { value: 'free', label: t('portUsage.FREE') },
  { value: 'occupied', label: t('portUsage.OCCUPIED') },
  { value: 'disabled', label: t('portUsage.DISABLED') }
];
