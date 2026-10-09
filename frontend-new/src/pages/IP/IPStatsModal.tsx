import { Modal, Row, Col, Card, Statistic, Spin, theme } from 'antd';
import { useTranslation } from 'react-i18next';

interface IPStats {
  total?: number;
  active?: number;
  inactive?: number;
  blocked?: number;
  unused?: number;
}

interface IPStatsModalProps {
  open: boolean;
  onClose: () => void;
  stats?: IPStats;
  scopeLabel?: string;
}

type StatField = 'active' | 'inactive' | 'blocked' | 'unused';
type StatLabelKey =
  'ip.stats.active' | 'ip.stats.inactive' | 'ip.stats.blocked' | 'ip.stats.unused';

type SemanticColorKey = 'colorSuccess' | 'colorTextTertiary' | 'colorError' | 'colorPrimary';

const STAT_CARDS: {
  key: StatField;
  labelKey: StatLabelKey;
  color: SemanticColorKey;
}[] = [
  { key: 'active', labelKey: 'ip.stats.active', color: 'colorSuccess' },
  { key: 'inactive', labelKey: 'ip.stats.inactive', color: 'colorTextTertiary' },
  { key: 'blocked', labelKey: 'ip.stats.blocked', color: 'colorError' },
  { key: 'unused', labelKey: 'ip.stats.unused', color: 'colorPrimary' }
];

export function IPStatsModal({ open, onClose, stats, scopeLabel }: IPStatsModalProps) {
  const { t } = useTranslation('network');
  const { token } = theme.useToken();
  return (
    <Modal
      title={t('ip.stats.title')}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      {stats ? (
        <>
          <Row gutter={[16, 16]}>
            {/* 总计卡始终占满一行，与同 Row 内的 xs/md 写法保持一致 */}
            <Col xs={24}>
              <Card size="small">
                <Statistic title={t('ip.stats.total')} value={stats.total ?? 0} />
              </Card>
            </Col>
            {STAT_CARDS.map(({ key, labelKey, color }) => {
              const count = (stats[key] as number) ?? 0;
              const total = stats.total ?? 0;
              const percent = total > 0 ? Math.round((count / total) * 100) : 0;
              return (
                <Col xs={12} md={6} key={key}>
                  <Card size="small">
                    <Statistic
                      title={t(labelKey)}
                      value={count}
                      suffix={
                        total > 0 ? (
                          <span style={{ fontSize: 14, color: '#999' }}>({percent}%)</span>
                        ) : undefined
                      }
                      styles={{ content: { color: token[color] } }}
                    />
                  </Card>
                </Col>
              );
            })}
          </Row>
          {scopeLabel && (
            <div style={{ marginTop: 12, color: '#999', fontSize: 12 }}>{scopeLabel}</div>
          )}
        </>
      ) : (
        <Spin />
      )}
    </Modal>
  );
}
