import { Modal, Row, Col, Card, Statistic, Spin } from 'antd';


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


export function IPStatsModal({ open, onClose, stats, scopeLabel }: IPStatsModalProps) {
  return (
    <Modal
      title="IP 状态统计"
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      {stats ? (
        <>
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card size="small">
                <Statistic title="总计" value={stats.total ?? 0} />
              </Card>
            </Col>
            {(
              [
                ['active', '活跃', '#52c41a'],
                ['inactive', '非活跃', '#8c8c8c'],
                ['blocked', '封禁', '#ff4d4f'],
                ['unused', '未使用', '#1890ff']
              ] as const
            ).map(([key, label, color]) => {
              const count = (stats[key] as number) ?? 0;
              const total = stats.total ?? 0;
              const percent = total > 0 ? Math.round((count / total) * 100) : 0;
              return (
                <Col span={6} key={key}>
                  <Card size="small">
                    <Statistic
                      title={label}
                      value={count}
                      suffix={
                        total > 0 ? (
                          <span style={{ fontSize: 14, color: '#999' }}>({percent}%)</span>
                        ) : undefined
                      }
                      styles={{ content: { color } }}
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
