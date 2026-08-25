import { describe, it, expect } from 'vitest';
import { DeviceType, DeviceSubtype } from '@/types/enums';
import { getCategoryConfig, CATEGORY_LIST, categoryFromDeviceType } from './categoryConfig';

describe('categoryConfig', () => {
  it('三类齐全且与 DeviceType 一一对应', () => {
    const keys = CATEGORY_LIST.map((c) => c.key).sort();
    expect(keys).toEqual(['network', 'other', 'server']);
    expect(CATEGORY_LIST.map((c) => c.deviceType).sort()).toEqual(
      [DeviceType.NETWORK, DeviceType.OTHER, DeviceType.SERVER].sort()
    );
  });

  it('server 类含 nics/connections/storage/asset 且 nodes 仅在 chassis 时', () => {
    const cfg = getCategoryConfig(DeviceType.SERVER);
    const keys = cfg.detailTabs.map((t) => t.key);
    expect(keys).toEqual(
      expect.arrayContaining(['basic', 'nics', 'connections', 'storage', 'asset'])
    );
    const nodesTab = cfg.detailTabs.find((t) => t.key === 'nodes');
    expect(nodesTab?.when?.({ is_chassis: true })).toBe(true);
    expect(nodesTab?.when?.({ is_chassis: false })).toBe(false);
  });

  it('network 类含 ports/vlans/lag，other 类无 ports 但含 nics（对齐现状 SERVER||OTHER）', () => {
    const net = getCategoryConfig(DeviceType.NETWORK).detailTabs.map((t) => t.key);
    expect(net).toEqual(expect.arrayContaining(['ports', 'vlans', 'lag']));
    const other = getCategoryConfig(DeviceType.OTHER).detailTabs.map((t) => t.key);
    expect(other).not.toContain('ports');
    expect(other).toContain('nics'); // 其他设备（PDU/UPS 等）详情同样显示网卡 tab
  });

  it('categoryFromDeviceType 映射正确', () => {
    expect(categoryFromDeviceType(DeviceType.SERVER)).toBe(DeviceType.SERVER);
    expect(categoryFromDeviceType(DeviceType.NETWORK)).toBe(DeviceType.NETWORK);
    expect(categoryFromDeviceType(DeviceType.OTHER)).toBe(DeviceType.OTHER);
  });

  it('serverSubtypeSections 等价于原 SERVER_REGION_MAP（子类型驱动区块）', () => {
    const sec = getCategoryConfig(DeviceType.SERVER).serverSubtypeSections!;
    expect(sec[DeviceSubtype.STANDALONE]).toEqual({
      hardware: true,
      nodeAssoc: false,
      chassis: false
    });
    expect(sec[DeviceSubtype.NODE]).toEqual({ hardware: true, nodeAssoc: true, chassis: false });
    expect(sec[DeviceSubtype.STORAGE]).toEqual({
      hardware: true,
      nodeAssoc: false,
      chassis: false
    });
    expect(sec[DeviceSubtype.GPU]).toEqual({ hardware: true, nodeAssoc: false, chassis: false });
    expect(sec[DeviceSubtype.CHASSIS]).toEqual({
      hardware: false,
      nodeAssoc: false,
      chassis: true
    });
  });

  it('非 server 类别无子类型区块映射', () => {
    expect(getCategoryConfig(DeviceType.NETWORK).serverSubtypeSections).toBeUndefined();
    expect(getCategoryConfig(DeviceType.OTHER).serverSubtypeSections).toBeUndefined();
  });
});
