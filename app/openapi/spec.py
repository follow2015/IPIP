# -*- coding: utf-8 -*-
"""APISpec 实例配置与 Schema 注册

提供全局 APISpec 实例，注册 Marshmallow Schema 和通用响应组件。
各路由模块通过 add_path() 注册端点信息。
"""
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin


def create_spec() -> APISpec:
    spec = APISpec(
        title="IPIP 管理 API",
        version="2.1.0",
        openapi_version="3.0.3",
        info={
            "description": "IP/IP 地址管理系统 RESTful API",
            "contact": {"name": "IPIP Dev Team"},
        },
        plugins=[MarshmallowPlugin()],
        security_schemes={
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        },
    )
    _register_common_schemas(spec)
    return spec


def _register_common_schemas(spec: APISpec):
    spec.components.schema("PaginationMeta", component={
        "type": "object",
        "properties": {
            "page": {"type": "integer", "example": 1},
            "per_page": {"type": "integer", "example": 20},
            "total": {"type": "integer", "example": 100},
            "total_pages": {"type": "integer", "example": 5},
        },
        "required": ["page", "per_page", "total", "total_pages"],
    })
    spec.components.schema("ApiError", component={
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "example": False},
            "message": {"type": "string"},
            "error_code": {"type": "string"},
            "timestamp": {"type": "string"},
        },
        "required": ["success", "message"],
    })


