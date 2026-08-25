/**
 * AddDevicesModal — 统一设备批量添加入口
 *
 * 架构说明
 * ────────
 * 统一入口：一个"批量添加"按钮 → AddDevicesModal，内部两个 Tab 切换（本文件，仅负责壳与路由）
 * 每个 Tab 拆分为独立文件，内部完全自治：
 *     • BatchAddTab.tsx  — 手动批量（表单公共字段 + 行内编辑表格）
 *     • CloneTab.tsx     — 克隆复制（两步向导：选模板 → 配置差异项）
 * CSV 导入已移至独立的导入导出模块，不再在此弹窗中提供。
 */

import React, { useState, useEffect } from 'react';
import { Modal, Tabs } from 'antd';

import BatchAddTab from './BatchAddTab';
import CloneTab from './CloneTab';


export interface AddDevicesModalProps {
  open: boolean;
  onClose: (refresh?: boolean) => void;
  templateDeviceId?: number;
  defaultTab?: 'batch' | 'clone';
}

/**
 * AddDevicesModal
 *
 * 统一的批量设备添加入口，整合手动批量、克隆复制两种方式。
 * CSV 导入已移至独立的导入导出模块。
 * 各 Tab 内部完全自治，通过 onClose(refresh?) 通知父组件刷新列表。
 */
const AddDevicesModal: React.FC<AddDevicesModalProps> = ({
  open,
  onClose,
  templateDeviceId,
  defaultTab = 'batch'
}) => {
  const [activeTab, setActiveTab] = useState<string>(defaultTab);

  useEffect(() => {
    if (open && templateDeviceId && templateDeviceId > 0) {
      setActiveTab('clone');
    }
  }, [open, templateDeviceId]);

  useEffect(() => {
    if (!open) setActiveTab(defaultTab);
  }, [open, defaultTab]);

  const tabItems = [
    {
      key: 'batch',
      label: '手动批量',
      children: <BatchAddTab active={open && activeTab === 'batch'} onClose={onClose} />
    },
    {
      key: 'clone',
      label: '克隆复制',
      children: (
        <CloneTab
          active={open && activeTab === 'clone'}
          templateDeviceId={templateDeviceId}
          onClose={onClose}
        />
      )
    }
  ];

  return (
    <Modal
      title="批量添加设备"
      open={open}
      onCancel={() => onClose()}
      width={1000}
      destroyOnHidden
      footer={null}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        destroyOnHidden={false}
      />
    </Modal>
  );
};

export default AddDevicesModal;
