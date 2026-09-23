import { useConfirm } from '@/utils/confirm';
import { useState } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Button, Switch, Space, Drawer, Tag, Checkbox, Typography, Input, Modal } from 'antd';
import {
  PlusOutlined,
  KeyOutlined,
  HistoryOutlined,
  TeamOutlined,
  CopyOutlined
} from '@ant-design/icons';
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
  type CreateUserRequest,
  type UpdateUserRequest
} from '@/services/user';
import { useRoleOptions, useUserRoles, useSetUserRoles, useRoleList } from '@/services/rbac';
import type { User, Role } from '@/types/models';
import { useCrudPage } from '@/hooks/useCrudPage';
import { useMessage } from '@/hooks/useMessage';
import { formatDateTime } from '@/utils/format';
import { useTranslation } from 'react-i18next';

function Users() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const { t: ta } = useTranslation('auth');
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

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (id: number) => <IdCell value={id} />
    },
    { title: ta('field.username'), dataIndex: 'username', key: 'username' },
    { title: t('user.field.fullName'), dataIndex: 'name', key: 'name', render: (v: string) => v || '-' },
    { title: t('user.field.email'), dataIndex: 'email', key: 'email', render: (v: string) => v || '-' },
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
      render: (_: unknown, r: User) => (
        <Space>
          <Button type="link" size="small" onClick={() => crud.handleEdit(r)}>
            {tc('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<TeamOutlined />}
            onClick={() => handleAssignRole(r)}
          >
            {t('role.label')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => handleResetPassword(r)}
          >
            {t('user.action.resetPassword')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => handleViewLoginLogs(r)}
          >
            {t('user.action.loginLogs')}
          </Button>
          <Button type="link" size="small" danger onClick={() => crud.handleDelete(r)}>
            {tc('action.delete')}
          </Button>
        </Space>
      )
    }
  ];

  return (
    <div>
      <DataTable<User>
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

  const allRoles = allRolesData?.items ?? [];
  const currentRoleNames = (userRoles ?? []).map((r) => r.name);
  const [selectedNames, setSelectedNames] = useState<string[]>([]);

  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen && userRoles) {
      setSelectedNames(currentRoleNames);
    }
  };

  const handleSubmit = async () => {
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

  return (
    <Drawer
      title={t('role.assignTitle', { username: user?.username ?? '' })}
      open={open}
      onClose={onClose}
      size={400}
      afterOpenChange={handleOpenChange}
      extra={
        <Button type="primary" loading={setUserRoles.isPending} onClick={handleSubmit}>
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
