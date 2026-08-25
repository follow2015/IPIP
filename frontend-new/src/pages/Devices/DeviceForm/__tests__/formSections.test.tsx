import { describe, it, expect } from 'vitest';
import { getCategoryConfig } from '@/pages/Devices/shared/categoryConfig';
import { DeviceType, DeviceSubtype } from '@/types/enums';

describe('formSections / serverSubtypeSections（配置驱动表单区块）', () => {
  it('server 子类型映射：standalone/node/storage/gpu 显硬件，chassis 不显硬件', () => {
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

  it('network 类 formSections 含 switchConfig+portGeneration，server/other 不含', () => {
    const net = getCategoryConfig(DeviceType.NETWORK).formSections;
    expect(net).toEqual(expect.arrayContaining(['switchConfig', 'portGeneration']));
    expect(getCategoryConfig(DeviceType.SERVER).formSections).not.toContain('switchConfig');
    expect(getCategoryConfig(DeviceType.OTHER).formSections).not.toContain('switchConfig');
  });

  it('非 server 类别无子类型区块映射（serverRegions 恒 undefined → 区块全 false）', () => {
    expect(getCategoryConfig(DeviceType.NETWORK).serverSubtypeSections).toBeUndefined();
    expect(getCategoryConfig(DeviceType.OTHER).serverSubtypeSections).toBeUndefined();
  });
});
