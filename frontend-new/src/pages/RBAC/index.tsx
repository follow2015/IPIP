import { useConfirmAction } from '@/hooks/useConfirmAction';
import { useState, useMemo } from 'react';
import { useDisclosure } from '@/hooks/useDisclosure';
import { Table, Button, Space, Card, Tabs, Tag, Switch } from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SafetyOutlined,
  KeyOutlined
} from '@ant-design/icons';
import RoleForm from './RoleForm';
import PermissionAssign from './PermissionAssign';
import {
  useRoleList,
  usePermissionList,
  useCreateRole,
  useUpdateRole,
  useDeleteRole,
  useRoleDetail,
  useRolePermissions,
  type CreateRoleRequest,
  type UpdateRoleRequest
} from '@/services/rbac';
import type { Role, Permission, RoleDetail } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

function RBAC() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [activeTab, setActiveTab] = useState('roles');
  const form = useDisclosure();
  const [editRecord, setEditRecord] = useState<Role | null>(null);
  const permAssign = useDisclosure();
  const [permAssignRole, setPermAssignRole] = useState<Role | null>(null);

  const { data: rolesData, isLoading: rolesLoading, refetch: refetchRoles } = useRoleList();
  const { data: permsData, isLoading: permsLoading } = usePermissionList();
  const createRole = useCreateRole();
  const updateRole = useUpdateRole();
  const deleteRole = useDeleteRole();
  const message = useMessage();

  const roles =
    (rolesData as unknown as { items?: Role[] })?.items ?? (rolesData as unknown as Role[]) ?? [];
  const permissions =
    (permsData as unknown as { items?: Permission[] })?.items ??
    (permsData as unknown as Permission[]) ??
    [];

  const handleAdd = () => {
    setEditRecord(null);
    form.open();
  };

  const handleEdit = (r: Role) => {
    setEditRecord(r);
    form.open();
  };

  const confirmAction = useConfirmAction();
  const handleDelete = (r: Role) => {
    confirmAction({
      title: tc('confirm.deleteTitle'),
      content: t('role.deleteConfirmContent', { name: r.display_name }),
      okType: 'danger',
      successMessage: tc('message.deleteSuccess'),
      errorMessage: tc('message.deleteFailed'),
      onConfirm: () => deleteRole.mutateAsync(r.id),
      afterConfirm: refetchRoles
    });
  };

  const handlePermAssign = (r: Role) => {
    setPermAssignRole(r);
    permAssign.open();
  };

  const handleFormSubmit = async (values: Record<string, unknown>) => {
    try {
      if (editRecord) {
        await updateRole.mutateAsync({
          id: editRecord.id,
          data: values as unknown as CreateRoleRequest
        });
        message.success(tc('message.updateSuccess'));
      } else {
        await createRole.mutateAsync(values as unknown as CreateRoleRequest);
        message.success(tc('message.createSuccess'));
      }
      form.close();
      refetchRoles();
    } catch (err) {
      message.error(err instanceof Error ? err.message : tc('message.operationFailed'));
    }
  };

  const roleColumns = [
    { title: t('role.field.name'), dataIndex: 'name', key: 'name' },
    { title: t('role.field.displayName'), dataIndex: 'display_name', key: 'display_name' },
    {
      title: tc('field.status'),
      dataIndex: 'status',
      key: 'status',
      render: (v: number) =>
        v === 0 ? (
          <Tag color="green">{t('role.status.normal')}</Tag>
        ) : (
          <Tag color="red">{t('role.status.disabled')}</Tag>
        )
    },
    {
      title: t('role.field.permissionCount'),
      key: 'perm_count',
      render: (_: unknown, r: Role) =>
        (r as Role & { permission_count?: number }).permission_count ?? r.permissions?.length ?? 0
    },
    {
      title: t('role.field.userCount'),
      key: 'user_count',
      render: (_: unknown, r: Role) => r.user_count ?? 0
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: tc('field.actions'),
      key: 'action',
      render: (_: unknown, r: Role) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            {tc('action.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SafetyOutlined />}
            onClick={() => handlePermAssign(r)}
          >
            {t('permission.label')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(r)}
          >
            {tc('action.delete')}
          </Button>
        </Space>
      )
    }
  ];

  const permCategories = useMemo(() => {
    const map = new Map<string, Permission[]>();
    permissions.forEach((p) => {
      const cat = p.category ?? t('permission.uncategorized');
      const list = map.get(cat) ?? [];
      list.push(p);
      map.set(cat, list);
    });
    return Array.from(map.entries());
  }, [permissions, t]);

  const permColumns = [
    {
      title: t('permission.field.code'),
      dataIndex: 'code',
      key: 'code',
      render: (v: string) => <Tag>{v}</Tag>
    },
    { title: t('permission.field.name'), dataIndex: 'name', key: 'name' },
    {
      title: t('permission.field.category'),
      dataIndex: 'category',
      key: 'category',
      render: (v: string | null) => v ?? t('permission.uncategorized')
    },
    {
      title: tc('field.description'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v ?? '-'
    }
  ];

  return (
    <Card>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'roles',
            label: t('rbac.tab.roles'),
            children: (
              <>
                <div style={{ marginBottom: 16, textAlign: 'right' }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    {t('role.action.add')}
                  </Button>
                </div>
                <Table<Role>
                  columns={roleColumns}
                  dataSource={roles}
                  rowKey="id"
                  loading={rolesLoading}
                  size="small"
                  scroll={{ x: 'max-content' }}
                />
              </>
            )
          },
          {
            key: 'permissions',
            label: t('rbac.tab.permissions'),
            children: (
              <Table<Permission>
                columns={permColumns}
                dataSource={permissions}
                rowKey="id"
                loading={permsLoading}
                size="small"
                pagination={{ pageSize: 20, showTotal: (t) => tc('pagination.total', { count: t }) }}
                scroll={{ x: 'max-content' }}
              />
            )
          }
        ]}
      />

      <RoleForm
        open={form.isOpen}
        editRecord={editRecord}
        onCancel={() => form.close()}
        onOk={handleFormSubmit}
        loading={createRole.isPending || updateRole.isPending}
      />

      <PermissionAssign
        open={permAssign.isOpen}
        role={permAssignRole}
        permissions={permissions}
        onClose={() => {
          permAssign.close();
          setPermAssignRole(null);
        }}
        onSuccess={() => refetchRoles()}
      />
    </Card>
  );
}

export default RBAC;
