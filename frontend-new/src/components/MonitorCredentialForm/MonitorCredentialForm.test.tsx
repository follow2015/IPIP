import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Form, Button } from 'antd';
import MonitorCredentialForm from './index';

function renderWithForm(protocol: string, mode: 'create' | 'edit') {
  function Harness() {
    const [form] = Form.useForm();
    return (
      <Form form={form} layout="vertical">
        <MonitorCredentialForm protocol={protocol} mode={mode} form={form} />
        <Button htmlType="submit">submit</Button>
      </Form>
    );
  }
  return render(<Harness />);
}

describe('MonitorCredentialForm 协议路由契约', () => {
  it('protocol=snmp 渲染 SNMP 子表单（SNMP 版本 + Community）', () => {
    renderWithForm('snmp', 'create');
    expect(screen.getByText('SNMP 版本')).toBeInTheDocument();
    expect(screen.getByText('Community')).toBeInTheDocument();
  });

  it('protocol=ipmi 渲染 IPMI 子表单（不渲染 SNMP 字段）', () => {
    renderWithForm('ipmi', 'create');
    expect(screen.queryByText('SNMP 版本')).not.toBeInTheDocument();
    expect(screen.queryByText('Community')).not.toBeInTheDocument();
  });

  it('protocol=zabbix 渲染 Zabbix 子表单（不渲染 SNMP/IPMI 字段）', () => {
    renderWithForm('zabbix', 'create');
    expect(screen.queryByText('SNMP 版本')).not.toBeInTheDocument();
    expect(screen.queryByText('Community')).not.toBeInTheDocument();
  });

  it('未知 protocol 返回 null（仅渲染 submit 按钮）', () => {
    renderWithForm('redfish', 'create');
    expect(screen.queryByText('SNMP 版本')).not.toBeInTheDocument();
    expect(screen.getByText('submit')).toBeInTheDocument();
  });

  it('edit 模式渲染 SNMP 子表单且 placeholder 为"留空保持不变"', () => {
    renderWithForm('snmp', 'edit');
    expect(screen.getByPlaceholderText('留空保持不变')).toBeInTheDocument();
  });
});
