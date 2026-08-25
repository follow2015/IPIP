/**
 * 导入导出页面
 * - 数据导入：选择类型 → 下载模板 → 上传文件 → 查看结果
 * - 数据导出：选择类型 → 可选过滤条件 → 导出 Excel
 */
import { useState } from 'react';
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

const TYPE_OPTIONS = [
  { label: '设备', value: ImportExportType.DEVICE },
  { label: '客户', value: ImportExportType.CUSTOMER },
  { label: '机柜', value: ImportExportType.CABINET }
];

const DEVICE_TEMPLATE_OPTIONS: { label: string; value: DeviceType; desc: string }[] = [
  {
    label: '服务器',
    value: DeviceType.SERVER,
    desc: '硬件配置必须通过配件模板ID指定，CPU/内存模板ID必填'
  },
  { label: '网络设备', value: DeviceType.NETWORK, desc: '含网管凭据、SSH配置、交换机拓扑字段' },
  { label: '其他设备', value: DeviceType.OTHER, desc: 'PDU、UPS等，仅基本信息+资产归属' }
];

const TYPE_LABEL: Record<ImportExportType, string> = {
  [ImportExportType.DEVICE]: '设备',
  [ImportExportType.CUSTOMER]: '客户',
  [ImportExportType.CABINET]: '机柜'
};

interface FailedRowDetail {
  row: number;
  name?: string;
  error?: string;
}


