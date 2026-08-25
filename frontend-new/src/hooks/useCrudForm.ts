/**
 * CRUD 表单逻辑 Hook
 *
 * 封装表单 Modal 的标准骨架逻辑：
 * - Form.useForm 实例
 * - 编辑时自动填充 / 新增时重置
 * - handleSubmit（validateFields → create/update → message → onClose）
 * - confirmLoading 状态
 *
 * 使用示例：
 * ```tsx
 * const { form, isEdit, handleSubmit, confirmLoading } = useCrudForm<Room, CreateRoomRequest, UpdateRoomRequest>({
 *   open,
 *   editRecord,
 *   onClose,
 *   useCreate: roomHooks.useCreate,
 *   useUpdate: roomHooks.useUpdate,
 * });
 * ```
 */
import { useEffect } from 'react';
import { Form } from 'antd';
import { useMessage } from './useMessage';
import type { UseMutationResult } from '@tanstack/react-query';
import type { ApiResponse } from '@/types/api';


export interface UseCrudFormOptions<T, TCreate, TUpdate> {
  
  open: boolean;
  
  editRecord: T | null;
  
  onClose: () => void;
  
  useCreate: () => UseMutationResult<ApiResponse<T>, Error, TCreate>;
  
  useUpdate: () => UseMutationResult<ApiResponse<T>, Error, TUpdate>;
  
  toFormValues?: (record: T) => Record<string, unknown>;
  
  toUpdatePayload?: (id: number, values: TCreate) => TUpdate;
}


export interface UseCrudFormReturn<TCreate> {
  
  form: ReturnType<typeof Form.useForm>[0];
  
  isEdit: boolean;
  
  handleSubmit: () => Promise<void>;
  
  confirmLoading: boolean;
}


export function useCrudForm<T extends { id: number }, TCreate, TUpdate>(
  options: UseCrudFormOptions<T, TCreate, TUpdate>,
): UseCrudFormReturn<TCreate> {
  const {
    open,
    editRecord,
    onClose,
    useCreate,
    useUpdate,
    toFormValues,
    toUpdatePayload,
  } = options;

  const [form] = Form.useForm();
  const message = useMessage();
  const createMutation = useCreate();
  const updateMutation = useUpdate();
  const isEdit = !!editRecord;

  
  useEffect(() => {
    if (open) {
      if (editRecord) {
        form.setFieldsValue(toFormValues ? toFormValues(editRecord) : editRecord as Record<string, unknown>);
      } else {
        form.resetFields();
      }
    }
  }, [open, editRecord, form, toFormValues]);

  
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit && editRecord) {
        const payload = toUpdatePayload
          ? toUpdatePayload(editRecord.id, values)
          : { id: editRecord.id, ...values } as unknown as TUpdate;
        await updateMutation.mutateAsync(payload);
        message.success('更新成功');
      } else {
        await createMutation.mutateAsync(values);
        message.success('创建成功');
      }
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return {
    form,
    isEdit,
    handleSubmit,
    confirmLoading: createMutation.isPending || updateMutation.isPending,
  };
}
