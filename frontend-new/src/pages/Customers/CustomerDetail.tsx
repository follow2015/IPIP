/**
 * 客户详情页（Card 布局，与交换机详情一致）
 * - Card(基本信息) + Card(资源统计)
 */
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Button, Descriptions, Spin, Result, message, Table, Tag } from 'antd';
import { ArrowLeftOutlined, DownloadOutlined } from '@ant-design/icons';
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

function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const customerId = Number(id);

  if (Number.isNaN(customerId)) {
    return (
      <Result
        status="404"
        title="参数无效"
        subTitle="客户 ID 无效"
        extra={<Button onClick={() => navigate(-1)}>返回</Button>}
      />
    );
  }

  return <CustomerDetailContent customerId={customerId} />;
}

function CustomerDetailContent({ customerId }: { customerId: number }) {
  const navigate = useNavigate();
  const { data: customer } = useCustomerSuspenseDetail(customerId);
  const { data: assetsData, isLoading: assetsLoading } = useCustomerAssets(customerId);
  const isTerminated = customer?.customer_status === CustomerStatusCode.TERMINATED;
  const { data: archives } = useTerminationArchives(customerId);

  if (!customer) {
    return <div>客户不存在</div>;
  }

  const s = assetsData?.summary;

  const handleExport = async () => {
    try {
      await exportCustomerAssets(customerId, customer.customer_name);
    } catch {
      message.error('导出失败');
    }
  };

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/customers')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      {/* 基本信息 Card */}
      <Card title={`客户详情 - ${customer.customer_name}`}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="客户名称">{customer.customer_name}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <StatusTag status={customer.customer_status} statusMap={CUSTOMER_STATUS_MAP} />
          </Descriptions.Item>
          <Descriptions.Item label="联系人">{customer.contact_person ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="联系电话">{customer.contact_phone ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{customer.email ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="地址">{customer.address ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>
            {customer.notes ?? '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 资源统计 Card */}
      <Card
        title="资源统计"
        style={{ marginTop: 16 }}
        extra={
          <Button icon={<DownloadOutlined />} onClick={handleExport} size="small">
            导出 Excel
          </Button>
        }
      >
        {assetsLoading ? (
          <Spin description="加载中..." />
        ) : assetsData ? (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="机房数">{s?.total_rooms ?? 0}</Descriptions.Item>
            <Descriptions.Item label="机柜数">{s?.total_cabinets ?? 0}</Descriptions.Item>
            <Descriptions.Item label="整柜租赁">{s?.full_cabinets ?? 0}</Descriptions.Item>
            <Descriptions.Item label="部分使用">{s?.partial_cabinets ?? 0}</Descriptions.Item>
            <Descriptions.Item label="设备数">{s?.total_devices ?? 0}</Descriptions.Item>
            <Descriptions.Item label="整柜设备">{s?.full_cabinet_devices ?? 0}</Descriptions.Item>
            <Descriptions.Item label="部分使用设备">
              {s?.partial_cabinet_devices ?? 0}
            </Descriptions.Item>
            <Descriptions.Item label="网段数">{s?.total_networks ?? 0}</Descriptions.Item>
            <Descriptions.Item label="整网段租赁">{s?.full_networks ?? 0}</Descriptions.Item>
            <Descriptions.Item label="IP总数">{s?.total_ips ?? 0}</Descriptions.Item>
          </Descriptions>
        ) : (
          <span>暂无数据</span>
        )}
      </Card>

      {/* 终止存档 Card（仅终止态客户显示） */}
      {isTerminated && (
        <Card title="终止存档" style={{ marginTop: 16 }}>
          {archives && archives.length > 0 ? (
            <Table
              size="small"
              rowKey="id"
              dataSource={archives}
              pagination={false}
              columns={[
                {
                  title: '终止时间',
                  dataIndex: 'created_at',
                  render: (v: string | null) => (v ? formatDateTime(v) : '-')
                },
                {
                  title: '操作人',
                  dataIndex: 'operator_name',
                  render: (v: string | null) => v ?? '-'
                },
                {
                  title: '终止原因',
                  dataIndex: 'reason',
                  render: (v: string | null) => v ?? '-'
                },
                {
                  title: 'PDF',
                  dataIndex: 'has_pdf',
                  render: (v: boolean) =>
                    v ? <Tag color="green">已生成</Tag> : <Tag color="orange">未生成</Tag>
                },
                {
                  title: '大小',
                  dataIndex: 'pdf_size',
                  render: (v: number | null) => (v != null ? `${(v / 1024).toFixed(1)} KB` : '-')
                },
                {
                  title: '操作',
                  key: 'action',
                  render: (_: unknown, r: (typeof archives)[number]) => (
                    <Button
                      type="link"
                      size="small"
                      icon={<DownloadOutlined />}
                      disabled={!r.has_pdf}
                      onClick={async () => {
                        try {
                          await downloadTerminationArchive(customerId, customer.customer_name);
                        } catch {
                          message.error('下载失败');
                        }
                      }}
                    >
                      下载
                    </Button>
                  )
                }
              ]}
            />
          ) : (
            <span>暂无终止存档</span>
          )}
        </Card>
      )}
    </div>
  );
}

export default CustomerDetail;
