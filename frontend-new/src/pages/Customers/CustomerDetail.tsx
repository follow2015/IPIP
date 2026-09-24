/**
 * 客户详情页（Card 布局，与交换机详情一致）
 * - Card(基本信息) + Card(资源统计)
 */
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Button, Descriptions, Spin, Result, Tag } from 'antd';
import { ArrowLeftOutlined, DownloadOutlined } from '@ant-design/icons';
import { useMessage } from '@/hooks/useMessage';
import {
  useCustomerSuspenseDetail,
  useCustomerAssets,
  exportCustomerAssets,
  useTerminationArchives,
  downloadTerminationArchive
} from '@/services/customer';
import { StatusTag } from '@/components/StatusTag';
import { CUSTOMER_STATUS_MAP, CustomerStatusCode } from '@/types/enums';
import { formatDateTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';
import DataTable from '@/components/DataTable';

function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const customerId = Number(id);

  if (Number.isNaN(customerId)) {
    return (
      <Result
        status="404"
        title={td('detail.invalidParam')}
        subTitle={td('customer.invalidId')}
        extra={<Button onClick={() => navigate(-1)}>{tc('action.back')}</Button>}
      />
    );
  }

  return <CustomerDetailContent customerId={customerId} />;
}

function CustomerDetailContent({ customerId }: { customerId: number }) {
  const { t: td } = useTranslation('device');
  const { t: tc } = useTranslation('common');
  const message = useMessage();
  const navigate = useNavigate();
  const { data: customer } = useCustomerSuspenseDetail(customerId);
  const { data: assetsData, isLoading: assetsLoading } = useCustomerAssets(customerId);
  const isTerminated = customer?.customer_status === CustomerStatusCode.TERMINATED;
  const { data: archives } = useTerminationArchives(customerId);

  if (!customer) {
    return <div>{td('customer.notFound')}</div>;
  }

  const s = assetsData?.summary;

  const handleExport = async () => {
    try {
      await exportCustomerAssets(customerId, customer.customer_name);
    } catch {
      message.error(td('customer.message.exportFailed'));
    }
  };

  const renderArchiveActions = (hasPdf: boolean) => (
    <Button
      type="link"
      size="small"
      icon={<DownloadOutlined />}
      disabled={!hasPdf}
      onClick={async () => {
        try {
          await downloadTerminationArchive(customerId, customer.customer_name);
        } catch {
          message.error(td('customer.message.downloadFailed'));
        }
      }}
    >
      {td('customer.archive.download')}
    </Button>
  );

  const renderArchiveCard = (a: NonNullable<typeof archives>[number]) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 12, color: '#999' }}>
        {a.created_at ? formatDateTime(a.created_at) : '-'}
      </div>
      <div>
        <span style={{ marginRight: 8 }}>{a.operator_name ?? '-'}</span>
        {a.has_pdf ? (
          <Tag color="green">{td('customer.archive.generated')}</Tag>
        ) : (
          <Tag color="orange">{td('customer.archive.notGenerated')}</Tag>
        )}
      </div>
      {a.reason && <div style={{ fontSize: 12 }}>{a.reason}</div>}
      <div style={{ fontSize: 12, color: '#999' }}>
        {a.pdf_size != null ? `${(a.pdf_size / 1024).toFixed(1)} KB` : '-'}
      </div>
      {renderArchiveActions(a.has_pdf)}
    </div>
  );

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/customers')}
        style={{ marginBottom: 16 }}
      >
        {td('detail.backToList')}
      </Button>

      {/* 基本信息 Card */}
      <Card title={td('customer.detailTitle', { name: customer.customer_name })}>
        <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
          <Descriptions.Item label={td('customer.field.name')}>
            {customer.customer_name}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.status')}>
            <StatusTag status={customer.customer_status} statusMap={CUSTOMER_STATUS_MAP} />
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.contactPerson')}>
            {customer.contact_person ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.contactPhone')}>
            {customer.contact_phone ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.email')}>
            {customer.email ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={td('customer.field.address')}>
            {customer.address ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label={tc('field.remarks')} span={2}>
            {customer.notes ?? '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 资源统计 Card */}
      <Card
        title={td('customer.resourceStats')}
        style={{ marginTop: 16 }}
        extra={
          <Button icon={<DownloadOutlined />} onClick={handleExport} size="small">
            {td('customer.exportExcel')}
          </Button>
        }
      >
        {assetsLoading ? (
          <Spin description={tc('message.loading')} />
        ) : assetsData ? (
          <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
            <Descriptions.Item label={td('customer.stats.roomCount')}>
              {s?.total_rooms ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.cabinetCount')}>
              {s?.total_cabinets ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.fullCabinets')}>
              {s?.full_cabinets ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.partialCabinets')}>
              {s?.partial_cabinets ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('cabinet.field.deviceCount')}>
              {s?.total_devices ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.fullCabinetDevices')}>
              {s?.full_cabinet_devices ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.partialCabinetDevices')}>
              {s?.partial_cabinet_devices ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.networkCount')}>
              {s?.total_networks ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.fullNetworks')}>
              {s?.full_networks ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label={td('customer.stats.ipTotal')}>
              {s?.total_ips ?? 0}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <span>{tc('message.noData')}</span>
        )}
      </Card>

      {/* 终止存档 Card（仅终止态客户显示） */}
      {isTerminated && (
        <Card title={td('customer.archive.title')} style={{ marginTop: 16 }}>
          {archives && archives.length > 0 ? (
            <DataTable
              size="small"
              rowKey="id"
              dataSource={archives}
              pagination={false}
              searchable={false}
              showCard={false}
              mobileCardMode
              cardRender={renderArchiveCard}
              columns={[
                {
                  title: td('customer.archive.terminatedAt'),
                  dataIndex: 'created_at',
                  render: (v: string | null) => (v ? formatDateTime(v) : '-')
                },
                {
                  title: td('customer.archive.operator'),
                  dataIndex: 'operator_name',
                  render: (v: string | null) => v ?? '-'
                },
                {
                  title: td('customer.archive.reason'),
                  dataIndex: 'reason',
                  render: (v: string | null) => v ?? '-'
                },
                {
                  title: 'PDF',
                  dataIndex: 'has_pdf',
                  render: (v: boolean) =>
                    v ? (
                      <Tag color="green">{td('customer.archive.generated')}</Tag>
                    ) : (
                      <Tag color="orange">{td('customer.archive.notGenerated')}</Tag>
                    )
                },
                {
                  title: td('customer.archive.size'),
                  dataIndex: 'pdf_size',
                  render: (v: number | null) => (v != null ? `${(v / 1024).toFixed(1)} KB` : '-')
                },
                {
                  title: tc('field.actions'),
                  key: 'action',
                  render: (_: unknown, r: NonNullable<typeof archives>[number]) =>
                    renderArchiveActions(r.has_pdf)
                }
              ]}
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <span>{td('customer.archive.empty')}</span>
          )}
        </Card>
      )}
    </div>
  );
}

export default CustomerDetail;
