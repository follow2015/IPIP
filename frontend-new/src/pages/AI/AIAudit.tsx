import { Space } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import AuditLogTable from '@/components/AuditLogTable';

const RESOURCE_OPTIONS = [
  { label: 'AI 调用', value: 'ai' },
  { label: '设备', value: 'device' },
  { label: 'RAG 知识库', value: 'ai_rag' },
  { label: 'AI 技能', value: 'ai_skill' },
  { label: 'AI 配置', value: 'ai_config' },
  { label: '熔断器', value: 'ai_circuit' }
];

const ACTION_COLOR_MAP: Record<string, string> = {
  'ai.nlq': 'blue',
  'ai.rag': 'cyan',
  'ai.alert': 'orange',
  'ai.remedial.execute': 'red',
  'ai.remedial.rollback': 'volcano',
  'ai.skill.create': 'green',
  'ai.skill.update': 'geekblue',
  'ai.skill.delete': 'magenta',
  'ai.skill.toggle': 'purple',
  'ai.config.update': 'gold',
  'ai.circuit.reset': 'lime'
};

export default function AIAudit() {
  return (
    <AuditLogTable
      title={
        <Space>
          <AuditOutlined />
          <span>AI 审计日志</span>
        </Space>
      }
      actionPrefix="ai."
      resourceOptions={RESOURCE_OPTIONS}
      actionColorMap={ACTION_COLOR_MAP}
    />
  );
}
