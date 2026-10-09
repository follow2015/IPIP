import { Button, Space } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';
import { useResponsive } from '@/hooks/useResponsive';

export interface DetailActionBarProps {
  backText: string;
  onBack: () => void;
  children?: ReactNode;
}

function DetailActionBar({ backText, onBack, children }: DetailActionBarProps) {
  const { isMobile } = useResponsive();

  const backButton = (
    <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
      {backText}
    </Button>
  );

  if (isMobile) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          gap: 8,
          marginBottom: 16
        }}
      >
        <div>{backButton}</div>
        {/* Space 的 wrap 让按钮按行折行；不设 nowrap 是本次修复的核心 */}
        <Space wrap size={[8, 8]}>
          {children}
        </Space>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16
      }}
    >
      {backButton}
      <Space>{children}</Space>
    </div>
  );
}

export default DetailActionBar;
