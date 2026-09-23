/**
 * BatchAddTab — 手动批量添加设备（组合根）
 *
 * 从原 AddDevicesModal 拆出（原 Tab 1）。本文件仅负责编排渲染：
 * 公共字段区 + 模式分支区块 + 行编辑表格 + 提交区 + 结果弹窗。
 * 全部状态与提交逻辑下沉到 useBatchAddTab，纯函数落在 buildCreateRequests / conflictCheck。
 */

import React from 'react';
import { Form, Select, InputNumber, Button, Space, Alert, Card, Checkbox } from 'antd';
import { PlusOutlined, AimOutlined, ThunderboltOutlined } from '@ant-design/icons';
import HardwareConfigFields from '@/components/HardwareConfigFields';
import NicConfigFields from '@/components/NicConfigFields';
import BatchResultModal from '../../BatchResultModal';
import { getTypeOptions } from '../shared';
import { useTranslation } from 'react-i18next';
import { useBatchAddTab } from './useBatchAddTab';
import BatchDeviceTable from './BatchDeviceTable';
import ChassisConfigPanel from './ChassisConfigPanel';
import PortGeneratePanel from './PortGeneratePanel';

interface BatchAddTabProps {
  active: boolean;
  onClose: (refresh?: boolean) => void;
}

const BatchAddTab: React.FC<BatchAddTabProps> = ({ active, onClose }) => {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const tab = useBatchAddTab(active);
  const {
    form,
    deviceType,
    selectedRoomId,
    selectedCabinetId,
    isChassisMode,
    isNodeMode,
    isServerType,
    isNetworkType,
    isUnmanagedNetwork,
    subtypeOptions,
    roomOptions,
    cabinetOptions,
    chassisOptions,
    selectedChassis,
    availableUCount,
    availableUPositions,
    portPreview,
    freeNodeSlots,
    rows,
    selectedChassisId,
    addRowCount,
    setAddRowCount,
    uGap,
    setUGap,
    batchHeightU,
    setBatchHeightU,
    handleAddRow,
    handleAutoAssignU,
    handleRegenerateNames,
    handleBatchSetHeightU,
    handleChassisChange,
    handleSubmit,
    handleRetry,
    batchCreate
  } = tab;

  const handleResultClose = () => {
    batchCreate.closeResult();
    if (batchCreate.result && batchCreate.result.success_count > 0) onClose(true);
  };

  return (
    <>
      <Form form={form} layout="vertical" autoComplete="off">
        <Space size="middle" wrap style={{ marginBottom: 16 }}>
          <Form.Item
            name="device_type"
            label={t('form.basicInfo.mainType.label')}
            rules={[{ required: true, message: tCommon('message.selectRequired') }]}
            style={{ marginBottom: 0, minWidth: 160 }}
          >
            <Select placeholder={tCommon('message.selectRequired')} options={getTypeOptions(t)} />
          </Form.Item>
          <Form.Item
            name="device_subtype"
            label={t('basic.field.deviceSubtype')}
            style={{ marginBottom: 0, minWidth: 160 }}
          >
            <Select
              placeholder={tCommon('message.selectRequired')}
              options={subtypeOptions}
              allowClear
              disabled={!deviceType}
            />
          </Form.Item>
          <Form.Item
            name="room_id"
            label={t('basic.field.room')}
            style={{ marginBottom: 0, minWidth: 180 }}
          >
            <Select placeholder={t('form.select.room')} options={roomOptions} allowClear />
          </Form.Item>
          <Form.Item
            name="cabinet_id"
            label={t('form.location.cabinet.label')}
            style={{ marginBottom: 0, minWidth: 180 }}
          >
            <Select
              placeholder={selectedRoomId ? t('form.select.cabinet') : t('form.hint.selectRoomFirst')}
              options={cabinetOptions}
              allowClear
              disabled={!selectedRoomId}
            />
          </Form.Item>
          {selectedCabinetId && availableUPositions != null && !isNodeMode && (
            <span
              style={{ color: '#8c8c8c', fontSize: 12, alignSelf: 'flex-end', paddingBottom: 4 }}
            >
              {t('form.location.availableUPositions', { count: availableUCount })}
            </span>
          )}
          {isNodeMode && (
            <Form.Item
              label={t('form.nodeAssoc.chassis.label')}
              style={{ marginBottom: 0, minWidth: 220 }}
            >
              <Select
                placeholder={t('form.select.chassis')}
                options={chassisOptions}
                allowClear
                value={selectedChassisId}
                onChange={handleChassisChange}
              />
            </Form.Item>
          )}
          {isNodeMode && selectedChassisId && selectedChassis && (
            <span
              style={{ color: '#8c8c8c', fontSize: 12, alignSelf: 'flex-end', paddingBottom: 4 }}
            >
              {t('form.nodeAssoc.vacantCount', { count: freeNodeSlots })}
            </span>
          )}
        </Space>

        {/* ── 硬件配置区域（独立服务器 + 子节点） ── */}
        {isServerType && !isChassisMode && (
          <Card
            title={t('addModal.section.hardware')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <HardwareConfigFields form={form} />
          </Card>
        )}

        {/* ── 网卡配置区域（独立服务器 + 子节点） ── */}
        {isServerType && !isChassisMode && (
          <Card
            title={t('node.field.nic')}
            size="small"
            style={{ marginBottom: 12 }}
            styles={{ body: { paddingTop: 8, paddingBottom: 0 } }}
          >
            <NicConfigFields form={form} />
          </Card>
        )}

        {/* ── 机箱配置区域：生成子节点选项 ── */}
        {isChassisMode && <ChassisConfigPanel form={form} />}

        {/* ── 网络设备：管理权限开关 ── */}
        {isNetworkType && (
          <div style={{ marginBottom: 12 }}>
            <Form.Item
              name="has_ssh"
              label={t('form.network.managementAccess.label')}
              valuePropName="checked"
              initialValue={false}
              style={{ marginBottom: 8 }}
            >
              <Checkbox>{t('addModal.managedSwitch')}</Checkbox>
            </Form.Item>
          </div>
        )}

        {/* ── 端口生成区域（非网管型网络设备） ── */}
        {isUnmanagedNetwork && <PortGeneratePanel form={form} portPreview={portPreview} />}
      </Form>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Space wrap>
          <InputNumber
            size="small"
            min={1}
            max={50}
            value={addRowCount}
            onChange={(v) => setAddRowCount(v ?? 1)}
            style={{ width: 56 }}
          />
          <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={handleAddRow}>
            {t('addModal.row.add')}
          </Button>
          {!isNodeMode && (
            <InputNumber
              size="small"
              min={0}
              max={10}
              value={uGap}
              onChange={(v) => setUGap(v ?? 0)}
              style={{ width: 56 }}
              placeholder={t('form.location.deviceGap.placeholder')}
            />
          )}
          {!isNodeMode && (
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>{t('addModal.uGap')}</span>
          )}
          {!isNodeMode && (
            <InputNumber
              size="small"
              min={1}
              max={42}
              value={batchHeightU}
              onChange={(v) => setBatchHeightU(v ?? 1)}
              style={{ width: 56 }}
            />
          )}
          {!isNodeMode && (
            <Button size="small" onClick={handleBatchSetHeightU}>
              {t('addModal.action.setHeightU')}
            </Button>
          )}
          {!isNodeMode && (
            <Button
              size="small"
              icon={<AimOutlined />}
              disabled={!selectedCabinetId}
              onClick={handleAutoAssignU}
            >
              {t('form.location.uPosition.autoAssignTooltip')}
            </Button>
          )}
          {!isNodeMode && (
            <Button size="small" icon={<ThunderboltOutlined />} onClick={handleRegenerateNames}>
              {t('addModal.action.regenerateNames')}
            </Button>
          )}
        </Space>
        <span style={{ color: '#8c8c8c', fontSize: 12, lineHeight: '24px' }}>
          {t('addModal.row.count', { count: rows.length })}
        </span>
      </div>

      <BatchDeviceTable
        rows={rows}
        isChassisMode={isChassisMode}
        isNodeMode={isNodeMode}
        updateRow={tab.updateRow}
        copyRow={tab.copyRow}
        deleteRow={tab.deleteRow}
        genNodeName={tab.genNodeName}
      />

      {rows.length > 0 && !deviceType && (
        <Alert
          type="warning"
          title={t('addModal.hint.selectDeviceTypeFirst')}
          showIcon
          style={{ marginTop: 12 }}
        />
      )}
      {rows.length > 0 && deviceType && !selectedCabinetId && (
        <Alert
          type="info"
          title={t('addModal.hint.noCabinetUPosition')}
          showIcon
          style={{ marginTop: 12 }}
        />
      )}

      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Space>
          <Button onClick={() => onClose()}>{tCommon('action.cancel')}</Button>
          <Button
            type="primary"
            loading={batchCreate.isPending}
            disabled={!deviceType}
            onClick={handleSubmit}
          >
            {t('addModal.submitBatch', { count: rows.length })}
          </Button>
        </Space>
      </div>

      <BatchResultModal
        open={batchCreate.resultOpen}
        result={batchCreate.result}
        title={t('addModal.resultTitle')}
        onClose={handleResultClose}
        onRetry={handleRetry}
      />
    </>
  );
};

export default BatchAddTab;
