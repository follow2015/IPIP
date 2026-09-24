import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import 'dayjs/locale/en';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';

import { DEFAULT_LANGUAGE, DEFAULT_NAMESPACE, LANGUAGE_STORAGE_KEY } from './config';
import type { AppLanguage } from './config';
import { pseudoLocalize } from './pseudo';

import zhCommon from '@/locales/zh-CN/common.json';
import zhAuth from '@/locales/zh-CN/auth.json';
import zhDevice from '@/locales/zh-CN/device.json';
import zhMonitor from '@/locales/zh-CN/monitor.json';
import zhNetwork from '@/locales/zh-CN/network.json';
import zhAsset from '@/locales/zh-CN/asset.json';
import zhSettings from '@/locales/zh-CN/settings.json';
import enCommon from '@/locales/en-US/common.json';
import enAuth from '@/locales/en-US/auth.json';
import enDevice from '@/locales/en-US/device.json';
import enMonitor from '@/locales/en-US/monitor.json';
import enNetwork from '@/locales/en-US/network.json';
import enAsset from '@/locales/en-US/asset.json';
import enSettings from '@/locales/en-US/settings.json';
import zhAi from '@/locales/zh-CN/ai.json';
import enAi from '@/locales/en-US/ai.json';

import './types';

const resources = {
  'zh-CN': {
    common: zhCommon,
    auth: zhAuth,
    device: zhDevice,
    monitor: zhMonitor,
    network: zhNetwork,
    asset: zhAsset,
    settings: zhSettings,
    ai: zhAi
  },
  'en-US': {
    common: enCommon,
    auth: enAuth,
    device: enDevice,
    monitor: enMonitor,
    network: enNetwork,
    asset: enAsset,
    settings: enSettings,
    ai: enAi
  }
};

export const ANTD_LOCALE: Record<AppLanguage, typeof zhCN> = {
  'zh-CN': zhCN,
  'en-US': enUS
};

const DAYJS_LOCALE: Record<AppLanguage, string> = {
  'zh-CN': 'zh-cn',
  'en-US': 'en'
};

const syncDayjs = (lng: string) => {
  dayjs.locale(DAYJS_LOCALE[lng as AppLanguage] ?? 'en');
};

const syncDocumentMeta = (lng: string) => {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = lng;
  const title = i18next.t('app.title', { defaultValue: 'IPIP' });
  if (title) document.title = title;
};

const PSEUDO_ENABLED =
  typeof globalThis !== 'undefined' &&
  new URLSearchParams(globalThis.location.search).get('pseudo') === '1';

i18next
  .use(LanguageDetector)
  .use(initReactI18next)
  .use({
    type: 'postProcessor',
    name: 'pseudo',
    process: (value: string) => pseudoLocalize(value)
  })
  .init({
    resources,
    fallbackLng: DEFAULT_LANGUAGE,
    defaultNS: DEFAULT_NAMESPACE,
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage']
    },
    postProcess: PSEUDO_ENABLED ? ['pseudo'] : undefined
  });

syncDayjs(i18next.language);
syncDocumentMeta(i18next.language);
i18next.on('languageChanged', syncDayjs);
i18next.on('languageChanged', syncDocumentMeta);

export function changeLanguage(lng: AppLanguage): Promise<unknown> {
  return i18next.changeLanguage(lng);
}

export default i18next;
