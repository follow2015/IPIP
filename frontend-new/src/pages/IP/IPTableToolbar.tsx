import { Space, Button } from 'antd';
import { StopOutlined, ExportOutlined, BarChartOutlined, SearchOutlined } from '@ant-design/icons';
import FilterBar from '@/components/FilterBar';
import type { SelectOption } from '@/services';
import type { UseTableReturn } from '@/hooks/useTable';
import { IP_STATUS_MAP } from '@/types/enums';

interface IPTableToolbarProps {
  table: UseTableReturn;
  roomOptions: SelectOption[];
  customerOptions: SelectOption[];
  switchOptions: SelectOption[];
  scanNetworkPending: boolean;
  onOpenBatchBan: () => void;
  onOpenStats: () => void;
  onExport: () => void;
  onScanNetwork: () => void;
}

export function IPTableToolbar(props: IPTableToolbarProps) {
  const {
    table,
    roomOptions,
    customerOptions,
    switchOptions,
    scanNetworkPending,
    onOpenBatchBan,
    onOpenStats,
    onExport,
    onScanNetwork
  } = props;

  return (
    <Space wrap>
      <FilterBar
        filters={[
          {
            key: 'status',
            label: '按状态筛选',
            type: 'select',
            width: 140,
            options: Object.entries(IP_STATUS_MAP).map(([k, v]) => ({
              label: v.label,
              value: Number(k)
            }))
          },
          { key: 'room_id', label: '按机房筛选', type: 'select', options: roomOptions, width: 160 },
          {
            key: 'customer_id',
            label: '按客户筛选',
            type: 'select',
            options: customerOptions,
            width: 160
          },
          {
            key: 'switch_id',
            label: '按交换机筛选',
            type: 'select',
            options: switchOptions,
            width: 160
          }
        ]}
        table={table}
        extra={
          <>
            <Button icon={<ExportOutlined />} onClick={onExport}>
              导出CSV
            </Button>
            <Button icon={<StopOutlined />} danger onClick={onOpenBatchBan}>
              批量封禁
            </Button>
            <Button icon={<BarChartOutlined />} onClick={onOpenStats}>
              统计
            </Button>
            <Button icon={<SearchOutlined />} onClick={onScanNetwork} loading={scanNetworkPending}>
              扫描网段
            </Button>
          </>
        }
      />
    </Space>
  );
}

export default IPTableToolbar;
