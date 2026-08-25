/**
 * AssetInfoFields — 资产信息字段区块（共享组件）
 *
 * 统一设备添加（DeviceForm）、批量修改资产信息（BatchUpdateAssetModal）、
 * 详情页资产编辑（AssetTab）三处的资产字段集，确保字段一致、改一处全生效。
 *
 * 字段集（以详情编辑为准）：
 *   - 资产编号：asset_number（录入方式见 assetNumberMode）
 *   - 采购信息：supplier / supplier_contact / contract_number /
 *              purchase_date / purchase_price / invoice_number
 *   - 保修信息：warranty_type / warranty_start / warranty_end
 *   - 生命周期：online_date / offline_date / lifecycle_years
 *
 * 交互增强：
 *   - 保修到期：DatePicker 始终可手动选择；额外提供「快捷」按钮，点开 Popover 浮层
 *             内含 1/2/3/5 年快捷项，从「保修开始」自动推算到期日。
 *   - 生命周期：下线日期 ↔ 预计使用年限 双向联动。任一有值自动推断另一个并落库；
 *             两者都有时取更久的一方，年限四舍五入取整后同步对齐下线日期。
 *   - 上线日期：新增设备时默认填充为「设备添加时间」(now)，编辑/批量不默认；手动改则按手填值。
 *
 * 注意：设备级「备注(notes)」不属于资产字段，不在此组件内，由各调用方自行渲染。
 */

import { useState } from 'react';
import {
  Form,
  Input,
  InputNumber,
  DatePicker,
  Row,
  Col,
  Divider,
  Switch,
  Button,
  Space,
  Popover
} from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import dayjs, { Dayjs } from 'dayjs';


export function generateAssetNumber(prefix = 'ZC'): string {
  const now = new Date();
  const d = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const t = now.toTimeString().slice(0, 8).replace(/:/g, '');
  const r = Math.floor(Math.random() * 10000)
    .toString()
    .padStart(4, '0');
  return `${prefix}-${d}-${t}-${r}`;
}

export type AssetNumberMode = 'manual' | 'manual-with-switch' | 'auto-only' | 'none';

export interface AssetInfoFieldsProps {
  form: FormInstance;
  
  prefix?: string;
  
  assetNumberMode?: AssetNumberMode;
  
  autoGenerate?: boolean;
  
  onAutoGenerateChange?: (value: boolean) => void;
  
  defaultOnlineDateNow?: boolean;
}

type NamePath = (string | number)[];
const buildName = (prefix: string | undefined, key: string): NamePath =>
  prefix ? [prefix, key] : [key];

const toNumber = (v: unknown): number | null => {
  if (v == null || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isNaN(n) ? null : n;
};


function syncLifecycle(
  form: FormInstance,
  prefix: string | undefined,
  changed: 'offline' | 'years',
  val: Dayjs | number | null
) {
  const anchorRaw = form.getFieldValue(buildName(prefix, 'online_date'));
  const anchor = anchorRaw ? dayjs(anchorRaw) : dayjs();

  if (changed === 'offline') {
    const offline = val ? dayjs(val) : null;
    if (!offline) return;
    const years = toNumber(form.getFieldValue(buildName(prefix, 'lifecycle_years')));
    const span = offline.diff(anchor, 'day') / 365.25;
    if (years != null) {
      if (span >= years) {
        const rounded = Math.round(span);
        form.setFieldValue(buildName(prefix, 'lifecycle_years'), rounded);
        form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(rounded, 'year'));
      } else {
        form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(years, 'year'));
      }
    } else {
      const rounded = Math.round(span);
      form.setFieldValue(buildName(prefix, 'lifecycle_years'), rounded);
      form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(rounded, 'year'));
    }
    return;
  }

  
  const years = toNumber(val);
  if (years == null) return;
  const offlineRaw = form.getFieldValue(buildName(prefix, 'offline_date'));
  const offline = offlineRaw ? dayjs(offlineRaw) : null;
  if (offline) {
    const span = offline.diff(anchor, 'day') / 365.25;
    if (years >= span) {
      form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(years, 'year'));
    } else {
      const rounded = Math.round(span);
      form.setFieldValue(buildName(prefix, 'lifecycle_years'), rounded);
      form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(rounded, 'year'));
    }
  } else {
    form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(years, 'year'));
  }
}


