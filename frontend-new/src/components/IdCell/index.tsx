import { CopyOutlined } from '@ant-design/icons';
import { useMessage } from '@/hooks/useMessage';

interface IdCellProps {
  value: number | string | null | undefined;
}

export default function IdCell({ value }: IdCellProps) {
  const message = useMessage();

  if (value === null || value === undefined || value === '') {
    return <span>-</span>;
  }

  const handleCopy = () => {
    const text = String(value);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => message.success('ID 已复制'))
        .catch(() => message.error('复制失败，请手动复制'));
    } else {
      message.error('当前环境不支持自动复制');
    }
  };

  return (
    <span
      onClick={handleCopy}
      title="点击复制 ID"
      style={{
        cursor: 'pointer',
        fontFamily: 'monospace',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4
      }}
    >
      {value}
      <CopyOutlined style={{ fontSize: 12, opacity: 0.45 }} />
    </span>
  );
}
