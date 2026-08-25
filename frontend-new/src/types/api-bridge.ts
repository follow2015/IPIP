/**
 * 类型桥接层：从 OpenAPI 自动生成的类型导出业务类型别名
 *
 * 本文件是 Flask → OpenAPI JSON → TypeScript 类型管线的核心桥接层。
 * 将 api-generated.ts 中 components["schemas"] 的 Response Schema 映射为
 * 前端业务代码使用的类型名称，逐步替代手写的 models.ts。
 *
 * 命名映射规则：
 *   - Response Schema → 业务实体类型（去掉 Response 后缀）
 *     例：DeviceResponse → Device, RoomResponse → Room
 *   - Create/Update Schema → 请求体类型（保持原名）
 *     例：DeviceCreate → DeviceCreate, RoomUpdate → RoomUpdate
 *   - Embedded Schema → 嵌套子类型（去掉 Embedded 后缀）
 *     例：SwitchCredentialEmbedded → SwitchCredential
 *   - 通用 Schema → 直接导出
 *     例：ApiResponse, PaginationMeta, ApiError
 *
 * 生成命令：npm run generate:types
 * 源文件：openapi.json（由后端 /api/openapi.json 生成）
 */
import type { components } from './api-generated';


/**
 * 将类型 T 的所有第一层属性变为 required（去掉 ? 修饰符）。
 * OpenAPI 3.0 + Marshmallow 生成的 Schema 缺少 required 声明，
 * 导致 openapi-typescript 将所有字段标记为 optional。
 * 后端 to_dict() 实际一定返回这些字段，因此需要收紧。
 *
 * 注意：仅处理第一层，不递归嵌套对象（嵌套对象由各自的 Schema 独立定义）。
 */
type MakeRequired<T> = {
  [K in keyof T]-?: T[K];
};

/**
 * 条件 required：将 T 中指定的 keys 收紧为 required，其余保持原样。
 * 用于部分字段后端确实可能不返回的场景（如条件追加的关联字段）。
 */
type RequireKeys<T, K extends keyof T> = T & Required<Pick<T, K>>;


export type ApiResp<T = unknown> = {
  success: boolean;
  message: string;
  data: T;
  error_code: string | null;
  timestamp: string;
};

export type PaginationMeta = components['schemas']['PaginationMeta'];

export type ApiError = components['schemas']['ApiError'];


export type User = MakeRequired<components['schemas']['UserResponse']>;

export type Room = MakeRequired<components['schemas']['RoomResponse']>;

export type Cabinet = MakeRequired<components['schemas']['CabinetResponse']>;

export type CabinetUtilization = MakeRequired<components['schemas']['CabinetUtilizationResponse']>;

export type Device = MakeRequired<components['schemas']['DeviceResponse']>;

export type DeviceNicPort = MakeRequired<components['schemas']['DeviceNicPortResponse']>;

export type DeviceConnection = MakeRequired<components['schemas']['DeviceConnectionResponse']>;

export type DeviceStorage = MakeRequired<components['schemas']['DeviceStorageResponse']>;

export type Customer = MakeRequired<components['schemas']['CustomerResponse']>;

export type IPAddress = MakeRequired<components['schemas']['IPAddressResponse']>;

export type IPAddressDetail = MakeRequired<components['schemas']['IPAddressDetailResponse']>;

export type Switch = MakeRequired<components['schemas']['SwitchResponse']>;

export type SwitchPort = MakeRequired<components['schemas']['SwitchPortResponse']>;

export type SwitchPortIP = MakeRequired<components['schemas']['SwitchPortIPResponse']>;

export type Permission = MakeRequired<components['schemas']['PermissionResponse']>;

export type Role = MakeRequired<components['schemas']['RoleResponse']>;

export type AuditLog = MakeRequired<components['schemas']['AuditLogResponse']>;

export type VLAN = MakeRequired<components['schemas']['VLANResponse']>;

export type LinkAggregationGroup = MakeRequired<components['schemas']['LinkAggregationGroupResponse']>;

export type IPNetwork = MakeRequired<components['schemas']['IPNetworkResponse']>;

export type DeviceConfigBackup = MakeRequired<components['schemas']['DeviceConfigBackupResponse']>;

export type DeviceConfigChange = MakeRequired<components['schemas']['DeviceConfigChangeResponse']>;

export type DashboardStats = MakeRequired<components['schemas']['DashboardStatsResponse']>;

export type LoginData = MakeRequired<components['schemas']['LoginDataResponse']>;

export type LoginUser = MakeRequired<components['schemas']['LoginUserResponse']>;

export type VerifyData = MakeRequired<components['schemas']['VerifyDataResponse']>;

export type SwitchCredential = MakeRequired<components['schemas']['SwitchCredentialEmbedded']> & {
  peer_port_names?: string[] | null;
};

export type PortSummary = MakeRequired<components['schemas']['PortSummaryEmbedded']>;


export type DeviceCreate = components['schemas']['DeviceCreate'];

export type DeviceUpdate = components['schemas']['DeviceUpdate'];

export type CabinetCreate = components['schemas']['CabinetCreate'];

export type CabinetUpdate = components['schemas']['CabinetUpdate'];

export type CustomerCreate = components['schemas']['CustomerCreate'];

export type CustomerUpdate = components['schemas']['CustomerUpdate'];

export type RoomCreate = components['schemas']['RoomCreate'];

export type RoomUpdate = components['schemas']['RoomUpdate'];

export type AuditLogQuery = components['schemas']['AuditLogQuery'];

export type VLANCreate = components['schemas']['VLANCreate'];

export type VLANUpdate = components['schemas']['VLANUpdate'];


export type TopologyNode = MakeRequired<components['schemas']['TopologyNode']>;
export type TopologyEdge = MakeRequired<components['schemas']['TopologyEdge']>;
export type TopologyStats = MakeRequired<components['schemas']['TopologyStats']>;
export type TopologyResponse = MakeRequired<components['schemas']['TopologyResponse']>;
export type TopologyAutoDetectChangeField = MakeRequired<components['schemas']['TopologyAutoDetectChangeField']>;
export type TopologyAutoDetectChange = MakeRequired<components['schemas']['TopologyAutoDetectChange']>;
export type TopologyAutoDetectResponse = MakeRequired<components['schemas']['TopologyAutoDetectResponse']>;


import type { paths } from './api-generated';

export type ApiPaths = paths;

export type GetResponse<
  Path extends keyof paths,
> = paths[Path] extends { get: { responses: { 200: { content: { 'application/json': infer R } } } } }
  ? R
  : never;

export type PostRequestBody<
  Path extends keyof paths,
> = paths[Path] extends { post: { requestBody: { content: { 'application/json': infer R } } } }
  ? R
  : never;

export type PostResponse<
  Path extends keyof paths,
> = paths[Path] extends { post: { responses: { 200: { content: { 'application/json': infer R } } } } }
  ? R
  : never;
