import type { TFunction } from 'i18next';

import type {
  AuthMethodKey,
  CabinetStatusKey,
  ChannelKey,
  ConnectionStatusKey,
  CustomerStatusKey,
  DeviceStatusKey,
  DeviceSubtypeKey,
  DeviceTypeKey,
  IPAuditActionKey,
  IPStatusKey,
  LAGStatusKey,
  LinkStatusKey,
  LoginTypeKey,
  NetworkLayerKey,
  NodeStatusKey,
  NotificationGroupKey,
  NotificationTypeKey,
  PortUsageStatusKey,
  ProbeErrorKey,
  RoomStatusKey,
  RouteNoteKey,
  SeverityKey,
  SwitchDeviceTypeKey,
  SwitchRoleKey,
  UserStatusKey,
  VLANStatusKey
} from './enums';

import {
  CABINET_STATUS_MAP,
  CONNECTION_STATUS_MAP,
  CUSTOMER_STATUS_MAP,
  DEVICE_STATUS_MAP,
  DEVICE_SUBTYPE_LABEL_KEYS,
  DEVICE_TYPE_MAP,
  IP_AUDIT_ACTION_MAP,
  IP_STATUS_MAP,
  LAG_STATUS_MAP,
  LINK_STATUS_MAP,
  LOGIN_TYPE_MAP,
  NODE_STATUS_MAP,
  PORT_USAGE_STATUS_MAP,
  PROBE_ERROR_MAP,
  ROOM_STATUS_MAP,
  ROUTE_NOTES_MAP,
  SEVERITY_LABEL_KEYS,
  SWITCH_ROLE_MAP,
  USER_STATUS_MAP,
  VLAN_STATUS_MAP,
  AUTH_METHOD_LABEL_KEYS,
  BROADCAST_CHANNELS,
  CHANNEL_LABEL_KEYS,
  NETWORK_LAYER_LABEL_KEYS,
  NOTIFICATION_TYPE_GROUPS,
  NOTIFICATION_TYPE_LABEL_KEYS,
  SWITCH_DEVICE_TYPE_LABEL_KEYS,
  CabinetStatusCode,
  CustomerStatusCode,
  DeviceStatusCode,
  DeviceSubtype,
  DeviceType,
  IPAuditAction,
  IPStatusCode,
  LAGStatusCode,
  ProbeErrorCode,
  RoomStatusCode,
  RouteNotesCode,
  SwitchDeviceType,
  SwitchRoleCode,
  UserStatusCode,
  VLANStatusCode
} from './enums';

export type DeviceT = TFunction<'device'>;

export type StatusLabelKey =
  | AuthMethodKey
  | CabinetStatusKey
  | ChannelKey
  | ConnectionStatusKey
  | CustomerStatusKey
  | DeviceStatusKey
  | DeviceSubtypeKey
  | DeviceTypeKey
  | IPAuditActionKey
  | IPStatusKey
  | LAGStatusKey
  | LinkStatusKey
  | LoginTypeKey
  | NetworkLayerKey
  | NodeStatusKey
  | NotificationGroupKey
  | NotificationTypeKey
  | PortUsageStatusKey
  | ProbeErrorKey
  | RoomStatusKey
  | RouteNoteKey
  | SeverityKey
  | SwitchDeviceTypeKey
  | SwitchRoleKey
  | UserStatusKey
  | VLANStatusKey;

export interface StatusMeta {
  label: string;
  color: string;
}

