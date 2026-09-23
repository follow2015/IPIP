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
import { useConfirm } from '@/utils/confirm';
import { ConfirmButton } from '@/components/ConfirmButton';
import { useTranslation } from 'react-i18next';

const { Paragraph, Text } = Typography;

export default function RAGPage() {
  const { t } = useTranslation('ai');
  const { t: tc } = useTranslation('common');
  const confirm = useConfirm();
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
      message.error(err instanceof Error ? err.message : t('rag.message.loadStatusFailed'));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await listRagDocs(100, 0);
      setDocs(res.docs);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('rag.message.loadDocsFailed'));
    }
  }, [message, t]);

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
        message.info(t('rag.message.ingestSubmitted', { taskId: task_id }));
        sseCancelRef.current?.cancel();
        const cancel = subscribeRagIngestProgress(
          task_id,
          (ev: RagIngestProgressEvent) => {
            if (ev.type === 'progress') {
              setIngestProgress(ev.progress ?? 0);
              setIngestTotal(ev.total ?? 0);
            } else if (ev.type === 'done') {
              const count = Number(ev.result);
              if (Number.isFinite(count) && ev.result !== null && ev.result !== '') {
                message.success(t('rag.message.ingestDone', { count }));
              } else {
                message.error(
                  t('rag.message.ingestFailed', {
                    reason: String(ev.result ?? t('error.unknown'))
                  })
                );
              }
              setIngesting(false);
              fetchStatus();
              fetchDocs();
            } else if (ev.type === 'error') {
              message.error(
                t('rag.message.ingestFailed', { reason: ev.message ?? t('error.unknown') })
              );
              setIngesting(false);
            }
          },
          () => {
            message.error(t('rag.message.sseDisconnected'));
            setIngesting(false);
          }
        );
        sseCancelRef.current = cancel;
      } catch (err) {
        setIngesting(false);
        message.error(err instanceof Error ? err.message : t('rag.message.ingestSubmitFailed'));
        throw err;
      }
    },
    [message, fetchStatus, fetchDocs, t]
  );

  const handleIngest = async (docsDir: string) => {
    const dir = (docsDir ?? '').trim() || '.';
    if (dir.startsWith('/') || /^[A-Za-z]:[\\/]/.test(dir)) {
      message.warning(t('rag.validation.relativePath'));
      return;
    }
    await startIngestTask(dir);
  };

  const handleRebuild = () => {
    const dir = ingestForm.getFieldValue('docs_dir')?.trim() || '.';
    if (dir.startsWith('/') || /^[A-Za-z]:[\\/]/.test(dir)) {
      message.warning(t('rag.validation.relativePath'));
      return;
    }
    confirm({
      title: t('rag.rebuild.title'),
      icon: <ExclamationCircleOutlined />,
      content: t('rag.rebuild.content', { dir }),
      okType: 'danger',
      okText: t('rag.rebuild.okText'),
      onOk: async () => {
        setIngesting(true);
        setIngestProgress(0);
        setIngestTotal(0);
        try {
          await resetRagStore();
          message.success(t('rag.message.storeClearedReingesting'));
          await startIngestTask(dir);
        } catch (err) {
          setIngesting(false);
          message.error(err instanceof Error ? err.message : t('rag.message.rebuildFailed'));
        }
      }
    });
  };

  const handleReset = () => {
    confirm({
      title: t('rag.reset.title'),
      icon: <ExclamationCircleOutlined />,
      content: t('rag.reset.content'),
      okType: 'danger',
      okText: t('rag.reset.okText'),
      onOk: async () => {
        try {
          await resetRagStore();
          message.success(t('rag.message.storeCleared'));
          fetchStatus();
          fetchDocs();
        } catch (err) {
          message.error(err instanceof Error ? err.message : t('rag.message.resetFailed'));
        }
      }
    });
  };

  const handleAsk = async () => {
    if (!question.trim()) {
      message.warning(t('validation.enterQuestion'));
      return;
    }
    setAsking(true);
    setQaResult(null);
    try {
      const result = await ragQa(question);
      setQaResult(result);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('rag.message.qaFailed'));
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
              <span>{t('rag.tab.qa')}</span>
            </Space>
          ),
          children: (
            <Card>
              <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={t('rag.placeholder.question')}
                  maxLength={2000}
                  onPressEnter={handleAsk}
                  disabled={asking}
                />
                <Button type="primary" icon={<SendOutlined />} onClick={handleAsk} loading={asking}>
                  {t('rag.action.ask')}
                </Button>
              </Space.Compact>

              {qaResult?.degraded && (
                <Alert
                  type="warning"
                  showIcon
                  message={t('rag.degraded.title')}
                  description={t('rag.degraded.description')}
                  style={{ marginBottom: 16 }}
                />
              )}

              {qaResult && (
                <Card type="inner" title={t('rag.answer.title')}>
                  <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{qaResult.answer}</Paragraph>
                  {qaResult.references.length > 0 && (
                    <>
                      <Divider />
                      <Paragraph type="secondary">
                        {t('rag.answer.hitFragments', { count: qaResult.references.length })}
                      </Paragraph>
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
              <span>{t('rag.tab.manage')}</span>
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
                    {tc('action.refresh')}
                  </Button>
                }
              >
                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col xs={12} md={6}>
                    <Statistic
                      title={t('rag.stat.status')}
                      valueRender={() =>
                        status?.available ? (
                          <Tag color="green">{t('rag.status.available')}</Tag>
                        ) : (
                          <Tag color="red">{t('rag.status.unavailable')}</Tag>
                        )
                      }
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic title={t('rag.stat.docCount')} value={status?.doc_count ?? 0} />
                  </Col>
                </Row>

                <Divider />
                {/* 显式展示文档根目录：docs_dir 是相对它的子目录。此前默认值填
                    "docs" 被拼成 <root>/docs/docs，反复报「目录不存在」。 */}
                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  {t('rag.docsRoot.rootLabel')}
                  <Text code>{status?.docs_root || tc('message.loading')}</Text>
                  {t('rag.docsRoot.relativeIntro')}
                  <Text strong>{t('rag.docsRoot.relativeWord')}</Text>
                  {t('rag.docsRoot.pathLabel')}
                  <Text code>.</Text>
                  {t('rag.docsRoot.dotHint')}
                  <Text code>monitoring</Text>
                  {t('rag.docsRoot.equals')}
                  <Text code>{`${status?.docs_root || t('rag.docsRoot.rootPlaceholder')}/monitoring`}</Text>
                  {t('rag.docsRoot.envNote')}
                  <Text code>AI_DOCS_ROOT</Text>
                  {t('rag.docsRoot.restartNote')}
                </Paragraph>
                <Form
                  form={ingestForm}
                  layout="inline"
                  onFinish={(vals) => handleIngest(vals.docs_dir)}
                >
                  <Form.Item name="docs_dir" initialValue="." style={{ flex: 1 }}>
                    <Input
                      prefix={<InboxOutlined />}
                      placeholder={t('rag.placeholder.subDir')}
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
                        {t('rag.action.ingest')}
                      </Button>
                      <Button
                        icon={<SyncOutlined />}
                        onClick={handleRebuild}
                        loading={ingesting}
                        disabled={!canAdmin}
                      >
                        {t('rag.action.rebuildIndex')}
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
                    {t('rag.progress.ingesting', {
                      current: ingestProgress,
                      total: ingestTotal
                    })}
                  </Paragraph>
                )}

                <Divider />
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleReset}
                  disabled={ingesting || !canAdmin}
                >
                  {t('rag.action.reset')}
                </Button>
              </Card>

              {/* 文档列表 */}
              <Card
                title={t('rag.docs.title')}
                extra={
                  <Button size="small" onClick={fetchDocs}>
                    {tc('action.refresh')}
                  </Button>
                }
              >
                <Table
                  rowKey="doc_id"
                  dataSource={docs}
                  pagination={{ pageSize: 10 }}
                  columns={[
                    {
                      title: t('rag.docs.column.docId'),
                      dataIndex: 'doc_id',
                      key: 'doc_id',
                      width: 200,
                      ellipsis: true
                    },
                    {
                      title: t('rag.docs.column.preview'),
                      dataIndex: 'preview',
                      key: 'preview',
                      ellipsis: true
                    },
                    {
                      title: tc('field.actions'),
                      key: 'action',
                      width: 80,
                      render: (_, record) => (
                        <ConfirmButton
                          type="link"
                          size="small"
                          icon={<DeleteOutlined />}
                          title={tc('confirm.deleteTitle')}
                          content={t('rag.docs.confirmDelete', { docId: record.doc_id })}
                          successMessage={t('rag.docs.deleteSuccess')}
                          onConfirm={async () => {
                            await deleteRagDoc(record.doc_id);
                          }}
                          afterConfirm={() => {
                            fetchStatus();
                            fetchDocs();
                          }}
                          disabled={!canAdmin}
                        >
                          {tc('action.delete')}
                        </ConfirmButton>
                      )
                    }
                  ]}
                  scroll={{ x: 'max-content' }}
                />
              </Card>
            </Space>
          )
        }
      ]}
    />
  );
}
