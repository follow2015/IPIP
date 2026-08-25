import { useConfirmAction } from '@/hooks/useConfirmAction';

import { useState, useMemo } from 'react';
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


function RBAC() {
  const [activeTab, setActiveTab] = useState('roles');
  const [formOpen, setFormOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<Role | null>(null);
  const [permAssignOpen, setPermAssignOpen] = useState(false);
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
    setFormOpen(true);
  };

  
  const handleEdit = (r: Role) => {
    setEditRecord(r);
    setFormOpen(true);
  };

  
  const confirmAction = useConfirmAction();
  const handleDelete = (r: Role) => {
    confirmAction({
      title: '确认删除',
      content: `确定要删除角色「${r.display_name}」吗？`,
      okType: 'danger',
      successMessage: '删除成功',
      errorMessage: '删除失败',
      onConfirm: () => deleteRole.mutateAsync(r.id),
      afterConfirm: refetchRoles
    });
  };

  
  const handlePermAssign = (r: Role) => {
    setPermAssignRole(r);
    setPermAssignOpen(true);
  };

  
  const handleFormSubmit = async (values: Record<string, unknown>) => {
    try {
      if (editRecord) {
        await updateRole.mutateAsync({
          id: editRecord.id,
          data: values as unknown as CreateRoleRequest
        });
        message.success('更新成功');
      } else {
        await createRole.mutateAsync(values as unknown as CreateRoleRequest);
        message.success('创建成功');
      }
      setFormOpen(false);
      refetchRoles();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  
  const roleColumns = [
    { title: '角色名', dataIndex: 'name', key: 'name' },
    { title: '显示名', dataIndex: 'display_name', key: 'display_name' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: number) => (v === 0 ? <Tag color="green">正常</Tag> : <Tag color="red">禁用</Tag>)
    },
    {
      title: '权限数',
      key: 'perm_count',
      render: (_: unknown, r: Role) =>
        (r as Role & { permission_count?: number }).permission_count ?? r.permissions?.length ?? 0
    },
    { title: '用户数', key: 'user_count', render: (_: unknown, r: Role) => r.user_count ?? 0 },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v ?? '-'
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: Role) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SafetyOutlined />}
            onClick={() => handlePermAssign(r)}
          >
            权限
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(r)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  
  const permCategories = useMemo(() => {
    const map = new Map<string, Permission[]>();
    permissions.forEach((p) => {
      const cat = p.category ?? '未分类';
      const list = map.get(cat) ?? [];
      list.push(p);
      map.set(cat, list);
    });
    return Array.from(map.entries());
  }, [permissions]);

  
  const permColumns = [
    { title: '权限编码', dataIndex: 'code', key: 'code', render: (v: string) => <Tag>{v}</Tag> },
    { title: '权限名称', dataIndex: 'name', key: 'name' },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      render: (v: string | null) => v ?? '未分类'
    },
    {
      title: '描述',
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
            label: '角色管理',
            children: (
              <>
                <div style={{ marginBottom: 16, textAlign: 'right' }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    新增角色
                  </Button>
                </div>
                <Table<Role>
                  columns={roleColumns}
                  dataSource={roles}
                  rowKey="id"
                  loading={rolesLoading}
                  size="small"
                />
              </>
            )
          },
          {
            key: 'permissions',
            label: '权限列表',
            children: (
              <Table<Permission>
                columns={permColumns}
                dataSource={permissions}
                rowKey="id"
                loading={permsLoading}
                size="small"
                pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
              />
            )
          }
        ]}
      />

      <RoleForm
        open={formOpen}
        editRecord={editRecord}
        onCancel={() => setFormOpen(false)}
        onOk={handleFormSubmit}
        loading={createRole.isPending || updateRole.isPending}
      />

      <PermissionAssign
        open={permAssignOpen}
        role={permAssignRole}
        permissions={permissions}
        onClose={() => {
          setPermAssignOpen(false);
          setPermAssignRole(null);
        }}
        onSuccess={() => refetchRoles()}
      />
    </Card>
  );
}

export default RBAC;
