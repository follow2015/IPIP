import { useEffect } from 'react';
import { Modal, Form, Input, Radio, Select } from 'antd';
import type { Role } from '@/types/models';
import { useRoomList } from '@/services/room';
import { useDeviceList } from '@/services/device';
import { useTranslation } from 'react-i18next';

interface RoleFormProps {
  open: boolean;
  editRecord?: Role | null;
  onCancel: () => void;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
}

const DATA_SCOPE_VALUES = ['all', 'responsible_person', 'room', 'custom'] as const;
type DataScopeValue = (typeof DATA_SCOPE_VALUES)[number];

function RoleForm({ open, editRecord, onCancel, onOk, loading }: RoleFormProps) {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [form] = Form.useForm();
  const isEdit = !!editRecord;

  const { data: roomsData } = useRoomList({ page: 1, per_page: 500 });
  const { data: devicesData } = useDeviceList({ page: 1, per_page: 500 });
  const rooms = roomsData?.items ?? [];
  const devices = devicesData?.items ?? [];

  const scope = Form.useWatch('data_scope', form);

  useEffect(() => {
    if (open && editRecord) {
      form.setFieldsValue({
        name: editRecord.name,
        display_name: editRecord.display_name,
        description: editRecord.description,
        data_scope: editRecord.data_scope ?? 'all',
        room_ids: editRecord.data_scope_config?.room_ids ?? [],
        device_ids: editRecord.data_scope_config?.device_ids ?? []
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, editRecord, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const { room_ids, device_ids, ...rest } = values;
    const payload: Record<string, unknown> = { ...rest };
    if (rest.data_scope === 'room') {
      payload.data_scope_config = { room_ids };
    } else if (rest.data_scope === 'custom') {
      payload.data_scope_config = { device_ids };
    } else {
      payload.data_scope_config = null;
    }
    await onOk(payload);
  };

  return (
    <Modal
      title={isEdit ? t('role.modal.editTitle') : t('role.modal.createTitle')}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      width={520}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t('role.field.name')}
          rules={[{ required: true, message: t('role.validation.nameRequired') }]}
        >
          <Input placeholder={t('role.placeholder.name')} disabled={isEdit} />
        </Form.Item>
        <Form.Item
          name="display_name"
          label={t('role.field.displayName')}
          rules={[{ required: true, message: t('role.validation.displayNameRequired') }]}
        >
          <Input placeholder={t('role.placeholder.displayName')} />
        </Form.Item>
        <Form.Item name="description" label={tc('field.description')}>
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="data_scope" label={t('role.field.dataScope')} initialValue="all">
          <Radio.Group>
            {DATA_SCOPE_VALUES.map((value) => (
              <Radio key={value} value={value}>
                {t(`role.dataScope.${value}`)}
              </Radio>
            ))}
          </Radio.Group>
        </Form.Item>
        {scope === 'room' && (
          <Form.Item
            name="room_ids"
            label={t('role.field.dataScopeRoomIds')}
            rules={[{ required: true, message: t('role.validation.dataScopeRequired') }]}
          >
            <Select
              mode="multiple"
              placeholder={t('role.placeholder.dataScopeRooms')}
              options={rooms.map((r) => ({ value: r.id, label: r.name }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
        )}
        {scope === 'custom' && (
          <Form.Item
            name="device_ids"
            label={t('role.field.dataScopeDeviceIds')}
            rules={[{ required: true, message: t('role.validation.dataScopeRequired') }]}
          >
            <Select
              mode="multiple"
              placeholder={t('role.placeholder.dataScopeDevices')}
              options={devices.map((d) => ({
                value: d.id,
                label: d.management_ip ? `${d.device_name} (${d.management_ip})` : d.device_name
              }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}

export default RoleForm;
