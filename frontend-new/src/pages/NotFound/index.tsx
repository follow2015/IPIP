import { useTranslation } from 'react-i18next';

function NotFound() {
  const { t } = useTranslation('common');

  return (
    <div style={{ textAlign: 'center', padding: '100px 0' }}>
      <h1>404</h1>
      <p>{t('error.notFound')}</p>
      <a href="/">{t('error.backHome')}</a>
    </div>
  );
}
export default NotFound;
