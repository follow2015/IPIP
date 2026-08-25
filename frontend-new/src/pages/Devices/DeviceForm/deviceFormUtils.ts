/**
 * DeviceForm 纯工具函数与常量
 *
 * 从原 DeviceForm.tsx 拆出：设备名称/资产编号自动生成、存储配置文本解析。
 * 均为不依赖 React 的纯函数，便于单独单元测试。
 *
 * 注意：TYPE_CODE 和 PORT_TYPE_TEMPLATES 已统一收敛到
 * AddDevicesModal/shared.ts，本文件从该处导入，消除跨目录重复定义。
 */

import { TYPE_CODE } from '../AddDevicesModal/shared';


export { generateAssetNumber } from '@/components/AssetInfoFields';

export function generateDeviceName(deviceType?: string): string {
  const code = (deviceType && TYPE_CODE[deviceType]) || 'DEV';
  const now = new Date();
  const d = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const r = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `${code}-${d}-${r}`;
}


function parseStorageSegment(seg: string): {
  storage_type: string;
  capacity: string;
  interface_type: string | null;
  count: number;
} | null {
  const typeMatch = seg.match(/\b(SSD|HDD|NVMe)\b/i);
  if (!typeMatch) return null;
  const storage_type = typeMatch[1].toUpperCase();

  const capMatch = seg.match(/(\d+(?:\.\d+)?)\s*(TB|GB|MB)/i);
  if (!capMatch) return null;
  const capacity = `${capMatch[1]}${capMatch[2].toUpperCase()}`;

  let count = 1;
  const preMatch = seg.match(/(\d+)\s*[×x*]\s*/);
  if (preMatch) {
    count = parseInt(preMatch[1], 10);
  } else {
    const postMatch = seg.match(/[×x*]\s*(\d+)\s*$/i);
    if (postMatch) count = parseInt(postMatch[1], 10);
  }

  let interface_type: string | null = null;
  const ifaceMatch = seg.match(/\b(SATA|SAS|NVMe|M\.2|U\.2|PCIe)\b/i);
  if (ifaceMatch) {
    const u = ifaceMatch[1].toUpperCase();
    if (u === 'NVME' && storage_type !== 'NVME') {
      /* skip */
    } else {
      interface_type = ifaceMatch[1];
    }
  }

  return { storage_type, capacity, interface_type, count };
}

export interface StorageItem {
  storage_type: string;
  capacity: string;
  interface_type: string | null;
  count: number;
}

export function parseStorageConfig(text: string): {
  valid: boolean;
  preview: string;
  items: StorageItem[];
  errors: string[];
} {
  if (!text.trim()) return { valid: true, preview: '', items: [], errors: [] };
  const segments = text.split(/\s*[,;，；]\s*|\s*\+\s*/).filter(Boolean);
  const items: StorageItem[] = [];
  const errors: string[] = [];

  for (const seg of segments) {
    const parsed = parseStorageSegment(seg.trim());
    if (parsed) items.push(parsed);
    else errors.push(seg.trim());
  }

  if (items.length === 0 && text.trim()) {
    return { valid: false, preview: '', items: [], errors: [text.trim()] };
  }

  const preview = items
    .map((i) => {
      const c = i.count > 1 ? `${i.count}×` : '';
      const iface = i.interface_type ? ` ${i.interface_type}` : '';
      return `${c}${i.capacity} ${i.storage_type}${iface}`;
    })
    .join(' + ');

  return { valid: errors.length === 0, preview, items, errors };
}

export function computeStorageSummary(items: StorageItem[]): {
  totalGb: number;
  byType: Record<string, { count: number; totalGb: number }>;
} {
  let totalGb = 0;
  const byType: Record<string, { count: number; totalGb: number }> = {};

  for (const item of items) {
    const capMatch = item.capacity.match(/(\d+(?:\.\d+)?)\s*(TB|GB|MB)/i);
    if (!capMatch) continue;
    const val = parseFloat(capMatch[1]);
    const unit = capMatch[2].toUpperCase();
    let gb = val;
    if (unit === 'TB') gb = val * 1024;
    else if (unit === 'MB') gb = val / 1024;

    const totalItemGb = gb * item.count;
    totalGb += totalItemGb;

    if (!byType[item.storage_type]) {
      byType[item.storage_type] = { count: 0, totalGb: 0 };
    }
    byType[item.storage_type].count += item.count;
    byType[item.storage_type].totalGb += totalItemGb;
  }

  return { totalGb, byType };
}
