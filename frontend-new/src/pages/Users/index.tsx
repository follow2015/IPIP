import { useConfirm } from '@/utils/confirm';
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useDirtyGuard, useSnapshotDirty } from '@/hooks/useDirtyGuard';
import {
  Button,
  Switch,
  Space,
  Drawer,
  Tag,
  Checkbox,
  Input,
  Modal,
  theme,
  Typography
} from 'antd';
import { PlusOutlined, KeyOutlined, HistoryOutlined, TeamOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import DataTable from '@/components/DataTable';
import IdCell from '@/components/IdCell';
import UserForm from './UserForm';
import {
  useUserList,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useToggleUserStatus,
  useResetPassword,
  type CreateUserRequest
} from '@/services/user';
import { useRoleOptions, useUserRoles, useSetUserRoles, useRoleList } from '@/services/rbac';
import type { User } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';

function Users() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const { t: ta } = useTranslation('auth');
  const { token } = theme.useToken();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const roleDrawer = useDisclosure();
  const [roleUser, setRoleUser] = useState<User | null>(null);

  const crud = useCrudPage<User>({
    useList: useUserList,
    useDelete: useDeleteUser,
    nameKey: 'username',
    nameLabel: t('user.label')
  });

  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const toggleStatus = useToggleUserStatus();
  const resetPassword = useResetPassword();
  const message = useMessage();
  const { data: roleOptions } = useRoleOptions();

  const handleResetPassword = (r: User) => {
    confirm({
      title: t('user.action.resetPassword'),
      content: t('user.resetPasswordConfirm', { username: r.username }),
      okText: t('user.action.confirmReset'),
      cancelText: tc('action.cancel'),
      onOk: async () => {
        try {
          const res = await resetPassword.mutateAsync(r.id);
          const newPassword = res.data?.new_password;
          if (newPassword) {
            Modal.success({
              title: t('user.message.resetPasswordSuccess'),
              content: (
                <div>
                  <p>{t('user.newPasswordLabel', { username: r.username })}</p>
                  <Input.TextArea
                    value={newPassword}
                    readOnly
                    autoSize
                    style={{ marginTop: 8, fontFamily: 'monospace' }}
                  />
                  <p style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
                    {t('user.passwordKeepSafeHint')}
                  </p>
                </div>
              ),
              okText: t('user.action.copiedAndClose'),
              onOk: () => {
                navigator.clipboard?.writeText(newPassword);
              }
            });
          } else {
            message.success(t('user.message.passwordReset'));
          }
        } catch (err) {
          message.error(err instanceof Error ? err.message : t('user.message.resetFailed'));
        }
      }
    });
  };

  const handleViewLoginLogs = (r: User) => {
    navigate(`/login-logs?user_id=${r.id}`);
  };

  const handleAssignRole = (r: User) => {
    setRoleUser(r);
    roleDrawer.open();
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      if (crud.editRecord) {
        await updateUser.mutateAsync({
          id: crud.editRecord.id,
          data: values as unknown as CreateUserRequest
        });
        message.success(tc('message.updateSuccess'));
      } else {
        await createUser.mutateAsync(values as unknown as CreateUserRequest);
        message.success(tc('message.createSuccess'));
      }
      crud.closeForm();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const handleToggle = (r: User) => {
    const newStatus = r.status === 1 ? 0 : 1;
    toggleStatus.mutateAsync({ id: r.id, status: newStatus }).then(() => {
      message.success(t('user.message.statusUpdated'));
      crud.refetch();
    });
  };

  const renderUserActions = (r: User) => (
    <Space wrap>
      <Button type="link" size="small" style={{ padding: 0 }} onClick={() => crud.handleEdit(r)}>
        {tc('action.edit')}
      </Button>
      <Button
        type="link"
        size="small"
        icon={<TeamOutlined />}
        style={{ padding: 0 }}
        onClick={() => handleAssignRole(r)}
      >
        {t('role.label')}
      </Button>
      <Button
        type="link"
        size="small"
        icon={<KeyOutlined />}
        style={{ padding: 0 }}
        onClick={() => handleResetPassword(r)}
      >
        {t('user.action.resetPassword')}
      </Button>
      <Button
        type="link"
        size="small"
        icon={<HistoryOutlined />}
        style={{ padding: 0 }}
        onClick={() => handleViewLoginLogs(r)}
      >
        {t('user.action.loginLogs')}
      </Button>
      <Button
        type="link"
        size="small"
        danger
        style={{ padding: 0 }}
        onClick={() => crud.handleDelete(r)}
      >
        {tc('action.delete')}
      </Button>
    </Space>
  );

  const renderUserCard = (r: User) => {
    const { Text } = Typography;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
        <Space wrap size={8}>
          <Text strong>{r.username ?? '-'}</Text>
          <Switch
            size="small"
            checked={r.is_active}
            onChange={() => handleToggle(r)}
            checkedChildren={tc('action.enable')}
            unCheckedChildren={tc('action.disable')}
          />
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.name || '-'}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.email || '-'}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.department || '-'}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {r.contact_phone || '-'}
        </Text>
        {r.roles?.length ? (
          <Space size={4} wrap>
            {r.roles.map((role) => (
              <Tag key={role} color={token.colorPrimary}>
                {role}
              </Tag>
            ))}
          </Space>
        ) : null}
        <Text type="secondary" style={{ fontSize: 12 }}>
          {tc('field.updatedAt')}: {formatDateTime(r.updated_at)}
        </Text>
        {renderUserActions(r)}
      </div>
    );
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    { title: ta('field.username'), dataIndex: 'username', key: 'username' },
    {
      title: t('user.field.fullName'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => v || '-'
    },
    {
      title: t('user.field.email'),
      dataIndex: 'email',
      key: 'email',
      render: (v: string) => v || '-'
    },
    {
      title: t('user.field.department'),
      dataIndex: 'department',
      key: 'department',
      render: (v: string) => v || '-'
    },
    {
      title: t('user.field.contactPhone'),
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      render: (v: string) => v || '-'
    },
    {
      title: t('role.label'),
      dataIndex: 'roles',
      key: 'roles',
      render: (v: string[]) => v?.map((r) => <Tag key={r}>{r}</Tag>) ?? '-'
    },
    {
      title: tc('field.status'),
      dataIndex: 'status',
      key: 'status',
      render: (_: number, r: User) => (
        <Switch
          checked={r.is_active}
          onChange={() => handleToggle(r)}
          checkedChildren={tc('action.enable')}
          unCheckedChildren={tc('action.disable')}
        />
      )
    },
    {
      title: tc('field.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => formatDateTime(v)
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: User) => renderUserActions(r)
    }
  ];

  return (
    <div>
      <DataTable<User>
        error={crud.error}
        onRetry={crud.refetch}
        columns={columns}
        dataSource={crud.data?.items ?? []}
        loading={crud.isLoading}
        rowKey="id"
        total={crud.data?.total}
        page={crud.table.page}
        perPage={crud.table.perPage}
        onPageChange={(p, ps) => {
          crud.table.setPage(p);
          if (ps !== crud.table.perPage) crud.table.setPerPage(ps);
        }}
        searchValue={crud.table.search}
        onSearch={crud.table.setSearch}
        onRefresh={() => crud.refetch()}
        toolbar={
          <Button type="primary" icon={<PlusOutlined />} onClick={crud.handleAdd}>
            {t('user.action.add')}
          </Button>
        }
        mobileCardMode
        cardRender={renderUserCard}
      />

      <UserForm
        open={crud.formOpen}
        editRecord={crud.editRecord}
        onCancel={crud.closeForm}
        onOk={handleSubmit}
        loading={createUser.isPending || updateUser.isPending}
        roleOptions={roleOptions}
      />

      {/* 分配角色抽屉 */}
      <RoleAssignDrawer
        open={roleDrawer.isOpen}
        user={roleUser}
        onClose={() => {
          roleDrawer.close();
          setRoleUser(null);
        }}
        onSuccess={() => crud.refetch()}
      />
    </div>
  );
}


