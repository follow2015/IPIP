import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Space,
  Table,
  Tag,
  Divider,
  Statistic,
  Row,
  Col,
  Typography,
  Progress,
  Tabs,
  Alert,
  List
} from 'antd';
import {
  DatabaseOutlined,
  InboxOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SyncOutlined,
  QuestionCircleOutlined,
  SendOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';
import {
  getRagStatus,
  listRagDocs,
  deleteRagDoc,
  resetRagStore,
  ragIngest,
  subscribeRagIngestProgress,
  ragQa,
  type RagStatus,
  type RagDoc,
  type RagIngestProgressEvent,
  type RagQaResult
} from '@/services/ai';
import { usePermission } from '@/hooks/usePermission';
import { useMessage } from '@/hooks/useMessage';
import { confirm } from '@/utils/confirm';
import { ConfirmButton } from '@/components/ConfirmButton';

const { Paragraph } = Typography;

export default function RAGPage() {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [docs, setDocs] = useState<RagDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [ingestProgress, setIngestProgress] = useState(0);
  const [ingestTotal, setIngestTotal] = useState(0);
  const [question, setQuestion] = useState('');
  const [qaResult, setQaResult] = useState<RagQaResult | null>(null);
  const [asking, setAsking] = useState(false);
  const message = useMessage();
  const { hasPermission } = usePermission();
  const canAdmin = hasPermission('ai:admin');
  const sseCancelRef = useRef<{ cancel: () => void } | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const s = await getRagStatus();
      setStatus(s);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载状态失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await listRagDocs(100, 0);
      setDocs(res.docs);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载文档列表失败');
    }
  }, [message]);

  useEffect(() => {
    fetchStatus();
    fetchDocs();
    return () => {
      sseCancelRef.current?.cancel();
    };
  }, [fetchStatus, fetchDocs]);

  const startIngestTask = useCallback(
    async (docsDir: string) => {
      setIngesting(true);
      setIngestProgress(0);
      setIngestTotal(0);
      try {
        const { task_id } = await ragIngest({ docs_dir: docsDir });
        message.info(`入库任务已提交：${task_id}`);
        sseCancelRef.current?.cancel();
        const cancel = subscribeRagIngestProgress(
          task_id,
          (ev: RagIngestProgressEvent) => {
            if (ev.type === 'progress') {
              setIngestProgress(ev.progress ?? 0);
              setIngestTotal(ev.total ?? 0);
            } else if (ev.type === 'done') {
              message.success(`入库完成，共 ${ev.result ?? ev.progress ?? 0} 篇文档`);
              setIngesting(false);
              fetchStatus();
              fetchDocs();
            } else if (ev.type === 'error') {
              message.error(`入库失败：${ev.message ?? '未知错误'}`);
              setIngesting(false);
            }
          },
          () => {
            message.error('SSE 连接中断');
            setIngesting(false);
          }
        );
        sseCancelRef.current = cancel;
      } catch (err) {
        setIngesting(false);
        message.error(err instanceof Error ? err.message : '提交入库失败');
        throw err;
      }
    },
    [message, fetchStatus, fetchDocs]
  );

  const handleIngest = async (docsDir: string) => {
    if (!docsDir.trim()) {
      message.warning('请输入文档目录');
      return;
    }
    await startIngestTask(docsDir);
  };

  const handleRebuild = () => {
    confirm({
      title: '确认重建知识库',
      icon: <ExclamationCircleOutlined />,
      content:
        '将清空全部文档与索引，并自动重新全量入库，不可恢复。' +
        `重跑目录：${ingestForm.getFieldValue('docs_dir')?.trim() || 'docs'}`,
      okType: 'danger',
      okText: '清空并重建',
      onOk: async () => {
        setIngesting(true);
        setIngestProgress(0);
        setIngestTotal(0);
        try {
          await resetRagStore();
          const dir = ingestForm.getFieldValue('docs_dir')?.trim() || 'docs';
          message.success('知识库已清空，正在重新入库');
          await startIngestTask(dir);
        } catch (err) {
          setIngesting(false);
          message.error(err instanceof Error ? err.message : '重建失败');
        }
      }
    });
  };

  const handleReset = () => {
    confirm({
      title: '确认清空知识库',
      icon: <ExclamationCircleOutlined />,
      content: '将删除所有文档与索引，不可恢复。下次入库会自动重建。',
      okType: 'danger',
      okText: '清空',
      onOk: async () => {
        try {
          await resetRagStore();
          message.success('知识库已清空');
          fetchStatus();
          fetchDocs();
        } catch (err) {
          message.error(err instanceof Error ? err.message : '清空失败');
        }
      }
    });
  };

  const handleAsk = async () => {
    if (!question.trim()) {
      message.warning('请输入问题');
      return;
    }
    setAsking(true);
    setQaResult(null);
    try {
      const result = await ragQa(question);
      setQaResult(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '问答失败');
    } finally {
      setAsking(false);
    }
  };

  const [ingestForm] = Form.useForm();

  return (
    <Tabs
      defaultActiveKey="qa"
      items={[
        {
          key: 'qa',
          label: (
            <Space size={6}>
              <QuestionCircleOutlined />
              <span>知识问答</span>
            </Space>
          ),
          children: (
            <Card>
              <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="输入问题，基于知识库检索回答"
                  maxLength={2000}
                  onPressEnter={handleAsk}
                  disabled={asking}
                />
                <Button type="primary" icon={<SendOutlined />} onClick={handleAsk} loading={asking}>
                  提问
                </Button>
              </Space.Compact>

              {qaResult?.degraded && (
                <Alert
                  type="warning"
                  showIcon
                  message="本地检索模式（无 LLM 参与）"
                  description="当前结果仅来自本地知识库检索，未经过 LLM 模型生成：AI 未配置或模型服务不可用。以下为命中的原文片段，请自行判读。"
                  style={{ marginBottom: 16 }}
                />
              )}

              {qaResult && (
                <Card type="inner" title="回答">
                  <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{qaResult.answer}</Paragraph>
                  {qaResult.references.length > 0 && (
                    <>
                      <Divider />
                      <Paragraph type="secondary">命中片段（{qaResult.references.length}）：</Paragraph>
                      <List
                        size="small"
                        dataSource={qaResult.references}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <List.Item.Meta
                              title={`[${idx + 1}] ${item.doc_id || '-'}`}
                              description={
                                <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                                  {item.text}
                                </Paragraph>
                              }
                            />
                          </List.Item>
                        )}
                      />
                    </>
                  )}
                </Card>
              )}
            </Card>
          )
        },
        {
          key: 'manage',
          label: (
            <Space size={6}>
              <DatabaseOutlined />
              <span>知识库管理</span>
            </Space>
          ),
          children: (
            <Space direction="vertical" size="large" style={{ display: 'flex' }}>
              {/* 状态 + 入库 */}
              <Card
                extra={
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      fetchStatus();
                      fetchDocs();
                    }}
                    loading={loading}
                  >
                    刷新
                  </Button>
                }
              >
                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col span={6}>
                    <Statistic
                      title="知识库状态"
                      valueRender={() =>
                        status?.available ? <Tag color="green">可用</Tag> : <Tag color="red">不可用</Tag>
                      }
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic title="文档总数" value={status?.doc_count ?? 0} />
                  </Col>
                </Row>

                <Divider />
                <Form form={ingestForm} layout="inline" onFinish={(vals) => handleIngest(vals.docs_dir)}>
                  <Form.Item
                    name="docs_dir"
                    rules={[{ required: true, message: '请输入文档目录' }]}
                    style={{ flex: 1 }}
                  >
                    <Input
                      prefix={<InboxOutlined />}
                      placeholder="文档目录（如 docs，相对于 AI_DOCS_ROOT）"
                      disabled={ingesting}
                    />
                  </Form.Item>
                  <Form.Item>
                    <Space>
                      <Button
                        type="primary"
                        htmlType="submit"
                        loading={ingesting}
                        icon={<InboxOutlined />}
                        disabled={!canAdmin}
                      >
                        入库
                      </Button>
                      <Button
                        icon={<SyncOutlined />}
                        onClick={handleRebuild}
                        loading={ingesting}
                        disabled={!canAdmin}
                      >
                        重建索引
                      </Button>
                    </Space>
                  </Form.Item>
                </Form>
                {ingesting && ingestTotal > 0 && (
                  <Progress
                    percent={Math.round((ingestProgress / ingestTotal) * 100)}
                    status="active"
                    style={{ marginTop: 16 }}
                  />
                )}
                {ingesting && (
                  <Paragraph type="secondary" style={{ marginTop: 8 }}>
                    正在入库 {ingestProgress}/{ingestTotal}...
                  </Paragraph>
                )}

                <Divider />
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleReset}
                  disabled={ingesting || !canAdmin}
                >
                  清空知识库
                </Button>
              </Card>

              {/* 文档列表 */}
              <Card
                title="文档列表"
                extra={
                  <Button size="small" onClick={fetchDocs}>
                    刷新
                  </Button>
                }
              >
                <Table
                  rowKey="doc_id"
                  dataSource={docs}
                  pagination={{ pageSize: 10 }}
                  columns={[
                    {
                      title: '文档 ID',
                      dataIndex: 'doc_id',
                      key: 'doc_id',
                      width: 200,
                      ellipsis: true
                    },
                    {
                      title: '内容预览',
                      dataIndex: 'preview',
                      key: 'preview',
                      ellipsis: true
                    },
                    {
                      title: '操作',
                      key: 'action',
                      width: 80,
                      render: (_, record) => (
                        <ConfirmButton
                          type="link"
                          size="small"
                          icon={<DeleteOutlined />}
                          title="确认删除"
                          content={`删除文档 ${record.doc_id}？`}
                          successMessage="已删除"
                          onConfirm={async () => {
                            await deleteRagDoc(record.doc_id);
                          }}
                          afterConfirm={() => {
                            fetchStatus();
                            fetchDocs();
                          }}
                          disabled={!canAdmin}
                        >
                          删除
                        </ConfirmButton>
                      )
                    }
                  ]}
                />
              </Card>
            </Space>
          )
        }
      ]}
    />
  );
}
