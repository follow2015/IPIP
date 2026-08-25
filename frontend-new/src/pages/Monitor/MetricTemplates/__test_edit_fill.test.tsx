import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { Form, Modal, Input, Button } from 'antd';
import { useState } from 'react';

describe('preserve={false} + destroyOnHidden + setFieldsValue', () => {
  it('关闭后 setFieldsValue 再打开，字段应回填', async () => {
    function Harness() {
      const [form] = Form.useForm();
      const [open, setOpen] = useState(false);
      const openEdit = () => {
        form.setFieldsValue({ name: 'EDITED' });
        setOpen(true);
      };
      const close = () => {
        setOpen(false);
        form.resetFields();
      };
      return (
        <>
          <Button data-testid="open" onClick={openEdit}>
            open
          </Button>
          <Button data-testid="close" onClick={close}>
            close
          </Button>
          <Modal open={open} onCancel={close} destroyOnHidden>
            <Form form={form} preserve={false}>
              <Form.Item label="Name" name="name">
                <Input />
              </Form.Item>
            </Form>
          </Modal>
        </>
      );
    }
    const { getByTestId } = render(<Harness />);
    await act(async () => {
      getByTestId('open').click();
    });
    await waitFor(() => {
      expect(screen.queryByDisplayValue('EDITED')).toBeInTheDocument();
    });
  });

  it('先打开关闭再打开编辑，preserve={false} 下字段应回填', async () => {
    function Harness() {
      const [form] = Form.useForm();
      const [open, setOpen] = useState(false);
      const openCreate = () => {
        form.resetFields();
        form.setFieldsValue({ name: 'CREATE_DEFAULT' });
        setOpen(true);
      };
      const openEdit = () => {
        form.setFieldsValue({ name: 'EDITED' });
        setOpen(true);
      };
      const close = () => {
        setOpen(false);
        form.resetFields();
      };
      return (
        <>
          <Button data-testid="create" onClick={openCreate}>
            create
          </Button>
          <Button data-testid="edit" onClick={openEdit}>
            edit
          </Button>
          <Button data-testid="close" onClick={close}>
            close
          </Button>
          <Modal open={open} onCancel={close} destroyOnHidden>
            <Form form={form} preserve={false}>
              <Form.Item label="Name" name="name">
                <Input />
              </Form.Item>
            </Form>
          </Modal>
        </>
      );
    }
    const { getByTestId } = render(<Harness />);
    await act(async () => {
      getByTestId('create').click();
    });
    await waitFor(() => expect(screen.getByDisplayValue('CREATE_DEFAULT')).toBeInTheDocument());
    await act(async () => {
      getByTestId('close').click();
    });
    await waitFor(() =>
      expect(screen.queryByDisplayValue('CREATE_DEFAULT')).not.toBeInTheDocument()
    );
    await act(async () => {
      getByTestId('edit').click();
    });
    await waitFor(
      () => {
        expect(screen.queryByDisplayValue('EDITED')).toBeInTheDocument();
      },
      { timeout: 2000 }
    );
  });
});
