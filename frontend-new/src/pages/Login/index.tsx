/**
 * 登录页面
 * - 用户名/密码表单
 * - 登录逻辑 + 错误提示
 * - 已登录自动跳转
 */
import React from 'react';
import { Form, Input, Button, Card, Typography, Checkbox, Tooltip, theme } from 'antd';
import { UserOutlined, LockOutlined, TranslationOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/auth';
import { useMessage } from '@/hooks/useMessage';
import { changeLanguage } from '@/i18n';
import { SUPPORTED_LANGUAGES, type AppLanguage } from '@/i18n/config';
import type { LoginRequest } from '@/types/api';

const { Title } = Typography;

const REMEMBER_DAYS = 30;

const CARD_WIDTH = '100%';
const CARD_MAX_WIDTH = 400;

function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuthStore();
  const message = useMessage();
  const { t, i18n } = useTranslation('auth');
  const { t: tc } = useTranslation('common');
  const [loading, setLoading] = React.useState(false);

  const currentLang = (i18n.resolvedLanguage || i18n.language) as AppLanguage;
  const nextLang = SUPPORTED_LANGUAGES.find((l) => l.key !== currentLang)?.key ?? 'zh-CN';
  const nextLangMeta =
    SUPPORTED_LANGUAGES.find((l) => l.key === nextLang) ?? SUPPORTED_LANGUAGES[0];
  const { token } = theme.useToken();

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
        background: token.colorBgLayout
      }}
    >
      <Card
        style={{
          width: CARD_WIDTH,
          maxWidth: CARD_MAX_WIDTH,
          boxShadow: '0 8px 24px rgba(0,0,0,0.15)'
        }}
      >
        {/* 语言切换：放在卡片内容顶部右侧，不引入新的定位上下文，避免窄屏溢出风险 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <Tooltip title={tc('language.switchTo')}>
            <Button
              type="text"
              size="small"
              icon={<TranslationOutlined />}
              onClick={() => changeLanguage(nextLang)}
              aria-label={tc('language.switchTo')}
            >
              {nextLangMeta.short}
            </Button>
          </Tooltip>
        </div>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3} style={{ margin: 0 }}>
            {t('title')}
          </Title>
          <p style={{ color: token.colorTextTertiary, marginTop: 8 }}>{t('subtitle')}</p>
        </div>
        <Form<LoginRequest> onFinish={handleLogin} autoComplete="off" size="large">
          <Form.Item
            name="username"
            rules={[{ required: true, message: t('validation.usernameRequired') }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('field.username')}
              autoComplete="username"
            />
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
            <Button type="primary" htmlType="submit" loading={loading} disabled={loading} block>
              {t('action.login')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}

export default Login;
