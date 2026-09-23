/**
 * 登录页面
 * - 用户名/密码表单
 * - 登录逻辑 + 错误提示
 * - 已登录自动跳转
 */
import React from 'react';
import { Form, Input, Button, Card, Typography, Checkbox } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/auth';
import { useMessage } from '@/hooks/useMessage';
import type { LoginRequest } from '@/types/api';

const { Title } = Typography;

const REMEMBER_DAYS = 30;

function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuthStore();
  const message = useMessage();
  const { t } = useTranslation('auth');
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (isAuthenticated) {
      const from =
        (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard';
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, location.state]);

  const handleLogin = async (values: LoginRequest) => {
    setLoading(true);
    try {
      await login(values);
      message.success(t('message.loginSuccess'));
      const from =
        (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard';
      navigate(from, { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('message.loginFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
      }}
    >
      <Card style={{ width: 400, boxShadow: '0 8px 24px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3} style={{ margin: 0 }}>
            {t('title')}
          </Title>
          <p style={{ color: '#999', marginTop: 8 }}>{t('subtitle')}</p>
        </div>
        <Form<LoginRequest> onFinish={handleLogin} autoComplete="off" size="large">
          <Form.Item
            name="username"
            rules={[{ required: true, message: t('validation.usernameRequired') }]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('field.username')} autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: t('validation.passwordRequired') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('field.password')}
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item name="remember" valuePropName="checked" initialValue={false}>
            <Checkbox>{t('field.remember', { days: REMEMBER_DAYS })}</Checkbox>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('action.login')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}

export default Login;
