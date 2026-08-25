import { confirm } from '@/utils/confirm';
import { useState } from 'react';
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

function Users() {
  const navigate = useNavigate();
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const [roleUser, setRoleUser] = useState<User | null>(null);

  const crud = useCrudPage<User>({
    useList: useUserList,
    useDelete: useDeleteUser,
    nameKey: 'username',
    nameLabel: '用户'
  });

  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const toggleStatus = useToggleUserStatus();
  const resetPassword = useResetPassword();
  const message = useMessage();
  const { data: roleOptions } = useRoleOptions();

  const handleResetPassword = (r: User) => {
    confirm({
      title: '重置密码',
      content: `确定要重置用户「${r.username}」的密码吗？系统将随机生成新密码。`,
      okText: '确定重置',
      cancelText: '取消',
      onOk: async () => {
        try {
          const res = await resetPassword.mutateAsync(r.id);
          const newPassword = res.data?.new_password;
          if (newPassword) {
            Modal.success({
              title: '密码重置成功',
              content: (
                <div>
                  <p>用户「{r.username}」的新密码：</p>
                  <Input.TextArea
                    value={newPassword}
                    readOnly
                    autoSize
                    style={{ marginTop: 8, fontFamily: 'monospace' }}
                  />
                  <p style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
                    请妥善保管此密码，关闭后无法再次查看。
                  </p>
                </div>
              ),
              okText: '已复制并关闭',
              onOk: () => {
                navigator.clipboard?.writeText(newPassword);
              }
            });
          } else {
            message.success('密码已重置');
          }
        } catch (err) {
          message.error(err instanceof Error ? err.message : '重置失败');
        }
      }
    });
  };

  const handleViewLoginLogs = (r: User) => {
    navigate(`/login-logs?user_id=${r.id}`);
  };

  const handleAssignRole = (r: User) => {
    setRoleUser(r);
    setRoleDrawerOpen(true);
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      if (crud.editRecord) {
        await updateUser.mutateAsync({
          id: crud.editRecord.id,
          data: values as unknown as CreateUserRequest
        });
        message.success('更新成功');
      } else {
        await createUser.mutateAsync(values as unknown as CreateUserRequest);
        message.success('创建成功');
      }
      crud.closeForm();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const handleToggle = (r: User) => {
    const newStatus = r.status === 1 ? 0 : 1;
    toggleStatus.mutateAsync({ id: r.id, status: newStatus }).then(() => {
      message.success('状态已更新');
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
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '姓名', dataIndex: 'name', key: 'name', render: (v: string) => v || '-' },
    { title: '邮箱', dataIndex: 'email', key: 'email', render: (v: string) => v || '-' },
    { title: '部门', dataIndex: 'department', key: 'department', render: (v: string) => v || '-' },
    {
      title: '联系电话',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      render: (v: string) => v || '-'
    },
    {
      title: '角色',
      dataIndex: 'roles',
      key: 'roles',
      render: (v: string[]) => v?.map((r) => <Tag key={r}>{r}</Tag>) ?? '-'
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (_: number, r: User) => (
        <Switch
          checked={r.is_active}
          onChange={() => handleToggle(r)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      )
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => formatDateTime(v)
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: User) => (
        <Space>
          <Button type="link" size="small" onClick={() => crud.handleEdit(r)}>
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<TeamOutlined />}
            onClick={() => handleAssignRole(r)}
          >
            角色
          </Button>
          <Button
            type="link"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => handleResetPassword(r)}
          >
            重置密码
          </Button>
          <Button
            type="link"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => handleViewLoginLogs(r)}
          >
            登录记录
          </Button>
          <Button type="link" size="small" danger onClick={() => crud.handleDelete(r)}>
            删除
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
            新增用户
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
        open={roleDrawerOpen}
        user={roleUser}
        onClose={() => {
          setRoleDrawerOpen(false);
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
      message.success('角色更新成功');
      onSuccess();
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '角色更新失败');
    }
  };

  return (
    <Drawer
      title={`${user?.username ?? ''} - 分配角色`}
      open={open}
      onClose={onClose}
      size={400}
      afterOpenChange={handleOpenChange}
      extra={
        <Button type="primary" loading={setUserRoles.isPending} onClick={handleSubmit}>
          保存
        </Button>
      }
    >
      {rolesLoading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>加载中...</div>
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
