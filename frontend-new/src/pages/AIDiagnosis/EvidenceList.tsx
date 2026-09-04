import { List, Typography, Tag } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface EvidenceListProps {
  evidence: string[];
}

export default function EvidenceList({ evidence }: EvidenceListProps) {
  if (!evidence || evidence.length === 0) {
    return <Text type="secondary">暂无证据</Text>;
  }
  return (
    <List
      size="small"
      dataSource={evidence}
      renderItem={(item, idx) => (
        <List.Item>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, width: '100%' }}>
            <CheckCircleOutlined style={{ color: '#52c41a', marginTop: 4 }} />
            <Text style={{ flex: 1 }}>{item}</Text>
            <Tag color="blue">证据 {idx + 1}</Tag>
          </div>
        </List.Item>
      )}
    />
  );
}
