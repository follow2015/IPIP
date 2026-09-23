export const SUPPORTED_LANGUAGES = [
  { key: 'zh-CN', label: '中文', short: '中' }, // i18n-ignore
  { key: 'en-US', label: 'English', short: 'EN' }
] as const;

export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number]['key'];

export const DEFAULT_LANGUAGE: AppLanguage = 'zh-CN';

export const DEFAULT_NAMESPACE = 'common' as const;

export const LANGUAGE_STORAGE_KEY = 'ipip-language';

export const NAMESPACES = [
  'common',
  'auth',
  'device',
  'monitor',
  'network',
  'asset',
  'settings',
  'ai'
] as const;
