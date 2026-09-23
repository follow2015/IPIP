/**
 * 权限分配组件
 * - 按分类展示权限树，勾选后提交到后端
 * - 对齐后端 PUT /rbac/roles/<id>/permissions 接口（接收 permissions: string[] 权限编码列表）
 */
import { useEffect, useState, useMemo } from 'react';
import { Modal, Tree, Spin, Tag } from 'antd';
import type { TreeProps } from 'antd';
import { useRolePermissions, useSetRolePermissions } from '@/services/rbac';
import type { Role, Permission } from '@/types/models';
import { useMessage } from '@/hooks/useMessage';
import { useTranslation } from 'react-i18next';

interface PermissionAssignProps {
  open: boolean;
  role: Role | null;
  permissions: Permission[];
  onClose: () => void;
  onSuccess: () => void;
}

function PermissionAssign({ open, role, permissions, onClose, onSuccess }: PermissionAssignProps) {
  const { t } = useTranslation('settings');
  const [checkedKeys, setCheckedKeys] = useState<string[]>([]);
  const { data: rolePerms, isLoading: permsLoading } = useRolePermissions(role?.id ?? 0);
  const setRolePermissions = useSetRolePermissions();
  const message = useMessage();

  const treeData = useMemo<TreeProps['treeData']>(() => {
    const categoryMap = new Map<string, Permission[]>();
    permissions.forEach((p) => {
      const cat = p.category ?? t('permission.uncategorized');
      const list = categoryMap.get(cat) ?? [];
      list.push(p);
      categoryMap.set(cat, list);
    });
    return Array.from(categoryMap.entries()).map(([category, perms]) => ({
      title: category,
      key: `cat-${category}`,
      children: perms.map((p) => ({
        title: `${p.name} (${p.code})`,
        key: p.code,
      })),
    }));
  }, [permissions, t]);

  const categoryKeys = useMemo(
    () => new Set((treeData ?? []).map((n) => n.key as string)),
    [treeData],
  );

  useEffect(() => {
    if (open && rolePerms) {
      const codes = Array.isArray(rolePerms)
        ? rolePerms.map((p) => (typeof p === 'string' ? p : p.code))
        : [];
      setCheckedKeys(codes);
    }
  }, [open, rolePerms]);

  const handleSubmit = async () => {
    if (!role) return;
    const permCodes = checkedKeys.filter((k) => !categoryKeys.has(k));
    try {
      await setRolePermissions.mutateAsync({ roleId: role.id, permissions: permCodes });
      message.success(t('permission.message.updated'));
      onSuccess();
      onClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('permission.message.updateFailed'));
    }
  };

  return (
    <Modal
      title={t('permission.assignTitle', { name: role?.display_name ?? '' })}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={560}
      confirmLoading={setRolePermissions.isPending}
      destroyOnHidden
    >
      {permsLoading ? (
        <Spin description={t('permission.loading')} />
      ) : (
        <Tree
          checkable
          defaultExpandAll
          checkedKeys={checkedKeys}
          onCheck={(keys) => setCheckedKeys(keys as string[])}
          treeData={treeData}
        />
      )}
    </Modal>
  );
}

export default PermissionAssign;
