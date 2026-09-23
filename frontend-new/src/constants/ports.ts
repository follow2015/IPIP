/**
 * 端口类型模板（跨模块共享常量）
 *
 * 原收敛于 AddDevicesModal/shared.ts，因被 7+ 处消费
 * （BatchAddTab / DeviceForm / useDeviceSubmit / UnifiedPortTab / BatchUpdateConfigModal 等），
 * 上提至独立的 constants 模块，消除 DeviceForm 经 deviceFormUtils 重导出的中间层，
 * 并让常量与运行时逻辑解耦（纯数据，无 React 依赖）。
 */

export type PortTemplateLabelKey = 'port.template.ge' | 'port.template.ge10' | 'port.template.custom';

export const PORT_TYPE_TEMPLATES: {
  labelKey?: PortTemplateLabelKey;
  value: string;
  speed: string;
  prefix: string;
}[] = [
  { labelKey: 'port.template.ge', value: 'GE', speed: '1G', prefix: 'GE' },
  { labelKey: 'port.template.ge10', value: '10GE', speed: '10G', prefix: '10GE' },
  { value: '40GE', speed: '40G', prefix: '40GE' },
  { value: '100GE', speed: '100G', prefix: '100GE' },
  { value: '200GE', speed: '200G', prefix: '200GE' },
  { value: '400GE', speed: '400G', prefix: '400GE' },
  { value: '800GE', speed: '800G', prefix: '800GE' },
  { labelKey: 'port.template.custom', value: 'custom', speed: '', prefix: '' }
];
