import type common from '@/locales/zh-CN/common.json';
import type auth from '@/locales/zh-CN/auth.json';
import type device from '@/locales/zh-CN/device.json';
import type monitor from '@/locales/zh-CN/monitor.json';
import type network from '@/locales/zh-CN/network.json';
import type asset from '@/locales/zh-CN/asset.json';
import type settings from '@/locales/zh-CN/settings.json';
import type ai from '@/locales/zh-CN/ai.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: typeof common;
      auth: typeof auth;
      device: typeof device;
      monitor: typeof monitor;
      network: typeof network;
      asset: typeof asset;
      settings: typeof settings;
      ai: typeof ai;
    };
  }
}
