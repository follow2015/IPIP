/**
 * 配件规格字段组件
 * - 四类配件（CPU / 内存 / 硬盘 / 网卡）的 spec 字段动态渲染
 * - 每个组件接收 prefix 参数，用于 Form.Item 的 name 前缀嵌套
 */
import { Form, InputNumber, Select, Input } from 'antd';
import { useTranslation } from 'react-i18next';

type NicPortTypeKey =
  | 'rj45'
  | 'sfp'
  | 'sfpPlus'
  | 'sfp28'
  | 'qsfpPlus'
  | 'qsfp28'
  | 'qsfp56'
  | 'qsfpdd';

const NIC_PORT_TYPES: { key: NicPortTypeKey; value: string }[] = [
  { key: 'rj45', value: 'RJ45' },
  { key: 'sfp', value: 'SFP' },
  { key: 'sfpPlus', value: 'SFP+' },
  { key: 'sfp28', value: 'SFP28' },
  { key: 'qsfpPlus', value: 'QSFP+' },
  { key: 'qsfp28', value: 'QSFP28' },
  { key: 'qsfp56', value: 'QSFP56' },
  { key: 'qsfpdd', value: 'QSFP-DD' }
];

export function CpuSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const { t } = useTranslation('settings');
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('cores_per_cpu')} label={t('componentSpec.cpu.coresPerCpu')}>
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('tdp_w')} label={t('componentSpec.cpu.tdp')}>
        <InputNumber min={1} max={1000} />
      </Form.Item>
      <Form.Item name={name('architecture')} label={t('componentSpec.cpu.architecture')}>
        <Select options={[{ label: 'x86_64', value: 'x86_64' }, { label: 'ARM64', value: 'ARM64' }]} />
      </Form.Item>
      <Form.Item name={name('base_freq_ghz')} label={t('componentSpec.cpu.baseFreq')}>
        <InputNumber min={0} step={0.1} />
      </Form.Item>
      <Form.Item name={name('boost_freq_ghz')} label={t('componentSpec.cpu.boostFreq')}>
        <InputNumber min={0} step={0.1} />
      </Form.Item>
    </>
  );
}

export function MemorySpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const { t } = useTranslation('settings');
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('capacity_gb')} label={t('componentSpec.memory.capacity')}>
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('speed_mhz')} label={t('componentSpec.memory.speed')}>
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('type')} label={t('componentSpec.memory.type')}>
        <Select options={[{ label: 'DDR4', value: 'DDR4' }, { label: 'DDR5', value: 'DDR5' }, { label: 'LPDDR5', value: 'LPDDR5' }]} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label={t('componentSpec.memory.formFactor')}>
        <Select options={[{ label: 'RDIMM', value: 'RDIMM' }, { label: 'UDIMM', value: 'UDIMM' }, { label: 'SO-DIMM', value: 'SO-DIMM' }]} />
      </Form.Item>
      <Form.Item name={name('ecc')} label={t('componentSpec.memory.ecc')}>
        <Select options={[{ label: t('componentSpec.yes'), value: true }, { label: t('componentSpec.no'), value: false }]} />
      </Form.Item>
    </>
  );
}

export function DiskSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const { t } = useTranslation('settings');
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('storage_type')} label={t('componentSpec.disk.storageType')}>
        <Select options={[{ label: 'SSD', value: 'SSD' }, { label: 'HDD', value: 'HDD' }, { label: 'NVMe', value: 'NVMe' }]} />
      </Form.Item>
      <Form.Item name={name('capacity_gb')} label={t('componentSpec.disk.capacity')}>
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('interface_type')} label={t('componentSpec.disk.interfaceType')}>
        <Select options={[{ label: 'NVMe', value: 'NVMe' }, { label: 'SATA', value: 'SATA' }, { label: 'SAS', value: 'SAS' }]} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label={t('componentSpec.disk.formFactor')}>
        <Select options={[{ label: '2.5"', value: '2.5"' }, { label: '3.5"', value: '3.5"' }]} />
      </Form.Item>
      <Form.Item name={name('endurance_tbw')} label={t('componentSpec.disk.tbw')}>
        <InputNumber min={0} />
      </Form.Item>
    </>
  );
}

export function NicSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const { t } = useTranslation('settings');
  const name = (field: string) => prefix ? [...prefix, field] : field;
  const portTypeOptions = NIC_PORT_TYPES.map(({ key, value }) => ({
    label: t(`componentSpec.nic.portTypeOption.${key}`),
    value
  }));
  return (
    <>
      <Form.Item name={name('port_count')} label={t('componentSpec.nic.portCount')}>
        <InputNumber min={1} max={16} />
      </Form.Item>
      <Form.Item name={name('port_type')} label={t('componentSpec.nic.portType')}>
        <Select options={portTypeOptions} />
      </Form.Item>
      <Form.Item name={name('port_speed')} label={t('componentSpec.nic.portSpeed')}>
        <Select options={['100M', '1G', '10G', '25G', '40G', '100G', '400G'].map(v => ({ label: v, value: v }))} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label={t('componentSpec.nic.formFactor')}>
        <Select options={[{ label: 'PCIe', value: 'PCIe' }, { label: 'OCP', value: 'OCP' }, { label: 'Mezzanine', value: 'Mezzanine' }, { label: 'Onboard', value: 'Onboard' }]} />
      </Form.Item>
    </>
  );
}

export function GpuSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const { t } = useTranslation('settings');
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('vram_gb')} label={t('componentSpec.gpu.vram')}>
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('gpu_memory_type')} label={t('componentSpec.gpu.memoryType')}>
        <Select options={[
          { label: 'HBM3e', value: 'HBM3e' },
          { label: 'HBM3', value: 'HBM3' },
          { label: 'HBM2e', value: 'HBM2e' },
          { label: 'GDDR6X', value: 'GDDR6X' },
          { label: 'GDDR6', value: 'GDDR6' },
          { label: 'LPDDR5', value: 'LPDDR5' },
          { label: 'LPDDR4X', value: 'LPDDR4X' },
        ]} />
      </Form.Item>
      <Form.Item name={name('cuda_cores')} label={t('componentSpec.gpu.cudaCores')}>
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('tdp_w')} label={t('componentSpec.gpu.tdp')}>
        <InputNumber min={1} max={1200} />
      </Form.Item>
      <Form.Item name={name('interface')} label={t('componentSpec.gpu.interface')}>
        <Select options={[
          { label: 'PCIe 5.0', value: 'PCIe 5.0' },
          { label: 'PCIe 4.0', value: 'PCIe 4.0' },
          { label: 'PCIe 3.0', value: 'PCIe 3.0' },
          { label: 'SXM5', value: 'SXM5' },
          { label: 'SXM4', value: 'SXM4' },
          { label: 'OAM', value: 'OAM' },
        ]} />
      </Form.Item>
      <Form.Item name={name('fp32_tflops')} label={t('componentSpec.gpu.fp32')}>
        <InputNumber min={0} step={0.1} />
      </Form.Item>
    </>
  );
}
