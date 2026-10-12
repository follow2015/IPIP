import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Select,
  Switch,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import { useMemo, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';

import { useMessage, useModal } from '@/hooks/useMessage';
import {
  useSecurityPolicies,
  useSecurityScan,
  useUpdatePolicy,
  type PolicyValue,
  type SecurityPolicyItem
} from '@/services/security';
import { getApiErrorMessage, isHttpStatus } from '@/utils/apiError';

import { SECURITY_POLICY_LABEL_KEYS, SECURITY_VALUE_LABEL_KEYS } from './labels';

const { Text } = Typography;

const KEY_FLEX: CSSProperties = { flex: '0 0 200px' };
const EDITOR_FLEX: CSSProperties = { flex: '1 1 220px' };
const NUMBER_FLEX: CSSProperties = { flex: '0 1 160px' };

function formatValue(value: PolicyValue): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

export default function PolicyPanel() {
  const { t } = useTranslation('security');
  const message = useMessage();
  const modal = useModal();
  const { data, isLoading } = useSecurityPolicies();
  const updateMutation = useUpdatePolicy();
  const scanMutation = useSecurityScan();
  const [drafts, setDrafts] = useState<Record<string, PolicyValue>>({});

  const items = useMemo(() => data?.items ?? [], [data]);

  const policyName = (key: string): string => {
    const labelKey = SECURITY_POLICY_LABEL_KEYS[key];
    return labelKey ? t(labelKey) : key;
  };

  const valueName = (value: PolicyValue): string => {
    if (typeof value === 'boolean') return t(value ? 'values.on' : 'values.off');
    if (typeof value === 'string') {
      const labelKey = SECURITY_VALUE_LABEL_KEYS[value];
      if (labelKey) return t(labelKey);
    }
    return formatValue(value);
  };

  const failureText = (err: unknown): string =>
    getApiErrorMessage(err) ??
    (isHttpStatus(err, 400) || isHttpStatus(err, 409)
      ? t('policies.conflict')
      : t('policies.saveFailed'));

  const draftOf = (item: SecurityPolicyItem): PolicyValue =>
    item.key in drafts ? drafts[item.key] : item.value;

  const setDraft = (key: string, value: PolicyValue) =>
    setDrafts((prev) => ({ ...prev, [key]: value }));

  const submit = (item: SecurityPolicyItem, value: PolicyValue) => {
    updateMutation.mutate(
      { key: item.key, value, version: item.version ?? undefined },
      {
        onSuccess: () => {
          message.success(t('policies.updated'));
          setDrafts((prev) => {
            const next = { ...prev };
            delete next[item.key];
            return next;
          });
        },
        onError: (err) => message.error(failureText(err))
      }
    );
  };

  const previewThenSubmit = async (item: SecurityPolicyItem, value: PolicyValue) => {
    try {
      const preview = await scanMutation.mutateAsync(true);
      modal.confirm({
        title: t('policies.impactPreview'),
        content: t('policies.impactContent', { count: preview.findings.length }),
        onOk: () => submit(item, value)
      });
    } catch (err) {
      message.error(getApiErrorMessage(err) ?? t('policies.scanFailed'));
    }
  };

  const renderEditor = (item: SecurityPolicyItem) => {
    const value = draftOf(item);
    if (item.type === 'bool') {
      return (
        <Switch checked={Boolean(value)} onChange={(checked) => setDraft(item.key, checked)} />
      );
    }
    if (item.type === 'choice') {
      return (
        <Select
          value={String(value ?? '')}
          style={EDITOR_FLEX}
          options={item.choices.map((choice) => ({ label: valueName(choice), value: choice }))}
          onChange={(next) => {
            if (item.key === 'snmp.mode' && next === 'enforce') {
              void previewThenSubmit(item, next);
              return;
            }
            setDraft(item.key, next);
          }}
        />
      );
    }
    if (item.type === 'int') {
      return (
        <InputNumber
          value={typeof value === 'number' ? value : undefined}
          min={item.min ?? undefined}
          max={item.max ?? undefined}
          style={NUMBER_FLEX}
          onChange={(next) => setDraft(item.key, next ?? 0)}
        />
      );
    }
    if (item.type === 'json') {
      return (
        <Select
          mode="tags"
          style={EDITOR_FLEX}
          value={Array.isArray(value) ? value : []}
          onChange={(next) => setDraft(item.key, next)}
        />
      );
    }
    return (
      <Input
        value={String(value ?? '')}
        style={EDITOR_FLEX}
        onChange={(event) => setDraft(item.key, event.target.value)}
      />
    );
  };

  if (!isLoading && items.length === 0) {
    return <Empty description={t('policies.notEditable')} />;
  }

  return (
    <Card loading={isLoading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {items.map((item) => (
          <div
            key={item.key}
            style={{ display: 'flex', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}
          >
            {/* 原 key 与后端长句说明都留在 Tooltip：正文只放给人看的中文短名 */}
            <Tooltip
              title={
                <>
                  <div>{item.key}</div>
                  <div>{item.description}</div>
                </>
              }
            >
              <Text strong style={KEY_FLEX}>
                {policyName(item.key)}
              </Text>
            </Tooltip>
            {renderEditor(item)}
            <Tag style={{ marginInlineEnd: 0 }}>
              {`${t('policies.default')}: ${valueName(item.default)}`}
            </Tag>
            <Button
              size="small"
              type="primary"
              disabled={!(item.key in drafts)}
              loading={updateMutation.isPending}
              onClick={() => submit(item, draftOf(item))}
            >
              {t('policies.save')}
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}
