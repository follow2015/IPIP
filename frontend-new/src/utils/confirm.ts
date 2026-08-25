import { Modal } from 'antd';

type ConfirmOptions = Parameters<typeof Modal.confirm>[0];

const CONFIRM_DEFAULTS = {
  okText: '确定',
  cancelText: '取消',
  centered: true,
  maskClosable: false
} as const;

export function confirm(options: ConfirmOptions) {
  return Modal.confirm({ ...CONFIRM_DEFAULTS, ...options });
}
