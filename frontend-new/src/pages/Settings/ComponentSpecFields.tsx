/**
 * 配件规格字段组件
 * - 四类配件（CPU / 内存 / 硬盘 / 网卡）的 spec 字段动态渲染
 * - 每个组件接收 prefix 参数，用于 Form.Item 的 name 前缀嵌套
 */
import { Form, InputNumber, Select, Input } from 'antd';


export function CpuSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('cores_per_cpu')} label="核数/颗">
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('tdp_w')} label="功耗 (W)">
        <InputNumber min={1} max={1000} />
      </Form.Item>
      <Form.Item name={name('architecture')} label="架构">
        <Select options={[{ label: 'x86_64', value: 'x86_64' }, { label: 'ARM64', value: 'ARM64' }]} />
      </Form.Item>
      <Form.Item name={name('base_freq_ghz')} label="基础频率 (GHz)">
        <InputNumber min={0} step={0.1} />
      </Form.Item>
      <Form.Item name={name('boost_freq_ghz')} label="Boost 频率 (GHz)">
        <InputNumber min={0} step={0.1} />
      </Form.Item>
    </>
  );
}


export function MemorySpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('capacity_gb')} label="单条容量 (GB)">
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('speed_mhz')} label="速率 (MHz)">
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('type')} label="类型">
        <Select options={[{ label: 'DDR4', value: 'DDR4' }, { label: 'DDR5', value: 'DDR5' }, { label: 'LPDDR5', value: 'LPDDR5' }]} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label="规格">
        <Select options={[{ label: 'RDIMM', value: 'RDIMM' }, { label: 'UDIMM', value: 'UDIMM' }, { label: 'SO-DIMM', value: 'SO-DIMM' }]} />
      </Form.Item>
      <Form.Item name={name('ecc')} label="ECC">
        <Select options={[{ label: '是', value: true }, { label: '否', value: false }]} />
      </Form.Item>
    </>
  );
}


export function DiskSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('storage_type')} label="存储类型">
        <Select options={[{ label: 'SSD', value: 'SSD' }, { label: 'HDD', value: 'HDD' }, { label: 'NVMe', value: 'NVMe' }]} />
      </Form.Item>
      <Form.Item name={name('capacity_gb')} label="容量 (GB)">
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('interface_type')} label="接口类型">
        <Select options={[{ label: 'NVMe', value: 'NVMe' }, { label: 'SATA', value: 'SATA' }, { label: 'SAS', value: 'SAS' }]} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label="规格">
        <Select options={[{ label: '2.5"', value: '2.5"' }, { label: '3.5"', value: '3.5"' }]} />
      </Form.Item>
      <Form.Item name={name('endurance_tbw')} label="TBW">
        <InputNumber min={0} />
      </Form.Item>
    </>
  );
}


export function NicSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('port_count')} label="端口数">
        <InputNumber min={1} max={16} />
      </Form.Item>
      <Form.Item name={name('port_type')} label="端口类型">
        <Select options={[
          { label: 'RJ45 (电口)', value: 'RJ45' },
          { label: 'SFP (1G光口)', value: 'SFP' },
          { label: 'SFP+ (10G光口)', value: 'SFP+' },
          { label: 'SFP28 (25G光口)', value: 'SFP28' },
          { label: 'QSFP+ (40G光口)', value: 'QSFP+' },
          { label: 'QSFP28 (100G光口)', value: 'QSFP28' },
          { label: 'QSFP56 (200G光口)', value: 'QSFP56' },
          { label: 'QSFP-DD (400G光口)', value: 'QSFP-DD' },
        ]} />
      </Form.Item>
      <Form.Item name={name('port_speed')} label="端口速率">
        <Select options={['100M', '1G', '10G', '25G', '40G', '100G', '400G'].map(v => ({ label: v, value: v }))} />
      </Form.Item>
      <Form.Item name={name('form_factor')} label="板型">
        <Select options={[{ label: 'PCIe', value: 'PCIe' }, { label: 'OCP', value: 'OCP' }, { label: 'Mezzanine', value: 'Mezzanine' }, { label: 'Onboard', value: 'Onboard' }]} />
      </Form.Item>
    </>
  );
}


export function GpuSpecFields({ prefix }: { prefix?: (string | number)[] }) {
  const name = (field: string) => prefix ? [...prefix, field] : field;
  return (
    <>
      <Form.Item name={name('vram_gb')} label="显存容量 (GB)">
        <InputNumber min={1} max={256} />
      </Form.Item>
      <Form.Item name={name('gpu_memory_type')} label="显存类型">
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
      <Form.Item name={name('cuda_cores')} label="CUDA核心数/计算单元">
        <InputNumber min={1} />
      </Form.Item>
      <Form.Item name={name('tdp_w')} label="功耗 (W)">
        <InputNumber min={1} max={1200} />
      </Form.Item>
      <Form.Item name={name('interface')} label="接口类型">
        <Select options={[
          { label: 'PCIe 5.0', value: 'PCIe 5.0' },
          { label: 'PCIe 4.0', value: 'PCIe 4.0' },
          { label: 'PCIe 3.0', value: 'PCIe 3.0' },
          { label: 'SXM5', value: 'SXM5' },
          { label: 'SXM4', value: 'SXM4' },
          { label: 'OAM', value: 'OAM' },
        ]} />
      </Form.Item>
      <Form.Item name={name('fp32_tflops')} label="FP32 算力 (TFLOPS)">
        <InputNumber min={0} step={0.1} />
      </Form.Item>
    </>
  );
}
