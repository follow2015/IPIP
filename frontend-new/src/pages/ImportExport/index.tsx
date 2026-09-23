/**
 * 导入导出页面
 * - 数据导入：选择类型 → 下载模板 → 上传文件 → 查看结果
 * - 数据导出：选择类型 → 可选过滤条件 → 导出 Excel
 */
import { useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import {
  Tabs,
  Card,
  Upload,
  Button,
  Select,
  Space,
  Alert,
  Typography,
  Steps,
  Table,
  Tag,
  Divider,
  Row,
  Col,
  InputNumber
} from 'antd';
import {
  UploadOutlined,
  DownloadOutlined,
  ExportOutlined,
  InboxOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileExcelOutlined
} from '@ant-design/icons';
import { useDownloadTemplate, useImportData, useExportData } from '@/services/import-export';
import { useMessage } from '@/hooks/useMessage';
import { ImportExportType, DeviceType } from '@/types/enums';

const { Text, Title } = Typography;

type ImportExportT = TFunction<'device'>;
type CommonT = TFunction<'common'>;

function getTypeOptions(td: ImportExportT, tc: CommonT) {
  return [
    { label: td('importExport.type.device'), value: ImportExportType.DEVICE },
    { label: tc('field.customer'), value: ImportExportType.CUSTOMER },
    { label: td('field.cabinet'), value: ImportExportType.CABINET }
  ];
}

function getTypeLabel(type: ImportExportType, td: ImportExportT, tc: CommonT): string {
  switch (type) {
    case ImportExportType.CUSTOMER:
      return tc('field.customer');
    case ImportExportType.CABINET:
      return td('field.cabinet');
    default:
      return td('importExport.type.device');
  }
}

function getTypeNameLabel(type: ImportExportType, td: ImportExportT): string {
  switch (type) {
    case ImportExportType.CUSTOMER:
      return td('customer.field.name');
    case ImportExportType.CABINET:
      return td('cabinet.form.name');
    default:
      return td('field.name');
  }
}

function getCsvHeaders(td: ImportExportT) {
  return {
    cpu: td('importExport.template.header.cpuTemplateId'),
    memory: td('importExport.template.header.memoryTemplateId'),
    storage: td('importExport.template.header.storageTemplateId'),
    nic: td('importExport.template.header.nicTemplateId')
  };
}

function getDeviceTemplateOptions(td: ImportExportT) {
  const headers = getCsvHeaders(td);
  return [
    {
      label: td('deviceType.SERVER'),
      value: DeviceType.SERVER,
      desc: td('importExport.template.server.desc', { cpu: headers.cpu, mem: headers.memory })
    },
    {
      label: td('deviceType.NETWORK'),
      value: DeviceType.NETWORK,
      desc: td('importExport.template.network.desc')
    },
    {
      label: td('deviceType.OTHER'),
      value: DeviceType.OTHER,
      desc: td('importExport.template.other.desc')
    }
  ];
}

interface FailedRowDetail {
  row: number;
  name?: string;
  error?: string;
}


function ImportPanel() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const message = useMessage();
  const [importType, setImportType] = useState<ImportExportType>(ImportExportType.DEVICE);
  const [deviceTemplateType, setDeviceTemplateType] = useState<DeviceType>(DeviceType.SERVER);
  const [fileList, setFileList] = useState<File[]>([]);
  const [importResult, setImportResult] = useState<{
    imported_count: number;
    failed_count: number;
    failed_rows: FailedRowDetail[];
  } | null>(null);

  const downloadTemplate = useDownloadTemplate();
  const importData = useImportData();

  const isDevice = importType === ImportExportType.DEVICE;

  const typeOptions = getTypeOptions(td, tc);
  const deviceTemplateOptions = getDeviceTemplateOptions(td);
  const typeLabel = getTypeLabel(importType, td, tc);
  const csvHeaders = getCsvHeaders(td);

  const handleDownloadTemplate = async () => {
    try {
      const res = await downloadTemplate.mutateAsync({
        type: importType,
        deviceTemplateType: isDevice ? deviceTemplateType : undefined
      });
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const suffix = isDevice ? `_${deviceTemplateType}` : '';
      a.download = `${importType}${suffix}_template.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(td('importExport.message.templateDownloaded'));
    } catch {
      message.error(td('importExport.message.templateDownloadFailed'));
    }
  };

  const handleFileSelect = (file: File) => {
    setFileList([file]);
    setImportResult(null);
    return false; // 阻止自动上传
  };

  const handleImport = async () => {
    if (!fileList.length) return;
    try {
      const res = await importData.mutateAsync({ type: importType, file: fileList[0] });
      const result = res?.data?.data;
      if (result) {
        setImportResult(result);
        const { imported_count, failed_count } = result;
        if (failed_count > 0) {
          message.warning(
            td('importExport.message.importedWithFailed', {
              imported: imported_count,
              failed: failed_count
            })
          );
        } else {
          message.success(td('importExport.message.imported', { count: imported_count }));
        }
      } else {
        message.success(td('importExport.message.importDone'));
      }
    } catch {
      message.error(td('importExport.message.importFailed'));
    }
  };

  const handleReset = () => {
    setFileList([]);
    setImportResult(null);
  };

  const failedColumns = [
    { title: td('importExport.result.column.row'), dataIndex: 'row', key: 'row', width: 60 },
    {
      title: getTypeNameLabel(importType, td),
      dataIndex: 'name',
      key: 'name',
      width: 120,
      ellipsis: true
    },
    {
      title: td('importExport.result.column.errorReason'),
      dataIndex: 'error',
      key: 'error',
      render: (text: string) => (
        <Text type="danger" style={{ fontSize: 12, wordBreak: 'break-all' }}>
          {text}
        </Text>
      )
    }
  ];

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      {/* 上方：操作区(左) + 说明区(右)，等高 */}
      <Row gutter={24} align="stretch">
        <Col xs={24} lg={14}>
          <Card title={td('importExport.panel.importTitle')} styles={{ body: { padding: 24 } }}>
            <Steps
              orientation="vertical"
              size="small"
              current={importResult ? 3 : fileList.length ? 2 : 0}
              items={[
                {
                  title: td('importExport.step.selectType'),
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Select
                        options={typeOptions}
                        value={importType}
                        onChange={(v) => {
                          setImportType(v);
                          handleReset();
                        }}
                        style={{ width: 200 }}
                      />
                      {isDevice && (
                        <Select
                          options={deviceTemplateOptions.map((o) => ({
                            label: o.label,
                            value: o.value
                          }))}
                          value={deviceTemplateType}
                          onChange={setDeviceTemplateType}
                          style={{ width: 200 }}
                        />
                      )}
                    </Space>
                  )
                },
                {
                  title: td('importExport.step.downloadTemplate'),
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={handleDownloadTemplate}
                        loading={downloadTemplate.isPending}
                      >
                        {td('importExport.action.downloadTemplate', { type: typeLabel })}
                      </Button>
                      {isDevice && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {deviceTemplateOptions.find((o) => o.value === deviceTemplateType)?.desc}
                        </Text>
                      )}
                    </Space>
                  )
                },
                {
                  title: td('importExport.step.uploadFile'),
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      {fileList.length > 0 ? (
                        <Space>
                          <Tag icon={<FileExcelOutlined />} color="blue">
                            {fileList[0].name}
                          </Tag>
                          <Button size="small" onClick={handleReset}>
                            {td('importExport.action.reselect')}
                          </Button>
                        </Space>
                      ) : (
                        <Upload
                          beforeUpload={handleFileSelect}
                          accept=".xlsx,.xls,.csv"
                          showUploadList={false}
                          maxCount={1}
                        >
                          <Button icon={<UploadOutlined />}>
                            {td('importExport.action.selectFile')}
                          </Button>
                        </Upload>
                      )}
                      {fileList.length > 0 && !importResult && (
                        <Button
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          onClick={handleImport}
                          loading={importData.isPending}
                        >
                          {td('importExport.action.startImport')}
                        </Button>
                      )}
                    </Space>
                  )
                }
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title={td('importExport.guide.title')} size="small" styles={{ body: { padding: 16 } }}>
            <Space orientation="vertical" style={{ width: '100%' }} size="small">
              <Text>{td('importExport.guide.step1')}</Text>
              <Text>{td('importExport.guide.step2')}</Text>
              <Text>{td('importExport.guide.step3')}</Text>
              <Divider style={{ margin: '8px 0' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {td('importExport.guide.supportedFormats')}
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {td('importExport.guide.keepHeader')}
              </Text>
              {isDevice && (
                <>
                  <Divider style={{ margin: '8px 0' }} />
                  <Text strong style={{ fontSize: 12 }}>
                    {td('importExport.guide.deviceTemplateTitle')}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="blue">{td('deviceType.SERVER')}</Tag>{' '}
                    {td('importExport.template.server.hardwareByTemplate')}
                  </Text>
                  <Text type="danger" style={{ fontSize: 12 }}>
                    {td('importExport.template.cpuMemoryRequired', {
                      cpu: csvHeaders.cpu,
                      mem: csvHeaders.memory
                    })}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {td('importExport.template.storageNicOptional', {
                      storage: csvHeaders.storage,
                      nic: csvHeaders.nic
                    })}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="green">{td('deviceType.NETWORK')}</Tag>{' '}
                    {td('importExport.template.network.desc')}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="orange">{td('deviceType.OTHER')}</Tag>{' '}
                    {td('importExport.template.other.desc')}
                  </Text>
                </>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 导入结果（下方全宽） */}
      {importResult && (
        <Card title={td('importExport.result.title')} styles={{ body: { padding: 16 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col xs={12} md={6}>
                <Card size="small" styles={{ body: { textAlign: 'center', padding: '12px 0' } }}>
                  <Title level={3} style={{ color: '#52c41a', margin: 0 }}>
                    {importResult.imported_count}
                  </Title>
                  <Text type="secondary">{td('importExport.result.success')}</Text>
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card size="small" styles={{ body: { textAlign: 'center', padding: '12px 0' } }}>
                  <Title
                    level={3}
                    style={{
                      color: importResult.failed_count > 0 ? '#ff4d4f' : '#52c41a',
                      margin: 0
                    }}
                  >
                    {importResult.failed_count}
                  </Title>
                  <Text type="secondary">{td('importExport.result.failed')}</Text>
                </Card>
              </Col>
            </Row>
            {importResult.failed_rows?.length > 0 && (
              <Table
                columns={failedColumns}
                dataSource={importResult.failed_rows.map((r, i) => ({ ...r, key: i }))}
                size="small"
                pagination={{ pageSize: 10, size: 'small' }}
                scroll={{ x: 'max-content' }}
              />
            )}
            <Button onClick={handleReset}>{td('importExport.action.continueImport')}</Button>
          </Space>
        </Card>
      )}
    </Space>
  );
}


function ExportPanel() {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const message = useMessage();
  const [exportType, setExportType] = useState<ImportExportType>(ImportExportType.DEVICE);
  const [cabinetId, setCabinetId] = useState<number | null>(null);
  const [customerId, setCustomerId] = useState<number | null>(null);

  const exportData = useExportData();

  const isDevice = exportType === ImportExportType.DEVICE;

  const typeOptions = getTypeOptions(td, tc);
  const typeLabel = getTypeLabel(exportType, td, tc);

  const handleExport = async () => {
    try {
      const params: Record<string, unknown> = {};
      if (isDevice) {
        if (cabinetId) params.cabinet_id = cabinetId;
        if (customerId) params.customer_id = customerId;
      }
      const res = await exportData.mutateAsync({ type: exportType, params });
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const timestamp = new Date().toISOString().slice(0, 10);
      a.download = `${exportType}_export_${timestamp}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(td('importExport.message.exportSuccess'));
    } catch {
      message.error(td('importExport.message.exportFailed'));
    }
  };

  return (
    <Row gutter={24}>
      <Col xs={24} lg={14}>
        <Card title={td('importExport.panel.exportTitle')} styles={{ body: { padding: 24 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="large">
            {/* 数据类型选择 */}
            <div>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                {td('importExport.step.selectType')}
              </Text>
              <Select
                options={typeOptions}
                value={exportType}
                onChange={(v) => {
                  setExportType(v);
                  setCabinetId(null);
                  setCustomerId(null);
                }}
                style={{ width: 200 }}
              />
            </div>

            {/* 设备导出过滤条件 */}
            {isDevice && (
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                  {td('importExport.export.filterTitle')}
                </Text>
                <Space>
                  <Space.Compact>
                    <Text style={{ lineHeight: '32px' }}>{td('importExport.export.cabinetId')}</Text>
                    <InputNumber
                      placeholder={td('importExport.export.all')}
                      value={cabinetId}
                      onChange={setCabinetId}
                      min={1}
                      style={{ width: 120 }}
                    />
                  </Space.Compact>
                  <Space.Compact>
                    <Text style={{ lineHeight: '32px' }}>
                      {td('importExport.export.customerId')}
                    </Text>
                    <InputNumber
                      placeholder={td('importExport.export.all')}
                      value={customerId}
                      onChange={setCustomerId}
                      min={1}
                      style={{ width: 120 }}
                    />
                  </Space.Compact>
                </Space>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {td('importExport.export.noFilterHint')}
                </Text>
              </div>
            )}

            {/* 导出按钮 */}
            <Button
              type="primary"
              icon={<ExportOutlined />}
              onClick={handleExport}
              loading={exportData.isPending}
              size="large"
            >
              {td('importExport.action.exportData', { type: typeLabel })}
            </Button>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={10}>
        <Card title={td('importExport.export.guideTitle')} size="small" styles={{ body: { padding: 16 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="small">
            <Text>{td('importExport.export.excelFormat')}</Text>
            {isDevice && (
              <>
                <Divider style={{ margin: '8px 0' }} />
                <Text strong>{td('importExport.export.deviceFilterTitle')}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {td('importExport.export.filterByCabinet')}
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {td('importExport.export.filterByCustomer')}
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {td('importExport.export.filterBoth')}
                </Text>
              </>
            )}
          </Space>
        </Card>
      </Col>
    </Row>
  );
}


function ImportExport() {
  const { t: td } = useTranslation('device');
  return (
    <Tabs
      defaultActiveKey="import"
      items={[
        {
          key: 'import',
          label: (
            <Space>
              <UploadOutlined />
              {td('importExport.tab.import')}
            </Space>
          ),
          children: <ImportPanel />
        },
        {
          key: 'export',
          label: (
            <Space>
              <ExportOutlined />
              {td('importExport.tab.export')}
            </Space>
          ),
          children: <ExportPanel />
        }
      ]}
    />
  );
}

export default ImportExport;
