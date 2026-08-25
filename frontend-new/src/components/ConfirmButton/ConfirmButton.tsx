import React from 'react';
import { Button, type ButtonProps } from 'antd';
import { useConfirmAction, type ConfirmActionOptions } from '@/hooks/useConfirmAction';


export interface ConfirmButtonProps
  extends
    Omit<ButtonProps, 'onClick' | 'danger' | 'content' | 'title' | 'icon'>,
    Pick<
      ConfirmActionOptions,
      | 'title'
      | 'content'
      | 'okType'
      | 'icon'
      | 'successMessage'
      | 'errorMessage'
      | 'onConfirm'
      | 'afterConfirm'
    > {
  children?: React.ReactNode;
}

export const ConfirmButton: React.FC<ConfirmButtonProps> = ({
  title,
  content,
  okType = 'danger',
  icon,
  successMessage,
  errorMessage,
  onConfirm,
  afterConfirm,
  children,
  ...buttonProps
}) => {
  const confirmAction = useConfirmAction();
  return (
    <Button
      danger={okType === 'danger'}
      icon={icon}
      {...buttonProps}
      onClick={() =>
        confirmAction({
          title,
          content,
          okType,
          icon,
          successMessage,
          errorMessage,
          onConfirm,
          afterConfirm
        })
      }
    >
      {children}
    </Button>
  );
};

export default ConfirmButton;