export const getDeviceStatusMeta = (
  code: DeviceStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = DEVICE_STATUS_MAP[code as DeviceStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getDeviceStatusOptions = (t: DeviceT) =>
  Object.entries(DEVICE_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getDeviceStatusEntries = (t: DeviceT) =>
  Object.entries(DEVICE_STATUS_MAP).map(([code, entry]) => ({
    code: Number(code),
    label: t(entry.labelKey),
    color: entry.color
  }));

export const getDeviceTypeMeta = (
  code: DeviceType | string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = DEVICE_TYPE_MAP[code as DeviceType];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getDeviceTypeOptions = (t: DeviceT) =>
  Object.entries(DEVICE_TYPE_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value
  }));

export const getDeviceSubtypeLabel = (
  subtype: DeviceSubtype | string | null | undefined,
  t: DeviceT
): string | undefined => {
  if (subtype == null) return undefined;
  const key = DEVICE_SUBTYPE_LABEL_KEYS[subtype as DeviceSubtype];
  return key ? t(key) : undefined;
};

export const getDeviceSubtypeOptions = (subtypes: DeviceSubtype[], t: DeviceT) =>
  subtypes.map((subtype) => ({
    label: getDeviceSubtypeLabel(subtype, t) ?? subtype,
    value: subtype
  }));

export const getIPStatusMeta = (
  code: IPStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = IP_STATUS_MAP[code as IPStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getIPStatusOptions = (t: DeviceT) =>
  Object.entries(IP_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getRouteNoteMeta = (
  code: RouteNotesCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = ROUTE_NOTES_MAP[Number(code)];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getRouteNoteOptions = (t: DeviceT) =>
  Object.entries(ROUTE_NOTES_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getSwitchRoleMeta = (
  code: SwitchRoleCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = SWITCH_ROLE_MAP[code as SwitchRoleCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getSwitchRoleOptions = (t: DeviceT) =>
  Object.entries(SWITCH_ROLE_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getSwitchDeviceTypeOptions = (t: DeviceT) =>
  Object.entries(SWITCH_DEVICE_TYPE_LABEL_KEYS).map(([value, key]) => ({
    label: t(key),
    value
  }));

export const getCustomerStatusMeta = (
  code: CustomerStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = CUSTOMER_STATUS_MAP[code as CustomerStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getCustomerStatusOptions = (t: DeviceT) =>
  Object.entries(CUSTOMER_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getRoomStatusMeta = (
  code: RoomStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = ROOM_STATUS_MAP[code as RoomStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getRoomStatusOptions = (t: DeviceT) =>
  Object.entries(ROOM_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getCabinetStatusMeta = (
  code: CabinetStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = CABINET_STATUS_MAP[code as CabinetStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getCabinetStatusOptions = (t: DeviceT) =>
  Object.entries(CABINET_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getVlanStatusMeta = (
  code: VLANStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = VLAN_STATUS_MAP[Number(code)];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getVlanStatusOptions = (t: DeviceT) =>
  Object.entries(VLAN_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getUserStatusMeta = (
  code: UserStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = USER_STATUS_MAP[code as UserStatusCode];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getUserStatusOptions = (t: DeviceT) =>
  Object.entries(USER_STATUS_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value: Number(value)
  }));

export const getLagStatusMeta = (
  code: LAGStatusCode | number | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = LAG_STATUS_MAP[Number(code)];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getPortUsageMeta = (
  code: string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = PORT_USAGE_STATUS_MAP[code];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getPortUsageLegend = (t: DeviceT) =>
  Object.entries(PORT_USAGE_STATUS_MAP).map(([value, entry]) => ({
    value,
    label: t(entry.labelKey),
    color: entry.color
  }));

export const getLinkStatusMeta = (
  code: string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = LINK_STATUS_MAP[code];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getNodeStatusMeta = (
  code: string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = NODE_STATUS_MAP[code];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getConnectionStatusMeta = (
  code: string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = CONNECTION_STATUS_MAP[code];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getProbeErrorMeta = (
  code: ProbeErrorCode | string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = PROBE_ERROR_MAP[code as ProbeErrorCode];
  return entry ? { label: (t as (k: string) => string)(entry.labelKey), color: entry.color } : undefined;
};

export const getIPAuditActionMeta = (
  code: IPAuditAction | string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = IP_AUDIT_ACTION_MAP[code as IPAuditAction];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getIPAuditActionOptions = (t: DeviceT) =>
  Object.entries(IP_AUDIT_ACTION_MAP).map(([value, entry]) => ({
    label: t(entry.labelKey),
    value
  }));

export const getLoginTypeMeta = (
  code: string | null | undefined,
  t: DeviceT
): StatusMeta | undefined => {
  if (code == null) return undefined;
  const entry = LOGIN_TYPE_MAP[code];
  return entry ? { label: t(entry.labelKey), color: entry.color } : undefined;
};

export const getSeverityLabel = (
  code: string | null | undefined,
  t: DeviceT
): string | undefined => {
  if (code == null) return undefined;
  const key = SEVERITY_LABEL_KEYS[code];
  return key ? t(key) : undefined;
};

export const getSeverityOptions = (t: DeviceT) =>
  Object.entries(SEVERITY_LABEL_KEYS).map(([value, key]) => ({
    label: t(key),
    value
  }));

export const getChannelLabel = (
  code: string | null | undefined,
  t: DeviceT
): string | undefined => {
  if (code == null) return undefined;
  const key = CHANNEL_LABEL_KEYS[code];
  return key ? t(key) : undefined;
};

export const getBroadcastChannelOptions = (t: DeviceT) =>
  BROADCAST_CHANNELS.map((value) => ({
    label: getChannelLabel(value, t) ?? value,
    value
  }));

export const getAuthMethodOptions = (t: DeviceT) =>
  Object.entries(AUTH_METHOD_LABEL_KEYS).map(([value, key]) => ({
    label: t(key),
    value
  }));

export const getNetworkLayerOptions = (t: DeviceT) =>
  Object.entries(NETWORK_LAYER_LABEL_KEYS).map(([value, key]) => ({
    label: t(key),
    value: Number(value)
  }));

export const getNotificationTypeOptions = (t: DeviceT) =>
  Object.entries(NOTIFICATION_TYPE_LABEL_KEYS).map(([value, key]) => ({
    label: t(key),
    value
  }));

export const getNotificationTypeGroupOptions = (t: DeviceT) =>
  NOTIFICATION_TYPE_GROUPS.map((group) => ({
    label: t(group.groupKey),
    options: group.types.map((type) => ({
      label: t(NOTIFICATION_TYPE_LABEL_KEYS[type]),
      value: type
    }))
  }));
