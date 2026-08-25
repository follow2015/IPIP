import { useState } from 'react';
import { Modal, Input } from 'antd';

interface IPBatchBanModalProps {
  open: boolean;
  onClose: () => void;
  submitting: boolean;
  
  onSubmit: (ips: string[]) => void;
}


export function IPBatchBanModal({ open, onClose, submitting, onSubmit }: IPBatchBanModalProps) {
  const [ips, setIps] = useState('');

  const handleOk = () => {
    const list = ips
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    onSubmit(list);
  };

  const handleCancel = () => {
    setIps('');
    onClose();
  };

  return (
    <Modal
      title="批量封禁IP"
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      okButtonProps={{ danger: true, loading: submitting }}
      width={520}
      destroyOnHidden
    >
      <p style={{ marginBottom: 8, color: '#666' }}>
        每行一个IP地址，将通过核心交换机下发黑洞路由进行封禁。
      </p>
      <Input.TextArea
        value={ips}
        onChange={(e) => setIps(e.target.value)}
        rows={8}
        placeholder={'10.10.1.100\n10.10.1.101\n10.10.1.102'}
      />
    </Modal>
  );
}
