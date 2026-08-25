/**
 * 用户中心页面
 * - 个人信息编辑（用户名、姓名、邮箱、手机号可编辑；部门、角色、状态只读）
 * - 修改密码（必须验证原密码）
 * - 登录记录（限制为当前用户）
 */
import { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Tabs,
  Descriptions,
  Table,
  Tag,
  message,
  Space,
  App,
} from 'antd';
import {
  UserOutlined,
  LockOutlined,
  HistoryOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import { useCurrentUser, useUpdateMyProfile, useChangePassword, useLoginLogs } from '@/services/user';
import type { LoginLog } from '@/services/user';
import { LOGIN_TYPE_MAP } from '@/types/enums';
import { formatDateTime } from '@/utils/format';


const PASSWORD_TIPS = '至少8位，需包含大写字母、小写字母、数字和特殊字符';


function ProfilePage() {
  const { message: messageApi } = App.useApp();
  const authUser = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);

  
  const { data: currentUser, isLoading: profileLoading, refetch: refetchProfile } = useCurrentUser();
  const userData = currentUser ?? authUser;

  
  const updateProfile = useUpdateMyProfile();

  
  const changePassword = useChangePassword();

  
  const [logPage, setLogPage] = useState(1);
  const [logPageSize, setLogPageSize] = useState(10);
  const { data: loginLogsData, isLoading: logsLoading } = useLoginLogs({ page: logPage, per_page: logPageSize });

  
  const [profileForm] = Form.useForm();
  const [profileEditing, setProfileEditing] = useState(false);

  
  const [passwordForm] = Form.useForm();

  
  useEffect(() => {
    if (userData) {
      profileForm.setFieldsValue({
        username: userData.username,
        name: userData.name || userData.real_name,
        email: userData.email,
        contact_phone: userData.contact_phone,
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
        messageApi.success('个人信息更新成功');
        setProfileEditing(false);
        refetchProfile();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新失败';
      messageApi.error(msg);
    }
  };

  
  const handleChangePassword = async () => {
    const values = await passwordForm.validateFields();
    if (values.new_password !== values.confirm_password) {
      messageApi.error('两次输入的新密码不一致');
      return;
    }
    try {
      await changePassword.mutateAsync({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      messageApi.success('密码修改成功，请重新登录');
      passwordForm.resetFields();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '密码修改失败';
      messageApi.error(msg);
    }
  };

  
  const logColumns = [
    {
      title: '登录时间',
      dataIndex: 'login_time',
      key: 'login_time',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: 'IP地址',
      dataIndex: 'login_ip',
      key: 'login_ip',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: '登录类型',
      dataIndex: 'login_type',
      key: 'login_type',
      width: 100,
      render: (v: string) => {
        const m = LOGIN_TYPE_MAP[v];
        return <Tag color={m?.color ?? 'default'}>{(m?.label ?? v) || 'Web'}</Tag>;
      },
    },
    {
      title: '设备/浏览器',
      dataIndex: 'user_agent',
      key: 'user_agent',
      render: (v: string | null) => v || '-',
      ellipsis: true,
    },
  ];

  
  const rolesDisplay = userData?.roles?.length
    ? userData.roles.map((r) => <Tag key={r} color="blue">{r}</Tag>)
    : <Tag>无角色</Tag>;

  
  const statusDisplay = userData?.status === 0
    ? <Tag color="success">正常</Tag>
    : <Tag color="error">禁用</Tag>;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Tabs
        defaultActiveKey="profile"
        items={[
          {
            key: 'profile',
            label: (
              <span><UserOutlined /> 个人信息</span>
            ),
            children: (
              <Card loading={profileLoading}>
                <Form
                  form={profileForm}
                  layout="vertical"
                  disabled={!profileEditing}
                >
                  <Form.Item
                    name="username"
                    label="用户名"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input placeholder="用户名" />
                  </Form.Item>

                  <Form.Item
                    name="name"
                    label="姓名"
                  >
                    <Input placeholder="真实姓名" />
                  </Form.Item>

                  <Form.Item
                    name="email"
                    label="邮箱"
                    rules={[
                      { type: 'email', message: '请输入有效的邮箱地址' },
                    ]}
                  >
                    <Input placeholder="邮箱" />
                  </Form.Item>

                  <Form.Item
                    name="contact_phone"
                    label="手机号码"
                  >
                    <Input placeholder="手机号码" />
                  </Form.Item>

                  {}
                  <Form.Item label="部门">
                    <Input value={userData?.department || '-'} disabled style={{ background: '#f5f5f5', color: 'rgba(0,0,0,0.45)' }} />
                  </Form.Item>

                  {}
                  <Form.Item label="角色">
                    <div style={{ minHeight: 32, display: 'flex', alignItems: 'center', background: '#f5f5f5', borderRadius: 6, padding: '4px 11px', color: 'rgba(0,0,0,0.45)' }}>
                      {rolesDisplay}
                    </div>
                  </Form.Item>

                  {}
                  <Form.Item label="状态">
                    <div style={{ minHeight: 32, display: 'flex', alignItems: 'center', background: '#f5f5f5', borderRadius: 6, padding: '4px 11px' }}>
                      {statusDisplay}
                    </div>
                  </Form.Item>

                  {}
                  <Form.Item label="更新时间">
                    <Input value={formatDateTime(userData?.updated_at)} disabled style={{ background: '#f5f5f5', color: 'rgba(0,0,0,0.45)' }} />
                  </Form.Item>
                </Form>

                <div style={{ textAlign: 'right', marginTop: 8 }}>
                  {profileEditing ? (
                    <Space>
                      <Button onClick={() => { setProfileEditing(false); profileForm.resetFields(); }}>
                        取消
                      </Button>
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        loading={updateProfile.isPending}
                        onClick={handleSaveProfile}
                      >
                        保存
                      </Button>
                    </Space>
                  ) : (
                    <Button type="primary" onClick={() => setProfileEditing(true)}>
                      编辑信息
                    </Button>
                  )}
                </div>
              </Card>
            ),
          },
          {
            key: 'password',
            label: (
              <span><LockOutlined /> 修改密码</span>
            ),
            children: (
              <Card>
                <Form
                  form={passwordForm}
                  layout="vertical"
                  style={{ maxWidth: 480 }}
                >
                  <Form.Item
                    name="old_password"
                    label="原密码"
                    rules={[{ required: true, message: '请输入原密码' }]}
                  >
                    <Input.Password placeholder="请输入原密码" />
                  </Form.Item>

                  <Form.Item
                    name="new_password"
                    label="新密码"
                    rules={[
                      { required: true, message: '请输入新密码' },
                      { min: 8, message: '密码至少8位' },
                    ]}
                    extra={PASSWORD_TIPS}
                  >
                    <Input.Password placeholder="请输入新密码" />
                  </Form.Item>

                  <Form.Item
                    name="confirm_password"
                    label="确认新密码"
                    dependencies={['new_password']}
                    rules={[
                      { required: true, message: '请确认新密码' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('new_password') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error('两次密码不一致'));
                        },
                      }),
                    ]}
                  >
                    <Input.Password placeholder="再次输入新密码" />
                  </Form.Item>

                  <Form.Item>
                    <Button
                      type="primary"
                      icon={<LockOutlined />}
                      loading={changePassword.isPending}
                      onClick={handleChangePassword}
                    >
                      修改密码
                    </Button>
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'login-logs',
            label: (
              <span><HistoryOutlined /> 登录记录</span>
            ),
            children: (
              <Card>
                <Table<LoginLog>
                  columns={logColumns}
                  dataSource={loginLogsData?.items ?? []}
                  loading={logsLoading}
                  rowKey="id"
                  pagination={{
                    total: loginLogsData?.total ?? 0,
                    pageSize: logPageSize,
                    current: logPage,
                    showTotal: (t) => `共 ${t} 条`,
                    showSizeChanger: true,
                    onChange: (p, ps) => { setLogPage(p); setLogPageSize(ps); },
                  }}
                  size="small"
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}

export default ProfilePage;
