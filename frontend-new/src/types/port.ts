/**
 * 端口相关共享类型（跨 Switches / Devices 域）
 *
 * 上提动机：原 SubmitActionFn 定义在 Switches/PortActions.tsx，被
 * Devices/DeviceDetail/UnifiedPortTab 子文件反向导入，形成
 * Devices → Switches 的耦合。将其与注入式渲染函数类型收敛到本纯类型模块
 * （零运行时依赖），使两域各自从 @/types/port 导入，切断反向依赖。
 */
import type { ReactNode } from 'react';
import type { SwitchPort } from './models';

export type SubmitActionFn = (
  action: string,
  port: string,
  params?: Record<string, unknown>
) => Promise<void>;

export interface PortActionRenderCtx {
  refetch: () => void;
  submitAction: SubmitActionFn;
}

/**
 * 端口操作列渲染函数（由 SwitchDetail 注入，捕获 switchId；
 * 运行时 ctx 注入 refetch / submitAction，避免 Devices 域直接依赖 Switches 组件）
 */
export type RenderPortActionsFn = (port: SwitchPort, ctx: PortActionRenderCtx) => ReactNode;

export interface BatchActionsRenderCtx {
  selectedPorts: string[];
  onClearSelection: () => void;
  hasSsh: boolean;
  refetch: () => void;
  onBatchLocalUpdate?: (portNames: string[], updates: Record<string, unknown>) => Promise<void>;
}

export type RenderBatchActionsFn = (ctx: BatchActionsRenderCtx) => ReactNode;
