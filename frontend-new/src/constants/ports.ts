/**
 * 端口类型模板（跨模块共享常量）
 *
 * 原收敛于 AddDevicesModal/shared.ts，因被 7+ 处消费
 * （BatchAddTab / DeviceForm / useDeviceSubmit / UnifiedPortTab / BatchUpdateConfigModal 等），
 * 上提至独立的 constants 模块，消除 DeviceForm 经 deviceFormUtils 重导出的中间层，
 * 并让常量与运行时逻辑解耦（纯数据，无 React 依赖）。
 */

export const PORT_TYPE_TEMPLATES = [
  { label: 'GE（千兆）', value: 'GE', speed: '1G', prefix: 'GE' },
  { label: '10GE（万兆）', value: '10GE', speed: '10G', prefix: '10GE' },
  { label: '40GE', value: '40GE', speed: '40G', prefix: '40GE' },
  { label: '100GE', value: '100GE', speed: '100G', prefix: '100GE' },
  { label: '200GE', value: '200GE', speed: '200G', prefix: '200GE' },
  { label: '400GE', value: '400GE', speed: '400G', prefix: '400GE' },
  { label: '800GE', value: '800GE', speed: '800G', prefix: '800GE' },
  { label: '自定义', value: 'custom', speed: '', prefix: '' }
];
