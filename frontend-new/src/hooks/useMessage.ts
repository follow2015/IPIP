/**
 * 封装 antd App.useApp() 上下文
 * - 通过 App.useApp() 获取，可消费 ConfigProvider 上下文
 * - 替代静态 message.xxx() 调用，消除 antd 警告
 * - 统一暴露 message / modal，减少对 App.useApp() 的直接依赖
 *
 * 注意：useNotification 已移除。后台异步操作结果统一走站内信（NotificationBell），
 * 不再使用 antd notification 卡片弹出。如需获取 notification 实例，请使用 useAppContext()。
 */
import { App } from 'antd';

export function useMessage() {
  const { message } = App.useApp();
  return message;
}

export function useModal() {
  const { modal } = App.useApp();
  return modal;
}

export function useAppContext() {
  return App.useApp();
}
