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
import { useTranslation } from 'react-i18next';

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

/**
 * 生命周期联动：下线日期 ↔ 预计使用年限。
 * anchor 取「上线日期」，未设置时回退为今天。
 * - 仅一项有值：推断另一项（年限四舍五入取整，并据此修正日期保持一致）。
 * - 两项都有：取更久的一方；年限取整后同步修改下线日期。
 */
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

/**
 * 上线日期变化（含清空）后，以下线日期/预计使用年限为基准，按新的锚点重新推算另一项。
 * 锚点取「上线日期」，未设置时回退为「当天编辑/提交时间」(dayjs())。
 * - 两项都有：取更久的一方，年限取整后同步修改下线日期。
 * - 仅一项有值：推断另一项（年限四舍五入取整并据此修正日期）。
 * - 两项都无：不处理。
 */
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
  const { t } = useTranslation('asset');
  return (
    <DatePicker
      style={{ width: '100%' }}
      placeholder={t('assetInfo.onlineDate.placeholder')}
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
  const { t } = useTranslation('asset');
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
        placeholder={t('assetInfo.warrantyEnd.placeholder')}
        value={value ?? null}
        onChange={(d) => onChange?.(d)}
      />
      <Popover
        trigger="click"
        open={popOpen}
        onOpenChange={setPopOpen}
        title={t('assetInfo.warrantyEnd.popoverTitle')}
        content={
          <Space wrap>
            {[1, 2, 3, 5].map((y) => (
              <Button key={y} size="small" onClick={() => quick(y)}>
                {t('assetInfo.warrantyEnd.quickYear', { count: y })}
              </Button>
            ))}
          </Space>
        }
      >
        <Button>{t('assetInfo.warrantyEnd.quick')}</Button>
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
  const { t } = useTranslation('asset');
  return (
    <DatePicker
      style={{ width: '100%' }}
      placeholder={t('assetInfo.offlineDate.placeholder')}
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
  const { t } = useTranslation('asset');
  return (
    <InputNumber
      min={1}
      max={30}
      precision={0}
      style={{ width: '100%' }}
      placeholder={t('assetInfo.lifecycleYears.placeholder')}
      addonAfter={t('assetInfo.lifecycleYears.unit')}
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
  const { t } = useTranslation('asset');
  if (mode === 'none') return null;
  const name = (key: string) => buildName(prefix, key);

  if (mode === 'auto-only') {
    return (
      <Row gutter={16} align="middle">
        <Col xs={24} md={16}>
          <Form.Item
            label={t('assetInfo.autoGenerate.label')}
            tooltip={t('assetInfo.autoGenerate.tooltip')}
          >
            <Switch
              checkedChildren={t('assetInfo.autoGenerate.on')}
              unCheckedChildren={t('assetInfo.autoGenerate.off')}
              checked={autoGenerate}
              onChange={onAutoGenerateChange}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8} style={{ paddingTop: 4 }}>
          {autoGenerate && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {t('assetInfo.autoGenerate.hintBatch')}
            </span>
          )}
        </Col>
      </Row>
    );
  }

  if (mode === 'manual-with-switch') {
    return (
      <Row gutter={16} align="middle">
        <Col xs={24} md={16}>
          <Form.Item
            name={name('asset_number')}
            label={t('assetInfo.assetNumber.label')}
            tooltip={t('assetInfo.assetNumber.tooltip')}
          >
            <Input
              placeholder={t('assetInfo.assetNumber.placeholderManual')}
              disabled={autoGenerate}
              addonAfter={
                <Switch
                  checkedChildren={t('assetInfo.autoGenerate.auto')}
                  unCheckedChildren={t('assetInfo.autoGenerate.manual')}
                  checked={autoGenerate}
                  onChange={onAutoGenerateChange}
                  size="small"
                />
              }
              addonBefore={<ThunderboltOutlined />}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8} style={{ paddingTop: 30 }}>
          {autoGenerate && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {t('assetInfo.autoGenerate.hint')}
            </span>
          )}
        </Col>
      </Row>
    );
  }

  return (
    <Row gutter={16}>
      <Col xs={24} md={16}>
        <Form.Item name={name('asset_number')} label={t('assetInfo.assetNumber.label')}>
          <Input
            placeholder={t('assetInfo.assetNumber.placeholder')}
            addonAfter={
              <Button
                type="text"
                size="small"
                icon={<ThunderboltOutlined />}
                onClick={() => form.setFieldValue(name('asset_number'), generateAssetNumber())}
                title={t('assetInfo.assetNumber.autoGenerate')}
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
  const { t } = useTranslation('asset');
  const name = (key: string) => buildName(prefix, key);

  return (
    <>
      {/* 资产编号 */}
      <Divider plain>{t('assetInfo.assetNumber.label')}</Divider>
      <AssetNumberSection
        form={form}
        prefix={prefix}
        mode={assetNumberMode}
        autoGenerate={autoGenerate}
        onAutoGenerateChange={onAutoGenerateChange}
      />

      {/* 采购信息 */}
      <Divider plain>{t('assetInfo.section.purchase')}</Divider>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Form.Item name={name('supplier')} label={t('assetInfo.supplier.label')}>
            <Input placeholder={t('assetInfo.supplier.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item
            name={name('supplier_contact')}
            label={t('assetInfo.supplierContact.label')}
          >
            <Input placeholder={t('assetInfo.supplierContact.placeholder')} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Form.Item name={name('contract_number')} label={t('assetInfo.contractNumber.label')}>
            <Input placeholder={t('assetInfo.contractNumber.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name={name('invoice_number')} label={t('assetInfo.invoiceNumber.label')}>
            <Input placeholder={t('assetInfo.invoiceNumber.placeholder')} />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item name={name('purchase_date')} label={t('assetInfo.purchaseDate.label')}>
            <DatePicker
              style={{ width: '100%' }}
              placeholder={t('assetInfo.purchaseDate.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name={name('purchase_price')} label={t('assetInfo.purchasePrice.label')}>
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              placeholder={t('assetInfo.purchasePrice.placeholder')}
              precision={2}
            />
          </Form.Item>
        </Col>
      </Row>

      {/* 保修信息 */}
      <Divider plain>{t('assetInfo.section.warranty')}</Divider>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item name={name('warranty_type')} label={t('assetInfo.warrantyType.label')}>
            <Input placeholder={t('assetInfo.warrantyType.placeholder')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item name={name('warranty_start')} label={t('assetInfo.warrantyStart.label')}>
            <DatePicker
              style={{ width: '100%' }}
              placeholder={t('assetInfo.warrantyStart.placeholder')}
            />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={name('warranty_end')}
            label={t('assetInfo.warrantyEnd.label')}
            tooltip={t('assetInfo.warrantyEnd.tooltip')}
          >
            <WarrantyEndControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
      </Row>

      {/* 生命周期 */}
      <Divider plain>{t('assetInfo.section.lifecycle')}</Divider>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Form.Item
            name={name('online_date')}
            label={t('assetInfo.onlineDate.label')}
            tooltip={
              defaultOnlineDateNow
                ? t('assetInfo.onlineDate.tooltipDefault')
                : t('assetInfo.onlineDate.tooltip')
            }
            initialValue={defaultOnlineDateNow ? dayjs() : undefined}
          >
            <OnlineDateControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={name('offline_date')}
            label={t('assetInfo.offlineDate.label')}
            tooltip={t('assetInfo.offlineDate.tooltip')}
          >
            <LifecycleOfflineControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
        <Col xs={24} md={8}>
          <Form.Item
            name={name('lifecycle_years')}
            label={t('assetInfo.lifecycleYears.label')}
            tooltip={t('assetInfo.lifecycleYears.tooltip')}
          >
            <LifecycleYearsControl form={form} prefix={prefix} />
          </Form.Item>
        </Col>
      </Row>
    </>
  );
}
