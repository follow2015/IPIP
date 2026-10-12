import { Space, Button, Dropdown } from 'antd';
import {
  StopOutlined,
  ExportOutlined,
  BarChartOutlined,
  SearchOutlined,
  MoreOutlined
} from '@ant-design/icons';
import { useResponsive } from '@/hooks/useResponsive';
import FilterBar from '@/components/FilterBar';
import type { SelectOption } from '@/services';
import type { UseTableReturn } from '@/hooks/useTable';
import { getIPStatusOptions } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';

interface IPTableToolbarProps {
  table: UseTableReturn;
  roomOptions: SelectOption[];
  customerOptions: SelectOption[];
  switchOptions: SelectOption[];
  scanNetworkDisabled: boolean;
  onOpenBatchBan: () => void;
  onOpenStats: () => void;
  onExport: () => void;
  onScanNetwork: () => void;
}

export function IPTableToolbar(props: IPTableToolbarProps) {
  const { t: td } = useTranslation('device');
  const { t } = useTranslation('network');
  const { t: tc } = useTranslation('common');
  const { isMobile } = useResponsive();
  const {
    table,
    roomOptions,
    customerOptions,
    switchOptions,
    scanNetworkDisabled,
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
            label: t('ip.filter.byStatus'),
            type: 'select',
            width: 140,
            options: getIPStatusOptions(td)
          },
          {
            key: 'room_id',
            label: t('ip.filter.byRoom'),
            type: 'select',
            options: roomOptions,
            width: 160
          },
          {
            key: 'customer_id',
            label: t('ip.filter.byCustomer'),
            type: 'select',
            options: customerOptions,
            width: 160
          },
          {
            key: 'switch_id',
            label: t('ip.filter.bySwitch'),
            type: 'select',
            options: switchOptions,
            width: 160
          }
        ]}
        table={table}
        extra={
          isMobile ? (
            <>
              <Button
                icon={<SearchOutlined />}
                onClick={onScanNetwork}
                disabled={scanNetworkDisabled}
              >
                {t('ip.action.scanNetwork')}
              </Button>
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'export',
                      icon: <ExportOutlined />,
                      label: t('ip.action.exportCsv'),
                      onClick: onExport
                    },
                    {
                      key: 'ban',
                      icon: <StopOutlined />,
                      label: t('ip.action.batchBan'),
                      onClick: onOpenBatchBan
                    },
                    {
                      key: 'stats',
                      icon: <BarChartOutlined />,
                      label: t('ip.action.stats'),
                      onClick: onOpenStats
                    }
                  ]
                }}
              >
                <Button icon={<MoreOutlined />} aria-label={tc('action.more')} />
              </Dropdown>
            </>
          ) : (
            <>
              <Button icon={<ExportOutlined />} onClick={onExport}>
                {t('ip.action.exportCsv')}
              </Button>
              <Button icon={<StopOutlined />} danger onClick={onOpenBatchBan}>
                {t('ip.action.batchBan')}
              </Button>
              <Button icon={<BarChartOutlined />} onClick={onOpenStats}>
                {t('ip.action.stats')}
              </Button>
              <Button
                icon={<SearchOutlined />}
                onClick={onScanNetwork}
                disabled={scanNetworkDisabled}
              >
                {t('ip.action.scanNetwork')}
              </Button>
            </>
          )
        }
      />
    </Space>
  );
}

export default IPTableToolbar;