function ImportPanel() {
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
      message.success('模板下载成功');
    } catch {
      message.error('下载模板失败');
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
          message.warning(`成功导入 ${imported_count} 条，${failed_count} 条失败`);
        } else {
          message.success(`成功导入 ${imported_count} 条数据`);
        }
      } else {
        message.success('导入完成');
      }
    } catch {
      message.error('导入失败，请检查文件格式是否与模板一致');
    }
  };

  const handleReset = () => {
    setFileList([]);
    setImportResult(null);
  };

  const failedColumns = [
    { title: '行号', dataIndex: 'row', key: 'row', width: 60 },
    {
      title: `${TYPE_LABEL[importType]}名称`,
      dataIndex: 'name',
      key: 'name',
      width: 120,
      ellipsis: true
    },
    {
      title: '错误原因',
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
          <Card title="导入操作" styles={{ body: { padding: 24 } }}>
            <Steps
              orientation="vertical"
              size="small"
              current={importResult ? 3 : fileList.length ? 2 : 0}
              items={[
                {
                  title: '选择数据类型',
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Select
                        options={TYPE_OPTIONS}
                        value={importType}
                        onChange={(v) => {
                          setImportType(v);
                          handleReset();
                        }}
                        style={{ width: 200 }}
                      />
                      {isDevice && (
                        <Select
                          options={DEVICE_TEMPLATE_OPTIONS.map((o) => ({
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
                  title: '下载模板并填写数据',
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={handleDownloadTemplate}
                        loading={downloadTemplate.isPending}
                      >
                        下载{TYPE_LABEL[importType]}导入模板
                      </Button>
                      {isDevice && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {
                            DEVICE_TEMPLATE_OPTIONS.find((o) => o.value === deviceTemplateType)
                              ?.desc
                          }
                        </Text>
                      )}
                    </Space>
                  )
                },
                {
                  title: '上传填写好的文件',
                  description: (
                    <Space orientation="vertical" style={{ width: '100%' }}>
                      {fileList.length > 0 ? (
                        <Space>
                          <Tag icon={<FileExcelOutlined />} color="blue">
                            {fileList[0].name}
                          </Tag>
                          <Button size="small" onClick={handleReset}>
                            重新选择
                          </Button>
                        </Space>
                      ) : (
                        <Upload
                          beforeUpload={handleFileSelect}
                          accept=".xlsx,.xls,.csv"
                          showUploadList={false}
                          maxCount={1}
                        >
                          <Button icon={<UploadOutlined />}>选择文件</Button>
                        </Upload>
                      )}
                      {fileList.length > 0 && !importResult && (
                        <Button
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          onClick={handleImport}
                          loading={importData.isPending}
                        >
                          开始导入
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
          <Card title="使用说明" size="small" styles={{ body: { padding: 16 } }}>
            <Space orientation="vertical" style={{ width: '100%' }} size="small">
              <Text>1. 选择要导入的数据类型</Text>
              <Text>2. 下载对应模板，按格式填写数据</Text>
              <Text>3. 上传填写好的文件，系统自动校验并导入</Text>
              <Divider style={{ margin: '8px 0' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                支持 .xlsx、.xls、.csv 格式
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                请勿修改模板表头，否则可能导致导入失败
              </Text>
              {isDevice && (
                <>
                  <Divider style={{ margin: '8px 0' }} />
                  <Text strong style={{ fontSize: 12 }}>
                    设备模板类型说明：
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="blue">服务器</Tag> 硬件配置必须通过配件模板ID指定
                  </Text>
                  <Text type="danger" style={{ fontSize: 12 }}>
                    CPU模板ID、内存模板ID 为必填项
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    存储模板ID、网卡模板ID 为选填，填写后自动创建对应子记录
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="green">网络设备</Tag> 含网管凭据、SSH配置、交换机拓扑字段
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <Tag color="orange">其他设备</Tag> PDU、UPS等，仅基本信息+资产归属
                  </Text>
                </>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 导入结果（下方全宽） */}
      {importResult && (
        <Card title="导入结果" styles={{ body: { padding: 16 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small" styles={{ body: { textAlign: 'center', padding: '12px 0' } }}>
                  <Title level={3} style={{ color: '#52c41a', margin: 0 }}>
                    {importResult.imported_count}
                  </Title>
                  <Text type="secondary">成功导入</Text>
                </Card>
              </Col>
              <Col span={6}>
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
                  <Text type="secondary">导入失败</Text>
                </Card>
              </Col>
            </Row>
            {importResult.failed_rows?.length > 0 && (
              <Table
                columns={failedColumns}
                dataSource={importResult.failed_rows.map((r, i) => ({ ...r, key: i }))}
                size="small"
                pagination={{ pageSize: 10, size: 'small' }}
              />
            )}
            <Button onClick={handleReset}>继续导入</Button>
          </Space>
        </Card>
      )}
    </Space>
  );
}


function ExportPanel() {
  const message = useMessage();
  const [exportType, setExportType] = useState<ImportExportType>(ImportExportType.DEVICE);
  const [cabinetId, setCabinetId] = useState<number | null>(null);
  const [customerId, setCustomerId] = useState<number | null>(null);

  const exportData = useExportData();

  const isDevice = exportType === ImportExportType.DEVICE;

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
      message.success('导出成功');
    } catch {
      message.error('导出失败');
    }
  };

  return (
    <Row gutter={24}>
      <Col xs={24} lg={14}>
        <Card title="导出操作" styles={{ body: { padding: 24 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="large">
            {/* 数据类型选择 */}
            <div>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                选择数据类型
              </Text>
              <Select
                options={TYPE_OPTIONS}
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
                  过滤条件（可选）
                </Text>
                <Space>
                  <Space.Compact>
                    <Text style={{ lineHeight: '32px' }}>机柜ID</Text>
                    <InputNumber
                      placeholder="全部"
                      value={cabinetId}
                      onChange={setCabinetId}
                      min={1}
                      style={{ width: 120 }}
                    />
                  </Space.Compact>
                  <Space.Compact>
                    <Text style={{ lineHeight: '32px' }}>客户ID</Text>
                    <InputNumber
                      placeholder="全部"
                      value={customerId}
                      onChange={setCustomerId}
                      min={1}
                      style={{ width: 120 }}
                    />
                  </Space.Compact>
                </Space>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  不填则导出全部数据
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
              导出{TYPE_LABEL[exportType]}数据
            </Button>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={10}>
        <Card title="导出说明" size="small" styles={{ body: { padding: 16 } }}>
          <Space orientation="vertical" style={{ width: '100%' }} size="small">
            <Text>导出数据为 Excel (.xlsx) 格式</Text>
            {isDevice && (
              <>
                <Divider style={{ margin: '8px 0' }} />
                <Text strong>设备导出支持按条件过滤：</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  - 指定机柜ID：仅导出该机柜下的设备
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  - 指定客户ID：仅导出归属该客户的设备
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  - 两个条件可同时使用
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
  return (
    <Tabs
      defaultActiveKey="import"
      items={[
        {
          key: 'import',
          label: (
            <Space>
              <UploadOutlined />
              数据导入
            </Space>
          ),
          children: <ImportPanel />
        },
        {
          key: 'export',
          label: (
            <Space>
              <ExportOutlined />
              数据导出
            </Space>
          ),
          children: <ExportPanel />
        }
      ]}
    />
  );
}

export default ImportExport;
