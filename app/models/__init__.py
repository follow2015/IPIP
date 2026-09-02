# -*- coding: utf-8 -*-
"""
数据模型包（本文件由 scripts/generate_model_init.py 自动生成，请勿手改）

新增 / 删除模型模块后运行 `make gen-models` 重新生成；CI 护栏测试会校验同步。
显式 import 让 IDE / pyright / mypy 可静态解析 app.models.X。
"""
from app.models.base import BaseModel

# AI 模型容错加载：deploy 无 AI 业务代码（ai_conversation/ai_diagnosis_session 被
# sync --with-ai 排除），缺失则跳过。主仓有则正常 import。
try:
    from app.models.ai_conversation import AIConversation
    from app.models.ai_diagnosis_session import AIDiagnosisSession
except ImportError:  # noqa: BLE001
    AIConversation = None  # type: ignore[assignment]
    AIDiagnosisSession = None  # type: ignore[assignment]
from app.models.audit_log import AuditLog
from app.models.cabinet import Cabinet
from app.models.component_template import ComponentTemplate
from app.models.customer import Customer
from app.models.customer_termination_archive import CustomerTerminationArchive
from app.models.device import Device
from app.models.device_asset import DeviceAsset
from app.models.device_config_backup import DeviceConfigBackup, DeviceConfigChange
from app.models.device_connection import DeviceConnection
from app.models.device_hardware import DeviceHardware
from app.models.device_metric_alert_state import DeviceMetricAlertState
from app.models.device_metric_baseline import DeviceMetricBaseline
from app.models.device_metric_latest import DeviceMetricLatest
from app.models.device_metric_override import DeviceMetricOverride
from app.models.device_metric_timeseries import DeviceMetricTimeseries
from app.models.device_monitor_probe_events import DeviceMonitorProbeEvents
from app.models.device_monitor_status import DeviceMonitorStatus
from app.models.device_monitor_timeseries_daily import DeviceMonitorTimeseriesDaily
from app.models.device_monitor_timeseries_hourly import DeviceMonitorTimeseriesHourly
from app.models.device_nics_port import DeviceNicsPort
from app.models.device_server_ext import DeviceServerExt
from app.models.device_storage import DeviceStorage
from app.models.device_switch_ext import DeviceSwitchExt
from app.models.ip_allocation_log import IPAllocationLog
from app.models.ip_model import IPBanRecord, IPManager
from app.models.link_aggregation import LinkAggregationGroup
from app.models.mail_setting import MailSetting
from app.models.monitor_alert_dependency_rule import MonitorAlertDependencyRule
from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.models.monitor_credential import DeviceMonitorCredential, MonitorCredential
from app.models.monitor_device_type_recommend import MonitorDeviceTypeRecommend
from app.models.monitor_dynamic_config import MonitorDynamicConfig
from app.models.monitor_escalation_policy import MonitorEscalationPolicy
from app.models.monitor_escalation_step import MonitorEscalationStep
from app.models.monitor_incident import MonitorIncident
from app.models.monitor_metric_template import MonitorMetricTemplate
from app.models.monitor_metric_template_group import MonitorMetricTemplateGroup, MonitorMetricTemplateGroupItem
from app.models.monitor_oid_category_rule import MonitorOidCategoryRule
from app.models.monitor_silence_rule import MonitorSilenceRule
from app.models.monitor_sla_target import MonitorSlaTarget
from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
from app.models.monitor_vendor_brand import MonitorVendorBrand
from app.models.network_connection import NetworkConnection
from app.models.network_port import NetworkPort
from app.models.notification import Notification, NotificationReceipt
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.room import Room
from app.models.switch_credentials import IPSwitchInfo, SwitchCredentials, SwitchPortIP, SwitchStatusCache
from app.models.switch_route import IPNetwork, SwitchRoute
from app.models.user import User
from app.models.user_log import UserLog
from app.models.virtual_room import VirtualRoom, VirtualRoomMember
from app.models.vlan import VLAN
from app.models.vlan_port_member import VLANPortMember
from app.models.voice_setting import VoiceSetting
from app.models.webhook_config import WebhookConfig

__all__ = [
    "BaseModel",
    "AIConversation",
    "AIDiagnosisSession",
    "AuditLog",
    "Cabinet",
    "ComponentTemplate",
    "Customer",
    "CustomerTerminationArchive",
    "Device",
    "DeviceAsset",
    "DeviceConfigBackup",
    "DeviceConfigChange",
    "DeviceConnection",
    "DeviceHardware",
    "DeviceMetricAlertState",
    "DeviceMetricBaseline",
    "DeviceMetricLatest",
    "DeviceMetricOverride",
    "DeviceMetricTimeseries",
    "DeviceMonitorCredential",
    "DeviceMonitorProbeEvents",
    "DeviceMonitorStatus",
    "DeviceMonitorTimeseriesDaily",
    "DeviceMonitorTimeseriesHourly",
    "DeviceNicsPort",
    "DeviceServerExt",
    "DeviceStorage",
    "DeviceSwitchExt",
    "IPAllocationLog",
    "IPBanRecord",
    "IPManager",
    "IPNetwork",
    "IPSwitchInfo",
    "LinkAggregationGroup",
    "MailSetting",
    "MonitorAlertDependencyRule",
    "MonitorAlertOutbox",
    "MonitorCredential",
    "MonitorDeviceTypeRecommend",
    "MonitorDynamicConfig",
    "MonitorEscalationPolicy",
    "MonitorEscalationStep",
    "MonitorIncident",
    "MonitorMetricTemplate",
    "MonitorMetricTemplateGroup",
    "MonitorMetricTemplateGroupItem",
    "MonitorOidCategoryRule",
    "MonitorSilenceRule",
    "MonitorSlaTarget",
    "MonitorSuppressedAlertLog",
    "MonitorVendorBrand",
    "NetworkConnection",
    "NetworkPort",
    "Notification",
    "NotificationReceipt",
    "Permission",
    "Role",
    "RolePermission",
    "Room",
    "SwitchCredentials",
    "SwitchPortIP",
    "SwitchRoute",
    "SwitchStatusCache",
    "User",
    "UserLog",
    "UserRole",
    "VLAN",
    "VLANPortMember",
    "VirtualRoom",
    "VirtualRoomMember",
    "VoiceSetting",
    "WebhookConfig",
]