function resyncLifecycle(form: FormInstance, prefix: string | undefined) {
  const anchorRaw = form.getFieldValue(buildName(prefix, 'online_date'));
  const anchor = anchorRaw ? dayjs(anchorRaw) : dayjs();
  const offlineRaw = form.getFieldValue(buildName(prefix, 'offline_date'));
  const offline = offlineRaw ? dayjs(offlineRaw) : null;
  const yearsRaw = toNumber(form.getFieldValue(buildName(prefix, 'lifecycle_years')));

  if (offline && yearsRaw != null) {
    const span = offline.diff(anchor, 'day') / 365.25;
    if (yearsRaw >= span) {
      form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(yearsRaw, 'year'));
    } else {
      const rounded = Math.round(span);
      form.setFieldValue(buildName(prefix, 'lifecycle_years'), rounded);
      form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(rounded, 'year'));
    }
  } else if (offline) {
    const span = offline.diff(anchor, 'day') / 365.25;
    const rounded = Math.round(span);
    form.setFieldValue(buildName(prefix, 'lifecycle_years'), rounded);
    form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(rounded, 'year'));
  } else if (yearsRaw != null) {
    form.setFieldValue(buildName(prefix, 'offline_date'), anchor.add(yearsRaw, 'year'));
  }
}


function OnlineDateControl({
  value,
  onChange,
  form,
  prefix
}: {
  value?: Dayjs | null;
  onChange?: (d: Dayjs | null) => void;
  form: FormInstance;
  prefix?: string;
}) {
  return (
    <DatePicker
      style={{ width: '100%' }}
      placeholder="上线投产日期"
      value={value ?? null}
      onChange={(d) => {
        onChange?.(d);
        resyncLifecycle(form, prefix);
      }}
    />
  );
}


function WarrantyEndControl({
  value,
  onChange,
  form,
  prefix
}: {
  value?: Dayjs | null;
  onChange?: (d: Dayjs | null) => void;
  form: FormInstance;
  prefix?: string;
}) {
  const [popOpen, setPopOpen] = useState(false);

  const quick = (y: number) => {
    const startRaw = form.getFieldValue(buildName(prefix, 'warranty_start'));
    const anchor = startRaw ? dayjs(startRaw) : dayjs();
    onChange?.(anchor.add(y, 'year'));
    setPopOpen(false);
  };

  return (
    <Space.Compact style={{ width: '100%' }}>
      <DatePicker
        style={{ flex: 1, minWidth: 0 }}
        placeholder="选择到期日"
        value={value ?? null}
        onChange={(d) => onChange?.(d)}
      />
      <Popover
        trigger="click"
        open={popOpen}
        onOpenChange={setPopOpen}
        title="从「保修开始」快速推算到期日"
        content={
          <Space wrap>
            {[1, 2, 3, 5].map((y) => (
              <Button key={y} size="small" onClick={() => quick(y)}>
                {y} 年
              </Button>
            ))}
          </Space>
        }
      >
        <Button>快捷</Button>
      </Popover>
    </Space.Compact>
  );
}


function LifecycleOfflineControl({
  value,
  onChange,
  form,
  prefix
}: {
  value?: Dayjs | null;
  onChange?: (d: Dayjs | null) => void;
  form: FormInstance;
  prefix?: string;
}) {
  return (
    <DatePicker
      style={{ width: '100%' }}
      placeholder="下线/报废日期"
      value={value ?? null}
      onChange={(d) => {
        onChange?.(d);
        syncLifecycle(form, prefix, 'offline', d);
      }}
    />
  );
}


function LifecycleYearsControl({
  value,
  onChange,
  form,
  prefix
}: {
  value?: number | null;
  onChange?: (v: number | null) => void;
  form: FormInstance;
  prefix?: string;
}) {
  return (
    <InputNumber
      min={1}
      max={30}
      precision={0}
      style={{ width: '100%' }}
      placeholder="年"
      addonAfter="年"
      value={value ?? null}
      onChange={(v) => {
        const n = toNumber(v);
        onChange?.(n);
        syncLifecycle(form, prefix, 'years', n);
      }}
    />
  );
}

