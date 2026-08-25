/**
 * 编辑凭据密文 Modal
 *
 * 从 Credentials/index.tsx 拆分（M26）：密文字段留空表示「保持不变」，
 * 提交后所有关联设备将用新凭据重新探测。
 */
import { Modal, Form, Input, Alert, type FormInstance } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import {
  useUpdateSharedCredentialPayload,
  type MonitorCredentialListItem
} from '@/services/monitor';
import MonitorCredentialForm from '@/components/MonitorCredentialForm';
import { useMessage } from '@/hooks/useMessage';

interface EditCredentialModalProps {
  open: boolean;
  editCred: MonitorCredentialListItem | null;
  editForm: FormInstance;
  onClose: () => void;
}

export default function EditCredentialModal({
  open,
  editCred,
  editForm,
  onClose
}: EditCredentialModalProps) {
  const updateShared = useUpdateSharedCredentialPayload();
  const msg = useMessage();

  
  const editInitialValues = (() => {
    const meta = editCred?.payload_meta || {};
    const initial: Record<string, unknown> = {
      snmp_version: (meta.snmp_version as string) || 'v2c'
    };
    for (const k of [
      'username',
      'auth_protocol',
      'priv_protocol',
      'api_url',
      'verify_ssl',
      'match_by',
      'community'
    ]) {
      if (meta[k] !== undefined) initial[k] = meta[k];
    }
    return initial;
  })();

  
  const handleSubmitEdit = async () => {
    if (!editCred?.id) return;
    let values: Record<string, unknown>;
    try {
      values = await editForm.validateFields();
    } catch {
      return;
    }
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === undefined || v === null || v === '') continue;
      payload[k] = v;
    }
    try {
      const res = await updateShared.mutateAsync({
        credentialId: editCred.id,
        payload,
        name: (values.name as string) || undefined
      });
      msg.success(res.credential_migrated ? '已更新密文（已为该凭据生成独立行）' : '凭据已更新');
      onClose();
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '更新失败');
    }
  };

  return (
    <Modal
      title="编辑凭据密文"
      open={open}
      onCancel={onClose}
      onOk={handleSubmitEdit}
      confirmLoading={updateShared.isPending}
      width={520}
      destroyOnHidden
    >
      {editCred && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: 16 }}
          message={`此操作将影响 ${editCred.linked_count ?? 0} 台关联设备`}
          description="密文字段留空表示「保持不变」；提交后所有关联设备将用新凭据重新探测。"
        />
      )}
      <Form form={editForm} layout="vertical" initialValues={editInitialValues}>
        <Form.Item
          label="凭据名称"
          name="name"
          rules={[{ required: true, message: '请输入凭据名称' }]}
        >
          <Input placeholder="如：机房A SNMP只读团体字" />
        </Form.Item>
        {editCred && (
          <MonitorCredentialForm
            protocol={editCred.protocol || 'snmp'}
            mode="edit"
            form={editForm}
          />
        )}
      </Form>
    </Modal>
  );
}
