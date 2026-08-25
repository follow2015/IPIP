/**
 * useInvalidatingMutation — 执行 mutation 后自动失效指定 query key
 *
 * 替代每个 hook 中重复的 useQueryClient + onSuccess 模板。
 * 自动失效逻辑与调用方传入的 onSuccess 合并执行，不会被覆盖。
 *
 * invalidateKeys 支持两种形态：
 * - 静态：单个 query key 数组（如 `queryKeys.devices.all`），向后兼容原有调用方；
 * - 动态：函数 `(data, variables, context) => Array<key>`，用于根据响应/入参失效多个 key
 *   （典型场景：失效对端设备缓存，避免丢失 peer 失效逻辑）。
 */
import { useMutation, useQueryClient, type UseMutationOptions } from '@tanstack/react-query';


export type InvalidateKeysArg<TData, TVariables> =
  | readonly unknown[]
  | ((data: TData, variables: TVariables, context: unknown) => Array<readonly unknown[]>);


export function useInvalidatingMutation<TData, TError, TVariables>(
  mutationFn: (vars: TVariables) => Promise<TData>,
  invalidateKeys: InvalidateKeysArg<TData, TVariables>,
  options?: Omit<UseMutationOptions<TData, TError, TVariables>, 'mutationFn'>
) {
  const queryClient = useQueryClient();
  
  const { onSuccess: callerOnSuccess, ...restOptions } = options ?? {};
  return useMutation({
    mutationFn,
    onSuccess: (data, vars, ctx, mutation) => {
      const keys =
        typeof invalidateKeys === 'function' ? invalidateKeys(data, vars, ctx) : [invalidateKeys];
      keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
      callerOnSuccess?.(data, vars, ctx, mutation);
    },
    ...restOptions
  });
}
