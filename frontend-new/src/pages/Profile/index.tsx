/**
 * 用户中心页面
 * - 个人信息编辑（用户名、姓名、邮箱、手机号可编辑；部门、角色、状态只读）
 * - 修改密码（必须验证原密码）
 * - 登录记录（限制为当前用户）
 */
import { useState, useEffect } from 'react';
import { Card, Form, Input, Button, Tabs, Tag, Space } from 'antd';
import DataTable from '@/components/DataTable';
import { serverPagination } from '@/components/DataTable/serverPagination';
import { UserOutlined, LockOutlined, HistoryOutlined, SaveOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import {
  useCurrentUser,
  useUpdateMyProfile,
  useChangePassword,
  useLoginLogs
} from '@/services/user';
import type { LoginLog } from '@/services/user';
import { getLoginTypeMeta } from '@/types/statusMeta';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/utils/format';
import { useMessage } from '@/hooks/useMessage';

function ProfilePage() {
  const { t } = useTranslation('settings');
  const { t: tDevice } = useTranslation('device');
  const { t: tAuth } = useTranslation('auth');
  const { t: tCommon } = useTranslation('common');
  const message = useMessage();
  const authUser = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);

  const {
    data: currentUser,
    isLoading: profileLoading,
    refetch: refetchProfile
  } = useCurrentUser();
  const userData = currentUser ?? authUser;

  const updateProfile = useUpdateMyProfile();

  const changePassword = useChangePassword();

  const [logPage, setLogPage] = useState(1);
  const [logPageSize, setLogPageSize] = useState(10);
  const { data: loginLogsData, isLoading: logsLoading } = useLoginLogs({
    page: logPage,
    per_page: logPageSize
  });

  const [profileForm] = Form.useForm();
  const [profileEditing, setProfileEditing] = useState(false);

  const [passwordForm] = Form.useForm();

  useEffect(() => {
    if (userData) {
      profileForm.setFieldsValue({
        username: userData.username,
        name: userData.name || userData.real_name,
        email: userData.email,
        contact_phone: userData.contact_phone
      });
    }
  }, [userData, profileForm]);

  const handleSaveProfile = async () => {
    const values = await profileForm.validateFields();
    try {
      const result = await updateProfile.mutateAsync(values);
      if (result.data) {
        const token = useAuthStore.getState().token ?? '';
        const permissions = useAuthStore.getState().permissions;
        setAuth(result.data, token, permissions);
        message.success(t('profile.message.profileUpdated'));
        setProfileEditing(false);
        refetchProfile();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('profile.message.profileUpdateFailed');
      message.error(msg);
    }
  };

  const handleChangePassword = async () => {
    const values = await passwordForm.validateFields();
    if (values.new_password !== values.confirm_password) {
      message.error(t('user.validation.passwordMismatch'));
      return;
    }
    try {
      await changePassword.mutateAsync({
        old_password: values.old_password,
        new_password: values.new_password
      });
      message.success(t('profile.message.passwordChanged'));
      passwordForm.resetFields();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('profile.message.passwordChangeFailed');
      message.error(msg);
    }
  };

  const logColumns = [
    {
      title: t('profile.column.loginTime'),
      dataIndex: 'login_time',
      key: 'login_time',
      width: 180,
      render: (v: string) => formatDateTime(v)
    },
    {
      title: tDevice('port.column.ipAddress'),
      dataIndex: 'login_ip',
      key: 'login_ip',
      width: 140,
      render: (v: string | null) => v || '-'
    },
    {
      title: t('profile.column.loginType'),
      dataIndex: 'login_type',
      key: 'login_type',
      width: 100,
      render: (v: string) => {
        const m = getLoginTypeMeta(v, tDevice);
        return <Tag color={m?.color ?? 'default'}>{(m?.label ?? v) || tDevice('loginType.WEB')}</Tag>;
      }
    },
    {
      title: t('profile.column.userAgent'),
      dataIndex: 'user_agent',
      key: 'user_agent',
      render: (v: string | null) => v || '-',
      ellipsis: true
    }
  ];

  const rolesDisplay = userData?.roles?.length ? (
    userData.roles.map((r) => (
      <Tag key={r} color="blue">
        {r}
      </Tag>
    ))
  ) : (
    <Tag>{t('profile.noRoles')}</Tag>
  );

  const statusDisplay =
    userData?.status === 0 ? (
      <Tag color="success">{t('role.status.normal')}</Tag>
    ) : (
      <Tag color="error">{t('role.status.disabled')}</Tag>
    );

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Tabs
        defaultActiveKey="profile"
        items={[
          {
            key: 'profile',
            label: (
              <span>
                <UserOutlined /> {t('profile.tab.profile')}
              </span>
            ),
            children: (
              <Card loading={profileLoading}>
                <Form form={profileForm} layout="vertical" disabled={!profileEditing}>
                  <Form.Item
                    name="username"
                    label={tAuth('field.username')}
                    rules={[{ required: true, message: tAuth('validation.usernameRequired') }]}
                  >
                    <Input placeholder={tAuth('field.username')} />
                  </Form.Item>

                  <Form.Item name="name" label={t('user.field.fullName')}>
                    <Input placeholder={t('user.field.realNamePlaceholder')} />
                  </Form.Item>

                  <Form.Item
                    name="email"
                    label={t('user.field.email')}
                    rules={[{ type: 'email', message: t('mail.validation.emailInvalid') }]}
                  >
                    <Input placeholder={t('user.field.email')} />
                  </Form.Item>

                  <Form.Item name="contact_phone" label={t('user.field.contactPhone')}>
                    <Input placeholder={t('user.field.contactPhone')} />
                  </Form.Item>

                  {/* 只读字段：部门 */}
                  <Form.Item label={t('user.field.department')}>
                    <Input
                      value={userData?.department || '-'}
                      disabled
                      style={{ background: '#f5f5f5', color: 'rgba(0,0,0,0.45)' }}
                    />
                  </Form.Item>

                  {/* 只读字段：角色 */}
                  <Form.Item label={t('role.label')}>
                    <div
                      style={{
                        minHeight: 32,
                        display: 'flex',
                        alignItems: 'center',
                        background: '#f5f5f5',
                        borderRadius: 6,
                        padding: '4px 11px',
                        color: 'rgba(0,0,0,0.45)'
                      }}
                    >
                      {rolesDisplay}
                    </div>
                  </Form.Item>

                  {/* 只读字段：状态 */}
                  <Form.Item label={tCommon('field.status')}>
                    <div
                      style={{
                        minHeight: 32,
                        display: 'flex',
                        alignItems: 'center',
                        background: '#f5f5f5',
                        borderRadius: 6,
                        padding: '4px 11px'
                      }}
                    >
                      {statusDisplay}
                    </div>
                  </Form.Item>

                  {/* 只读字段：更新时间 */}
                  <Form.Item label={tCommon('field.updatedAt')}>
                    <Input
                      value={formatDateTime(userData?.updated_at)}
                      disabled
                      style={{ background: '#f5f5f5', color: 'rgba(0,0,0,0.45)' }}
                    />
                  </Form.Item>
                </Form>

                <div style={{ textAlign: 'right', marginTop: 8 }}>
                  {profileEditing ? (
                    <Space>
                      <Button
                        onClick={() => {
                          setProfileEditing(false);
                          profileForm.resetFields();
                        }}
                      >
                        {tCommon('action.cancel')}
                      </Button>
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        loading={updateProfile.isPending}
                        onClick={handleSaveProfile}
                      >
                        {tCommon('action.save')}
                      </Button>
                    </Space>
                  ) : (
                    <Button type="primary" onClick={() => setProfileEditing(true)}>
                      {t('profile.action.editProfile')}
                    </Button>
                  )}
                </div>
              </Card>
            )
          },
          {
            key: 'password',
            label: (
              <span>
                <LockOutlined /> {t('profile.tab.password')}
              </span>
            ),
            children: (
              <Card>
                <Form form={passwordForm} layout="vertical" style={{ maxWidth: 480 }}>
                  <Form.Item
                    name="old_password"
                    label={t('profile.field.oldPassword')}
                    rules={[{ required: true, message: t('profile.validation.oldPasswordRequired') }]}
                  >
                    <Input.Password placeholder={t('profile.validation.oldPasswordRequired')} />
                  </Form.Item>

                  <Form.Item
                    name="new_password"
                    label={t('profile.field.newPassword')}
                    rules={[
                      { required: true, message: t('profile.validation.newPasswordRequired') },
                      { min: 8, message: t('user.validation.passwordMinLength') }
                    ]}
                    extra={t('user.field.passwordTips')}
                  >
                    <Input.Password placeholder={t('profile.validation.newPasswordRequired')} />
                  </Form.Item>

                  <Form.Item
                    name="confirm_password"
                    label={t('profile.field.confirmPassword')}
                    dependencies={['new_password']}
                    rules={[
                      { required: true, message: t('user.validation.confirmPasswordRequired') },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('new_password') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(
                            new Error(t('user.validation.passwordMismatch'))
                          );
                        }
                      })
                    ]}
                  >
                    <Input.Password placeholder={t('user.field.passwordAgain')} />
                  </Form.Item>

                  <Form.Item>
                    <Button
                      type="primary"
                      icon={<LockOutlined />}
                      loading={changePassword.isPending}
                      onClick={handleChangePassword}
                    >
                      {t('profile.tab.password')}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            )
          },
          {
            key: 'login-logs',
            label: (
              <span>
                <HistoryOutlined /> {t('user.action.loginLogs')}
              </span>
            ),
            children: (
              <Card>
                <DataTable<LoginLog>
                  columns={logColumns}
                  dataSource={loginLogsData?.items ?? []}
                  loading={logsLoading}
                  rowKey="id"
                  pagination={serverPagination({
                    current: logPage,
                    pageSize: logPageSize,
                    total: loginLogsData?.total ?? 0,
                    showTotal: (total) => tCommon('pagination.total', { count: total }),
                    showSizeChanger: true,
                    onChange: (p, ps) => {
                      setLogPage(p);
                      setLogPageSize(ps);
                    }
                  })}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  showCard={false}
                  searchable={false}
                />
              </Card>
            )
          }
        ]}
      />
    </div>
  );
}

export default ProfilePage;