interface RoleAssignDrawerProps {
  open: boolean;
  user: User | null;
  onClose: () => void;
  onSuccess: () => void;
}

function RoleAssignDrawer({ open, user, onClose, onSuccess }: RoleAssignDrawerProps) {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const { data: userRoles, isLoading: rolesLoading } = useUserRoles(user?.id ?? 0);
  const { data: allRolesData } = useRoleList();
  const setUserRoles = useSetUserRoles();
  const message = useMessage();
  const confirm = useConfirm();

  const allRoles = allRolesData?.items ?? [];
  const currentRoleNames = (userRoles ?? []).map((r) => r.name);
  const [selectedNames, setSelectedNames] = useState<string[]>([]);
  const [initialNames, setInitialNames] = useState<string[]>([]);

  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen && userRoles) {
      setSelectedNames(currentRoleNames);
      setInitialNames(currentRoleNames);
    }
  };

  const isPending = setUserRoles.isPending;
  const isDirty = useSnapshotDirty(initialNames, selectedNames);
  const guard = useDirtyGuard({ isPending, isDirty });

  const doSubmit = async () => {
    if (!user) return;
    try {
      await setUserRoles.mutateAsync({ userId: user.id, roles: selectedNames });
      message.success(t('role.message.updated'));
      onSuccess();
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('role.message.updateFailed'));
    }
  };

  const handleSubmit = () => {
    if (selectedNames.length === 0) {
      confirm({
        title: tc('confirm.emptyRoleTitle'),
        content: tc('confirm.emptyRoleContent'),
        okButtonProps: { danger: true },
        onOk: doSubmit
      });
      return;
    }
    void doSubmit();
  };

  return (
    <Drawer
      title={t('role.assignTitle', { username: user?.username ?? '' })}
      open={open}
      onClose={() => guard.requestClose(onClose)}
      size={400}
      afterOpenChange={handleOpenChange}
      closable={!isPending}
      mask={{ closable: false }}
      extra={
        <Button type="primary" loading={isPending} onClick={handleSubmit}>
          {tc('action.save')}
        </Button>
      }
    >
      {rolesLoading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>{tc('message.loading')}...</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {allRoles.map((role) => (
            <div
              key={role.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                border: '1px solid #f0f0f0',
                borderRadius: 6
              }}
            >
              <div>
                <span style={{ fontWeight: 500 }}>{role.display_name}</span>
                <span style={{ color: '#999', marginLeft: 8 }}>({role.name})</span>
                {role.description && (
                  <div style={{ color: '#999', fontSize: 12 }}>{role.description}</div>
                )}
              </div>
              <Checkbox
                checked={selectedNames.includes(role.name)}
                onChange={(e) => {
                  setSelectedNames((prev) =>
                    e.target.checked ? [...prev, role.name] : prev.filter((n) => n !== role.name)
                  );
                }}
              />
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}

export default Users;