def register_marshmallow_schemas(spec: APISpec):
    from app.api.device import DeviceCreateSchema, DeviceUpdateSchema
    from app.api.device import (
        BatchUpdateAssetSchema, BatchResetAssetSchema,
        BatchDeleteSchema, BatchUpdateDeviceStatusSchema,
        BatchUpdateHardwareSchema, DeviceStatusUpdateSchema,
        DeviceLocationUpdateSchema, SerialNumberGenerateSchema,
        SerialNumberCheckSchema, NodePositionCheckSchema,
        SwitchPortUpdateSchema, BatchCreateSwitchPortsSchema,
        BatchCreateDevicesSchema, DeviceVLANCreateSchema,
        VLANMemberUpdateSchema, VLANFieldUpdateSchema,
        LAGCreateSchema, LAGMemberUpdateSchema, LAGFieldUpdateSchema,
    )
    from app.api.cabinet import (
        CabinetCreateSchema, CabinetUpdateSchema,
        UPositionCheckSchema, UAssignSchema, SmartUAssignSchema,
        CabinetCapacityValidateSchema, CabinetOptimizeSchema,
        CabinetCustomerUpdateSchema,
    )
    from app.api.customer import CustomerCreateSchema, CustomerUpdateSchema
    from app.api.room import RoomCreateSchema, RoomUpdateSchema
    from app.api.device_connection import DeviceConnectionCreateSchema, DeviceConnectionUpdateSchema
    from app.api.device_config import ConfigChangeRequestSchema
    from app.api.device_nics_port import NicPortBatchSchema, NicPortIncrementalBatchSchema, NicPortUpdateSchema
    from app.api.device_storage import (
        StorageAddSchema, StorageOverwriteSchema,
        StorageUpdateSchema, StorageSerialCheckSchema,
    )
    from app.api.auth import LoginSchema, QRCodeConfirmSchema, QRCodeCompleteSchema
    from app.api.audit import AuditLogQuerySchema
    from app.api.vlan import VLANCreateSchema, VLANUpdateSchema
    from app.api.virtual_room_routes import VirtualRoomCreateSchema, VirtualRoomUpdateSchema, VirtualRoomMembersSchema
    from app.api.user import (
        UserLoginSchema, UserRegisterSchema, RefreshTokenSchema,
        UserUpdateRequestSchema, ChangePasswordSchema, ResetPasswordSchema,
    )
    from app.schemas.monitor import MonitorCredentialUpsertSchema
    from app.openapi.schemas import (
        MonitorCredentialListItemSchema,
        MonitorCredentialCreateSchema,
    )

    request_schema_map = {
        "DeviceCreate": DeviceCreateSchema,
        "DeviceUpdate": DeviceUpdateSchema,
        "BatchUpdateAsset": BatchUpdateAssetSchema,
        "BatchResetAsset": BatchResetAssetSchema,
        "BatchDelete": BatchDeleteSchema,
        "BatchUpdateDeviceStatus": BatchUpdateDeviceStatusSchema,
        "BatchUpdateHardware": BatchUpdateHardwareSchema,
        "DeviceStatusUpdate": DeviceStatusUpdateSchema,
        "DeviceLocationUpdate": DeviceLocationUpdateSchema,
        "SerialNumberGenerate": SerialNumberGenerateSchema,
        "SerialNumberCheck": SerialNumberCheckSchema,
        "NodePositionCheck": NodePositionCheckSchema,
        "SwitchPortUpdate": SwitchPortUpdateSchema,
        "BatchCreateSwitchPorts": BatchCreateSwitchPortsSchema,
        "BatchCreateDevices": BatchCreateDevicesSchema,
        "DeviceVLANCreate": DeviceVLANCreateSchema,
        "VLANMemberUpdate": VLANMemberUpdateSchema,
        "VLANFieldUpdate": VLANFieldUpdateSchema,
        "LAGCreate": LAGCreateSchema,
        "LAGMemberUpdate": LAGMemberUpdateSchema,
        "LAGFieldUpdate": LAGFieldUpdateSchema,
        "CabinetCreate": CabinetCreateSchema,
        "CabinetUpdate": CabinetUpdateSchema,
        "UPositionCheck": UPositionCheckSchema,
        "UAssign": UAssignSchema,
        "SmartUAssign": SmartUAssignSchema,
        "CabinetCapacityValidate": CabinetCapacityValidateSchema,
        "CabinetOptimize": CabinetOptimizeSchema,
        "CabinetCustomerUpdate": CabinetCustomerUpdateSchema,
        "CustomerCreate": CustomerCreateSchema,
        "CustomerUpdate": CustomerUpdateSchema,
        "RoomCreate": RoomCreateSchema,
        "RoomUpdate": RoomUpdateSchema,
        "DeviceConnectionCreate": DeviceConnectionCreateSchema,
        "DeviceConnectionUpdate": DeviceConnectionUpdateSchema,
        "ConfigChangeRequest": ConfigChangeRequestSchema,
        "NicPortBatch": NicPortBatchSchema,
        "NicPortIncrementalBatch": NicPortIncrementalBatchSchema,
        "NicPortUpdate": NicPortUpdateSchema,
        "StorageAdd": StorageAddSchema,
        "StorageOverwrite": StorageOverwriteSchema,
        "StorageUpdate": StorageUpdateSchema,
        "StorageSerialCheck": StorageSerialCheckSchema,
        "Login": LoginSchema,
        "QRCodeConfirm": QRCodeConfirmSchema,
        "QRCodeComplete": QRCodeCompleteSchema,
        "AuditLogQuery": AuditLogQuerySchema,
        "VLANCreate": VLANCreateSchema,
        "VLANUpdate": VLANUpdateSchema,
        "VirtualRoomCreate": VirtualRoomCreateSchema,
        "VirtualRoomUpdate": VirtualRoomUpdateSchema,
        "VirtualRoomMembers": VirtualRoomMembersSchema,
        "UserLogin": UserLoginSchema,
        "UserRegister": UserRegisterSchema,
        "RefreshToken": RefreshTokenSchema,
        "UserUpdateRequest": UserUpdateRequestSchema,
        "ChangePassword": ChangePasswordSchema,
        "ResetPassword": ResetPasswordSchema,
        "MonitorCredentialUpsert": MonitorCredentialUpsertSchema,
        "MonitorCredentialCreate": MonitorCredentialCreateSchema,
    }
    for name, schema_cls in request_schema_map.items():
        spec.components.schema(name, schema=schema_cls())

    from app.openapi.schemas import (
        UserResponseSchema,
        LoginDataResponseSchema,
        LoginUserResponseSchema,
        VerifyDataResponseSchema,
        RoomResponseSchema,
        CabinetResponseSchema,
        CabinetUtilizationResponseSchema,
        DeviceResponseSchema,
        DeviceNicPortResponseSchema,
        DeviceConnectionResponseSchema,
        DeviceStorageResponseSchema,
        CustomerResponseSchema,
        IPAddressResponseSchema,
        IPAddressDetailResponseSchema,
        SwitchResponseSchema,
        SwitchPortResponseSchema,
        SwitchPortIPResponseSchema,
        PermissionResponseSchema,
        RoleResponseSchema,
        AuditLogResponseSchema,
        VLANResponseSchema,
        LinkAggregationGroupResponseSchema,
        IPNetworkResponseSchema,
        DeviceConfigBackupResponseSchema,
        DeviceConfigChangeResponseSchema,
        DashboardStatsResponseSchema,
        TopologyNodeSchema,
        TopologyEdgeSchema,
        TopologyStatsSchema,
        TopologyResponseSchema,
        TopologyAutoDetectChangeFieldSchema,
        TopologyAutoDetectChangeSchema,
        TopologyAutoDetectResponseSchema,
        VirtualRoomResponseSchema,
        ApiResponseSchema,
        ApiErrorResponseSchema,
        PaginationMetaSchema,
        MonitorStatusResponseSchema,
        DeviceMonitorStatusResponseSchema,
        MonitorCredentialConfigResponseSchema,
        MonitorCredentialDeleteResponseSchema,
        MonitorProbeResultResponseSchema,
        MonitorCredentialPatchResponseSchema,
        MonitorOverviewResponseSchema,
        MonitorOverviewRecentAlertSchema,
        MonitorStatusListResponseSchema,
        MonitorStatusListItemSchema,
        MonitorConfigResponseSchema,
        MonitorConfigItemSchema,
        MonitorConfigUpdateResponseSchema,
        MonitorCheckBatchResponseSchema,
        MonitorCredentialPayloadUpdateResponseSchema,
        MonitorAlertListItemSchema,
        MonitorAlertListResponseSchema,
        MonitorAlertRetryResponseSchema,
        MonitorAlertAckResponseSchema,
        MonitorAlertDetailSchema,
        MonitorAlertBatchAckRequestSchema,
        MonitorAlertBatchAckResponseSchema,
        MonitorAlertBatchRetryRequestSchema,
        MonitorAlertBatchRetryResponseSchema,
        MonitorAlertCloseResponseSchema,
        MonitorAlertBatchCloseRequestSchema,
        MonitorAlertBatchCloseResponseSchema,
        MonitorAlertAggregationItemSchema,
        MonitorAlertAggregationResponseSchema,
        MonitorDeviceMonitorEnabledResponseSchema,
        MonitorProbeHistoryItemSchema,
        MonitorProbeHistoryResponseSchema,
        MonitorProbeTrendsResponseSchema,
        DeviceMetricAlertStateItemSchema,
        DeviceMetricAlertListResponseSchema,
        MetricTemplateItemSchema,
        MetricTemplateListResponseSchema,
        MetricTemplateUpsertResponseSchema,
        MetricTemplateSeedResponseSchema,
        MetricTemplateDeleteResponseSchema,
        DeviceTrafficResponseSchema,
        DeviceTrafficPortItemSchema,
        DeviceTrafficPortsResponseSchema,
        OidCategoryRuleItemSchema,
        OidCategoryRuleListResponseSchema,
        OidCategoryRuleMutationResponseSchema,
        DeviceTypeRecommendItemSchema,
        DeviceTypeRecommendListResponseSchema,
        RecommendConfigResponseSchema,
        VendorBrandItemSchema,
        VendorBrandListResponseSchema,
        VendorBrandMutationResponseSchema,
        MonitorSilenceRuleItemSchema,
        MonitorAlertDependencyRuleItemSchema,
        MonitorSlaTargetItemSchema,
        MonitorSlaAchievementSchema,
        MonitorEscalationPolicyItemSchema,
        MonitorEscalationStepItemSchema,
        MonitorAlertStatisticsResponseSchema,
        DeviceMetricOverrideItemSchema,
        MibScanResponseSchema,
        MetricTemplateGroupItemSchema,
        MetricTemplateGroupListResponseSchema,
        MetricTemplateGroupDetailResponseSchema,
        MetricTemplateGroupMutationResponseSchema,
        DeviceMetricLatestItemSchema,
        DeviceMetricLatestListResponseSchema,
        DeviceMetricHistoryItemSchema,
        DeviceMetricHistoryResponseSchema,
        DeviceMetricKeysResponseSchema,
        DeviceMetricDashboardItemSchema,
        DeviceMetricDashboardResponseSchema,
        DevicePortSyncEnabledResponseSchema,
        DevicePortSyncEnabledUpdateResponseSchema,
        DeviceBatchPortSyncEnabledResponseSchema,
    )

    response_schema_map = {
        "UserResponse": UserResponseSchema,
        "LoginDataResponse": LoginDataResponseSchema,
        "LoginUserResponse": LoginUserResponseSchema,
        "VerifyDataResponse": VerifyDataResponseSchema,
        "RoomResponse": RoomResponseSchema,
        "CabinetResponse": CabinetResponseSchema,
        "CabinetUtilizationResponse": CabinetUtilizationResponseSchema,
        "DeviceResponse": DeviceResponseSchema,
        "DeviceNicPortResponse": DeviceNicPortResponseSchema,
        "DeviceConnectionResponse": DeviceConnectionResponseSchema,
        "DeviceStorageResponse": DeviceStorageResponseSchema,
        "CustomerResponse": CustomerResponseSchema,
        "IPAddressResponse": IPAddressResponseSchema,
        "IPAddressDetailResponse": IPAddressDetailResponseSchema,
        "SwitchResponse": SwitchResponseSchema,
        "SwitchPortResponse": SwitchPortResponseSchema,
        "SwitchPortIPResponse": SwitchPortIPResponseSchema,
        "PermissionResponse": PermissionResponseSchema,
        "RoleResponse": RoleResponseSchema,
        "AuditLogResponse": AuditLogResponseSchema,
        "VLANResponse": VLANResponseSchema,
        "LinkAggregationGroupResponse": LinkAggregationGroupResponseSchema,
        "IPNetworkResponse": IPNetworkResponseSchema,
        "DeviceConfigBackupResponse": DeviceConfigBackupResponseSchema,
        "DeviceConfigChangeResponse": DeviceConfigChangeResponseSchema,
        "DashboardStatsResponse": DashboardStatsResponseSchema,
        "TopologyNode": TopologyNodeSchema,
        "TopologyEdge": TopologyEdgeSchema,
        "TopologyStats": TopologyStatsSchema,
        "TopologyResponse": TopologyResponseSchema,
        "TopologyAutoDetectChangeField": TopologyAutoDetectChangeFieldSchema,
        "TopologyAutoDetectChange": TopologyAutoDetectChangeSchema,
        "TopologyAutoDetectResponse": TopologyAutoDetectResponseSchema,
        "VirtualRoomResponse": VirtualRoomResponseSchema,
        "ApiResponse": ApiResponseSchema,
        "ApiError": ApiErrorResponseSchema,
        "PaginationMetaResponse": PaginationMetaSchema,
        "MonitorStatusResponse": MonitorStatusResponseSchema,
        "DeviceMonitorStatusResponse": DeviceMonitorStatusResponseSchema,
        "MonitorCredentialConfigResponse": MonitorCredentialConfigResponseSchema,
        "MonitorCredentialDeleteResponse": MonitorCredentialDeleteResponseSchema,
        "MonitorProbeResultResponse": MonitorProbeResultResponseSchema,
        "MonitorCredentialListItem": MonitorCredentialListItemSchema,
        "MonitorCredentialPatchResponse": MonitorCredentialPatchResponseSchema,
        "MonitorOverviewResponse": MonitorOverviewResponseSchema,
        "MonitorOverviewRecentAlert": MonitorOverviewRecentAlertSchema,
        "MonitorStatusListResponse": MonitorStatusListResponseSchema,
        "MonitorStatusListItem": MonitorStatusListItemSchema,
        "MonitorConfigResponse": MonitorConfigResponseSchema,
        "MonitorConfigItem": MonitorConfigItemSchema,
        "MonitorConfigUpdateResponse": MonitorConfigUpdateResponseSchema,
        "MonitorCheckBatchResponse": MonitorCheckBatchResponseSchema,
        "MonitorCredentialPayloadUpdateResponse": MonitorCredentialPayloadUpdateResponseSchema,
        "MonitorAlertListItem": MonitorAlertListItemSchema,
        "MonitorAlertListResponse": MonitorAlertListResponseSchema,
        "MonitorAlertRetryResponse": MonitorAlertRetryResponseSchema,
        "MonitorAlertAckResponse": MonitorAlertAckResponseSchema,
        "MonitorAlertDetail": MonitorAlertDetailSchema,
        "MonitorAlertBatchAckRequest": MonitorAlertBatchAckRequestSchema,
        "MonitorAlertBatchAckResponse": MonitorAlertBatchAckResponseSchema,
        "MonitorAlertBatchRetryRequest": MonitorAlertBatchRetryRequestSchema,
        "MonitorAlertBatchRetryResponse": MonitorAlertBatchRetryResponseSchema,
        "MonitorAlertCloseResponse": MonitorAlertCloseResponseSchema,
        "MonitorAlertBatchCloseRequest": MonitorAlertBatchCloseRequestSchema,
        "MonitorAlertBatchCloseResponse": MonitorAlertBatchCloseResponseSchema,
        "MonitorAlertAggregationItem": MonitorAlertAggregationItemSchema,
        "MonitorAlertAggregationResponse": MonitorAlertAggregationResponseSchema,
        "MonitorDeviceMonitorEnabledResponse": MonitorDeviceMonitorEnabledResponseSchema,
        "MonitorProbeHistoryItem": MonitorProbeHistoryItemSchema,
        "MonitorProbeHistoryResponse": MonitorProbeHistoryResponseSchema,
        "MonitorProbeTrendsResponse": MonitorProbeTrendsResponseSchema,
        "DeviceMetricAlertStateItem": DeviceMetricAlertStateItemSchema,
        "DeviceMetricAlertListResponse": DeviceMetricAlertListResponseSchema,
        "MetricTemplateItem": MetricTemplateItemSchema,
        "MetricTemplateListResponse": MetricTemplateListResponseSchema,
        "MetricTemplateUpsertResponse": MetricTemplateUpsertResponseSchema,
        "MetricTemplateSeedResponse": MetricTemplateSeedResponseSchema,
        "MetricTemplateDeleteResponse": MetricTemplateDeleteResponseSchema,
        "DeviceTrafficResponse": DeviceTrafficResponseSchema,
        "DeviceTrafficPortItem": DeviceTrafficPortItemSchema,
        "DeviceTrafficPortsResponse": DeviceTrafficPortsResponseSchema,
        "OidCategoryRuleItem": OidCategoryRuleItemSchema,
        "OidCategoryRuleListResponse": OidCategoryRuleListResponseSchema,
        "OidCategoryRuleMutationResponse": OidCategoryRuleMutationResponseSchema,
        "DeviceTypeRecommendItem": DeviceTypeRecommendItemSchema,
        "DeviceTypeRecommendListResponse": DeviceTypeRecommendListResponseSchema,
        "RecommendConfigResponse": RecommendConfigResponseSchema,
        "VendorBrandListResponse": VendorBrandListResponseSchema,
        "VendorBrandMutationResponse": VendorBrandMutationResponseSchema,
        "MonitorSilenceRuleItem": MonitorSilenceRuleItemSchema,
        "MonitorAlertDependencyRuleItem": MonitorAlertDependencyRuleItemSchema,
        "MonitorSlaTargetItem": MonitorSlaTargetItemSchema,
        "MonitorSlaAchievement": MonitorSlaAchievementSchema,
        "MonitorEscalationPolicyItem": MonitorEscalationPolicyItemSchema,
        "MonitorEscalationStepItem": MonitorEscalationStepItemSchema,
        "MonitorAlertStatisticsResponse": MonitorAlertStatisticsResponseSchema,
        "DeviceMetricOverrideItem": DeviceMetricOverrideItemSchema,
        "MibScanResponse": MibScanResponseSchema,
        "MetricTemplateGroupItem": MetricTemplateGroupItemSchema,
        "MetricTemplateGroupListResponse": MetricTemplateGroupListResponseSchema,
        "MetricTemplateGroupDetailResponse": MetricTemplateGroupDetailResponseSchema,
        "MetricTemplateGroupMutationResponse": MetricTemplateGroupMutationResponseSchema,
        "DeviceMetricLatestItem": DeviceMetricLatestItemSchema,
        "DeviceMetricLatestListResponse": DeviceMetricLatestListResponseSchema,
        "DeviceMetricHistoryItem": DeviceMetricHistoryItemSchema,
        "DeviceMetricHistoryResponse": DeviceMetricHistoryResponseSchema,
        "DeviceMetricKeysResponse": DeviceMetricKeysResponseSchema,
        "DeviceMetricDashboardItem": DeviceMetricDashboardItemSchema,
        "DeviceMetricDashboardResponse": DeviceMetricDashboardResponseSchema,
        "DevicePortSyncEnabledResponse": DevicePortSyncEnabledResponseSchema,
        "DevicePortSyncEnabledUpdateResponse": DevicePortSyncEnabledUpdateResponseSchema,
        "DeviceBatchPortSyncEnabledResponse": DeviceBatchPortSyncEnabledResponseSchema,
    }
    for name, schema_cls in response_schema_map.items():
        try:
            spec.components.schema(name, schema=schema_cls())
        except Exception:
            pass

    spec.components.schema("LinkedDevicesResponse", component={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "device_id": {"type": "integer"},
                "device_name": {"type": "string"},
                "device_type": {"type": ["string", "null"]},
                "management_ip": {"type": ["string", "null"]},
            },
        },
    })


_spec_instance: APISpec | None = None


def get_spec() -> APISpec:
    global _spec_instance
    if _spec_instance is None:
        _spec_instance = create_spec()
        register_marshmallow_schemas(_spec_instance)
    return _spec_instance
