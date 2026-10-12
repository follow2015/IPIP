import { Button, Empty, Input, Modal, Space } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import DataTable from '@/components/DataTable';
import { serverPagination } from '@/components/DataTable/serverPagination';
import { useMessage } from '@/hooks/useMessage';
import {
  useLockAccount,
  useRemoteLogins,
  useUnlockAccount,
  type RemoteLoginRow
} from '@/services/security';
import { getApiErrorMessage } from '@/utils/apiError';

const PAGE_SIZE = 20;

export default function RemoteLoginPanel() {
  const { t } = useTranslation('security');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<RemoteLoginRow | null>(null);
  const [reason, setReason] = useState('');

  const params = useMemo(() => ({ page, per_page: PAGE_SIZE }), [page]);
  const { data, isLoading, error, refetch } = useRemoteLogins(params);
  const lockMutation = useLockAccount();
  const unlockMutation = useUnlockAccount();

  const unlock = useCallback(
    (row: RemoteLoginRow) => {
      unlockMutation.mutate(row.user_id, {
        onSuccess: () => message.success(t('remoteLogins.unlocked')),
        onError: (err) => message.error(getApiErrorMessage(err) ?? t('remoteLogins.unlockFailed'))
      });
    },
    [message, t, unlockMutation]
  );

  const columns = useMemo(
    () => [
      { title: t('remoteLogins.user'), dataIndex: 'username' },
      { title: t('remoteLogins.ip'), dataIndex: 'ip' },
      { title: t('remoteLogins.count'), dataIndex: 'count' },
      {
        title: t('remoteLogins.lastTime'),
        dataIndex: 'last_time',
        render: (value: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-')
      },
      {
        title: '',
        key: 'action',
        render: (_: unknown, row: RemoteLoginRow) => (
          <Space wrap>
            <Button
              size="small"
              onClick={() => {
                setTarget(row);
                setReason('');
              }}
            >
              {t('remoteLogins.lock')}
            </Button>
            <Button size="small" onClick={() => unlock(row)}>
              {t('remoteLogins.unlock')}
            </Button>
          </Space>
        )
      }
    ],
    [t, unlock]
  );

  const submitLock = () => {
    if (!target) return;
    if (!reason.trim()) {
      message.warning(t('remoteLogins.reasonRequired'));
      return;
    }
    lockMutation.mutate(
      { userId: target.user_id, reason: reason.trim() },
      {
        onSuccess: () => {
          message.success(t('remoteLogins.locked'));
          setTarget(null);
        },
        onError: (err) => message.error(getApiErrorMessage(err) ?? t('remoteLogins.lockFailed'))
      }
    );
  };

  if (data && !data.enabled) {
    return <Empty description={t('remoteLogins.disabled')} />;
  }

  return (
    <>
      <DataTable<RemoteLoginRow>
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey={(row) => `${row.user_id}-${row.ip}`}
        pagination={serverPagination({
          current: page,
          pageSize: PAGE_SIZE,
          total: data?.total ?? 0,
          onChange: (nextPage) => setPage(nextPage)
        })}
        size="small"
        scroll={{ x: 'max-content' }}
        showCard={false}
        searchable={false}
        error={error}
        onRetry={refetch}
        emptyText={t('remoteLogins.empty')}
      />
      <Modal
        open={Boolean(target)}
        title={t('remoteLogins.lock')}
        okText={t('remoteLogins.lock')}
        cancelText={tCommon('action.cancel')}
        confirmLoading={lockMutation.isPending}
        onOk={submitLock}
        onCancel={() => setTarget(null)}
      >
        <Input.TextArea
          rows={3}
          value={reason}
          placeholder={t('remoteLogins.reason')}
          onChange={(event) => setReason(event.target.value)}
        />
      </Modal>
    </>
  );
}