function AssetNumberSection({
  form,
  prefix,
  mode,
  autoGenerate = false,
  onAutoGenerateChange
}: {
  form: FormInstance;
  prefix?: string;
  mode: AssetNumberMode;
  autoGenerate?: boolean;
  onAutoGenerateChange?: (value: boolean) => void;
}) {
  if (mode === 'none') return null;
  const name = (key: string) => buildName(prefix, key);

  
  if (mode === 'auto-only') {
    return (
      <Row gutter={16} align="middle">
        <Col span={16}>
          <Form.Item
            label="自动生成资产编号"
            tooltip="开启后，每个设备将获得不同的唯一编号（ZC-YYYYMMDD-HHmmss-XXXX）"
          >
            <Switch
              checkedChildren="开启"
              unCheckedChildren="关闭"
              checked={autoGenerate}
              onChange={onAutoGenerateChange}
            />
          </Form.Item>
        </Col>
        <Col span={8} style={{ paddingTop: 4 }}>
          {autoGenerate && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              将为每台设备自动生成唯一编号（ZC-YYYYMMDD-HHmmss-XXXX）
            </span>
          )}
        </Col>
      </Row>
    );
  }

  
  if (mode === 'manual-with-switch') {
    return (
      <Row gutter={16} align="middle">
        <Col span={16}>
          <Form.Item
            name={name('asset_number')}
            label="资产编号"
            tooltip="可手动输入，或开启自动生成"
          >
            <Input
              placeholder="手动输入资产编号"
              disabled={autoGenerate}
              addonAfter={
                <Switch
                  checkedChildren="自动"
                  unCheckedChildren="手动"
                  checked={autoGenerate}
                  onChange={onAutoGenerateChange}
                  size="small"
                />
              }
              addonBefore={<ThunderboltOutlined />}
            />
          </Form.Item>
        </Col>
        <Col span={8} style={{ paddingTop: 30 }}>
          {autoGenerate && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              将自动生成唯一编号（ZC-YYYYMMDD-HHmmss-XXXX）
            </span>
          )}
        </Col>
      </Row>
    );
  }

  
  return (
    <Row gutter={16}>
      <Col span={16}>
        <Form.Item name={name('asset_number')} label="资产编号">
          <Input
            placeholder="资产编号（可自动生成）"
            addonAfter={
              <Button
                type="text"
                size="small"
                icon={<ThunderboltOutlined />}
                onClick={() => form.setFieldValue(name('asset_number'), generateAssetNumber())}
                title="自动生成"
              />
            }
          />
        </Form.Item>
      </Col>
    </Row>
  );
}

export default function AssetInfoFields({
  form,
  prefix,
  assetNumberMode = 'manual-with-switch',
  autoGenerate = false,
  onAutoGenerateChange,
  defaultOnlineDateNow = false
}: AssetInfoFieldsProps) {
  const name = (key: string) => buildName(prefix, key);

  return (
    <>
      {}
      <Divider plain>资产编号</Divider>
      <AssetNumberSection
        form={form}
        prefix={prefix}
        mode={assetNumberMode}
        autoGenerate={autoGenerate}
        onAutoGenerateChange={onAutoGenerateChange}
      />

      {}
      <Divider plain>采购信息</Divider>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name={name('supplier')} label="供应商">
            <Input placeholder="供应商名称" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name={name('supplier_contact')} label="供应商联系人">
            <Input placeholder="联系人" />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name={name('contract_number')} label="合同编号">
            <Input placeholder="采购合同编号" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name={name('invoice_number')} label="发票号码">
            <Input placeholder="发票号码" />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name={name('purchase_date')} label="采购日期">
            <DatePicker style={{ width: '100%' }} placeholder="采购日期" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name={name('purchase_price')} label="采购价格(元)">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="价格" precision={2} />
          </Form.Item>
        </Col>
      </Row>

      {}
      <Divider plain>保修信息</Divider>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name={name('warranty_type')} label="保修类型">
            <Input placeholder="如：原厂保修" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name={name('warranty_start')} label="保修开始">
            <DatePicker style={{ width: '100%' }} placeholder="开始日期" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name={name('warranty_end')}
            label="保修到期"
            tooltip="可直接选择日期，或点右侧「快捷」按钮从「保修开始」按 1/2/3/5 年自动推算"
          >
            <WarrantyEndControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
      </Row>

      {}
      <Divider plain>生命周期</Divider>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item
            name={name('online_date')}
            label="上线日期"
            tooltip={
              defaultOnlineDateNow
                ? '默认填充为设备添加时间，可手动修改；清空后生命周期按编辑当天重新计算'
                : '清空后生命周期按编辑当天重新计算'
            }
            initialValue={defaultOnlineDateNow ? dayjs() : undefined}
          >
            <OnlineDateControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name={name('offline_date')}
            label="下线日期"
            tooltip="填写后将自动推算「预计使用年限」；两者都有时取更久的一方并同步对齐"
          >
            <LifecycleOfflineControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            name={name('lifecycle_years')}
            label="预计使用年限"
            tooltip="填写后将自动推算「下线日期」；两者都有时取更久的一方并同步对齐"
          >
            <LifecycleYearsControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
      </Row>
    </>
  );
}
