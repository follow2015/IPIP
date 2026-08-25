/**
 * 表单验证规则
 * - 通用验证规则集合
 */
import type { Rule } from 'antd/es/form';


export const ipRule: Rule = {
  validator: (_, value: string) => {
    if (!value) return Promise.resolve();
    
    const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (ipv4Regex.test(value)) {
      const parts = value.split('.').map(Number);
      if (parts.every((p) => p >= 0 && p <= 255)) {
        return Promise.resolve();
      }
    }
    return Promise.reject(new Error('请输入有效的 IP 地址'));
  },
};


export const macRule: Rule = {
  validator: (_, value: string) => {
    if (!value) return Promise.resolve();
    const macRegex = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/;
    if (macRegex.test(value)) {
      return Promise.resolve();
    }
    return Promise.reject(new Error('请输入有效的 MAC 地址（格式：XX:XX:XX:XX:XX:XX）'));
  },
};


export const emailRule: Rule = {
  type: 'email',
  message: '请输入有效的邮箱地址',
};


export const phoneRule: Rule = {
  pattern: /^1[3-9]\d{9}$/,
  message: '请输入有效的手机号',
};
