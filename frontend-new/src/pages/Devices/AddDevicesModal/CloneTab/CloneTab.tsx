/**
 * CloneTab — 克隆复制设备（组合根）
 *
 * 两步向导：选模板 → 配置差异项。
 * 状态与提交逻辑全部下沉到 useCloneTab，步骤渲染委托给 StepSource / StepEdit。
 */
import React from 'react';
import { Button, Space, Steps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCloneTab, type CloneTabProps } from './useCloneTab';
import StepSource from './StepSource';
import StepEdit from './StepEdit';
import BatchResultModal from '../../BatchResultModal';

const CloneTab: React.FC<CloneTabProps> = (props) => {
  const { t } = useTranslation('device');
  const { t: tCommon } = useTranslation('common');
  const {
    step,
    setStep,
    templateId,
    setTemplateId,
    setSearchText,
    cloneCount,
    setCloneCount,
    targetCabinetId,
    setTargetCabinetId,
    templateDetail,
    isTemplateLoading,
    isChassisTemplate,
    isNodeTemplate,
    cloneChassisId,
    setCloneChassisId,
    cloneChassisOptions,
    cloneAvailablePositions,
    cabinetOptions,
    diffRows,
    availableUPositions,
    availableUCount,
    effectiveCabinetId,
    deviceSelectOptions,
    isDeviceListLoading,
    handleNext,
    handleAutoAssignU,
    handleRegenerateNames,
    handleSubmit,
    handleRetry,
    handleResultClose,
    diffColumns,
    batchCreate
  } = useCloneTab(props);

  return (
    <>
      <Steps
        current={step}
        size="small"
        items={[
          { title: t('addModal.clone.step.source') },
          { title: t('addModal.clone.step.edit') }
        ]}
        style={{ marginBottom: 24 }}
      />

      {step === 0 && (
        <StepSource
          templateId={templateId}
          setTemplateId={setTemplateId}
          setSearchText={setSearchText}
          cloneCount={cloneCount}
          setCloneCount={setCloneCount}
          targetCabinetId={targetCabinetId}
          setTargetCabinetId={setTargetCabinetId}
          isTemplateLoading={isTemplateLoading}
          isDeviceListLoading={isDeviceListLoading}
          deviceSelectOptions={deviceSelectOptions}
          templateDetail={templateDetail}
          isChassisTemplate={isChassisTemplate}
          isNodeTemplate={isNodeTemplate}
          cloneChassisId={cloneChassisId}
          setCloneChassisId={setCloneChassisId}
          cloneChassisOptions={cloneChassisOptions}
          cloneAvailablePositions={cloneAvailablePositions}
          cabinetOptions={cabinetOptions}
        />
      )}

      {step === 1 && (
        <StepEdit
          diffRows={diffRows}
          diffColumns={diffColumns}
          isNodeTemplate={isNodeTemplate}
          effectiveCabinetId={effectiveCabinetId}
          handleAutoAssignU={handleAutoAssignU}
          handleRegenerateNames={handleRegenerateNames}
          availableUPositions={availableUPositions}
          availableUCount={availableUCount}
          cloneChassisId={cloneChassisId}
          cloneAvailablePositions={cloneAvailablePositions}
        />
      )}

      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Space>
          <Button onClick={() => props.onClose()}>{tCommon('action.cancel')}</Button>
          {step === 1 && <Button onClick={() => setStep(0)}>{t('addModal.action.prev')}</Button>}
          {step === 0 && (
            <Button
              type="primary"
              disabled={!templateId || isTemplateLoading || (isNodeTemplate && !cloneChassisId)}
              onClick={handleNext}
            >
              {t('addModal.action.next')}
            </Button>
          )}
          {step === 1 && (
            <Button type="primary" loading={batchCreate.isPending} onClick={handleSubmit}>
              {t('addModal.clone.submit', { count: diffRows.length })}
            </Button>
          )}
        </Space>
      </div>

      <BatchResultModal
        open={batchCreate.resultOpen}
        result={batchCreate.result}
        title={t('addModal.clone.resultTitle')}
        onClose={handleResultClose}
        onRetry={handleRetry}
      />
    </>
  );
};

export default CloneTab;
