/**
 * CloneTab — 克隆复制设备（组合根）
 *
 * 两步向导：选模板 → 配置差异项。
 * 状态与提交逻辑全部下沉到 useCloneTab，步骤渲染委托给 StepSource / StepEdit。
 */
import React from 'react';
import { Button, Space, Steps } from 'antd';
import { useCloneTab, type CloneTabProps } from './useCloneTab';
import StepSource from './StepSource';
import StepEdit from './StepEdit';
import BatchResultModal from '../../BatchResultModal';

const CloneTab: React.FC<CloneTabProps> = (props) => {
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
        items={[{ title: '选择模板' }, { title: '配置差异项' }]}
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
          <Button onClick={() => props.onClose()}>取消</Button>
          {step === 1 && <Button onClick={() => setStep(0)}>上一步</Button>}
          {step === 0 && (
            <Button
              type="primary"
              disabled={!templateId || isTemplateLoading || (isNodeTemplate && !cloneChassisId)}
              onClick={handleNext}
            >
              下一步
            </Button>
          )}
          {step === 1 && (
            <Button type="primary" loading={batchCreate.isPending} onClick={handleSubmit}>
              开始克隆（{diffRows.length} 台）
            </Button>
          )}
        </Space>
      </div>

      <BatchResultModal
        open={batchCreate.resultOpen}
        result={batchCreate.result}
        title="克隆设备结果"
        onClose={handleResultClose}
        onRetry={handleRetry}
      />
    </>
  );
};

export default CloneTab;
