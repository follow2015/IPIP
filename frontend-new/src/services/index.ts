/**
 * Services 层统一出口（新增文件）
 *
 * 使用方直接从 '@/services' 导入，无需关心内部文件分布：
 *
 * ```ts
 * import { useDeviceList, useCreateDevice, useScanIP } from '@/services';
 * import { queryKeys } from '@/services';
 * ```
 */


export { queryKeys }            from './query-keys';
export { unwrapNested, toSelectOptions } from './service-utils';
export { default as apiClient } from './api-client';
export { get, post, put, del }  from './api-client';
export { createCrudHooks }      from './crud-factory';
export type { CrudConfig, CrudHooks, SelectOption } from './crud-factory';


export * from './auth';


export * from './room';


export * from './cabinet';


export * from './device';
export * from './device-nic';
export * from './device-storage';
export * from './device-connection';
export * from './network-port';


export * from './ip';          
export * from './network';


export * from './switch';


export * from './link-aggregation';


export * from './customer';


export * from './user';
export * from './rbac';


export * from './dashboard';


export * from './vlan';


export * from './audit';


export * from './deviceConfig';
