# -*- coding: utf-8 -*-
"""指标模板仓库（MonitorMetricTemplateRepository）

提供指标模板的查询/管理能力：
- 按设备类型查询启用模板（worker 指标采集驱动）
- 模板 CRUD（管理接口）
- 内置默认模板种子（temperature / port_updown / disk_failure / raid_failure）

阈值覆盖说明：本仓库只维护「全局默认阈值」层。设备级/端口级覆盖由
``device_metric_overrides`` 表承担（本里程碑预留，见 MetricThresholdService）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_metric_template import MonitorMetricTemplate


class MonitorMetricTemplateRepository:

    def __init__(self, session=None):
        self.session = session or db.session


    def find_enabled_by_device_type(self, device_type: str, vendor: str | None = None) -> List[MonitorMetricTemplate]:
        q = (
            self.session.query(MonitorMetricTemplate)
            .filter(
                MonitorMetricTemplate.device_type == device_type,
                MonitorMetricTemplate.enabled.is_(True),
            )
        )
        if vendor is not None:
            from sqlalchemy import or_
            q = q.filter(
                or_(
                    MonitorMetricTemplate.vendor.is_(None),
                    MonitorMetricTemplate.vendor == vendor,
                )
            )
        return q.order_by(MonitorMetricTemplate.id.asc()).all()

    def find_by_id(self, template_id: int) -> Optional[MonitorMetricTemplate]:
        return self.session.get(MonitorMetricTemplate, template_id)

    def add(self, tpl: MonitorMetricTemplate) -> MonitorMetricTemplate:
        self.session.add(tpl)
        self.session.flush()
        return tpl

    def find_by_metric_key(self, metric_key: str, device_type: str = None) -> Optional[MonitorMetricTemplate]:
        q = self.session.query(MonitorMetricTemplate).filter(
            MonitorMetricTemplate.metric_key == metric_key
        )
        if device_type:
            q = q.filter(MonitorMetricTemplate.device_type == device_type)
        return q.first()

    def flush(self) -> None:
        self.session.flush()

    def list_all(self) -> List[MonitorMetricTemplate]:
        return self.session.query(MonitorMetricTemplate).order_by(
            MonitorMetricTemplate.device_type.asc(), MonitorMetricTemplate.metric_key.asc()
        ).all()


    def upsert(
        self,
        device_type: str,
        metric_key: str,
        *,
        source: str = "snmp",
        vendor: Optional[str] = None,
        category: Optional[str] = None,
        display_name: Optional[str] = None,
        mib: Optional[str] = None,
        oid_symbol: Optional[str] = None,
        oid: Optional[str] = None,
        zabbix_item_key: Optional[str] = None,
        index_kind: Optional[str] = None,
        metric_type: str = "gauge",
        unit: Optional[str] = None,
        poll_interval: int = 60,
        threshold: Optional[dict] = None,
        severity_default: Optional[str] = None,
        enabled: bool = True,
        description: Optional[str] = None,
        runbook_url: Optional[str] = None,
        runbook_title: Optional[str] = None,
    ) -> MonitorMetricTemplate:
        tpl = (
            self.session.query(MonitorMetricTemplate)
            .filter(
                MonitorMetricTemplate.device_type == device_type,
                MonitorMetricTemplate.metric_key == metric_key,
                MonitorMetricTemplate.vendor == vendor,
            )
            .first()
        )
        if tpl is None:
            tpl = MonitorMetricTemplate(
                device_type=device_type,
                metric_key=metric_key,
            )
            self.session.add(tpl)
        tpl.source = source
        tpl.vendor = vendor
        tpl.category = category
        tpl.display_name = display_name
        tpl.mib = mib
        tpl.oid_symbol = oid_symbol
        tpl.oid = oid
        tpl.zabbix_item_key = zabbix_item_key
        tpl.index_kind = index_kind
        tpl.metric_type = metric_type
        tpl.unit = unit
        tpl.poll_interval = poll_interval
        tpl.threshold = threshold
        tpl.severity_default = severity_default
        tpl.enabled = enabled
        tpl.description = description
        tpl.runbook_url = runbook_url
        tpl.runbook_title = runbook_title
        self.session.flush()
        return tpl

    def delete(self, template_id: int) -> bool:
        tpl = self.find_by_id(template_id)
        if tpl is None:
            return False
        self.session.delete(tpl)
        self.session.flush()
        return True

    def batch_delete(self, template_ids: list[int]) -> int:
        if not template_ids:
            return 0
        deleted = (
            self.session.query(MonitorMetricTemplate)
            .filter(MonitorMetricTemplate.id.in_(template_ids))
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted

    def batch_set_enabled(self, template_ids: list[int], enabled: bool) -> int:
        if not template_ids:
            return 0
        updated = (
            self.session.query(MonitorMetricTemplate)
            .filter(MonitorMetricTemplate.id.in_(template_ids))
            .update({MonitorMetricTemplate.enabled: enabled}, synchronize_session=False)
        )
        self.session.flush()
        return updated


    @staticmethod
    def default_seed_specs() -> List[dict]:
        return [
            {
                "device_type": "network",
                "metric_key": "if_status",
                "category": "if_status",
                "display_name": "端口状态",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifOperStatus",
                "oid": "1.3.6.1.2.1.2.2.1.8",
                "index_kind": "ifIndex",
                "metric_type": "state",
                "threshold": {"expected": "up"},
                "severity_default": "warn",
                "description": "交换机端口 up/down 状态（按订阅端口监控）",
            },
            {
                "device_type": "network",
                "metric_key": "if_in_octets",
                "category": "if_in_octets",
                "display_name": "入流量",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifInOctets",
                "oid": "1.3.6.1.2.1.2.2.1.10",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "unit": "octets",
                "poll_interval": 60,
                "threshold": {},
                "severity_default": "info",
                "description": "端口入方向字节数（Counter32，需差分计算速率）",
            },
            {
                "device_type": "network",
                "metric_key": "if_out_octets",
                "category": "if_out_octets",
                "display_name": "出流量",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifOutOctets",
                "oid": "1.3.6.1.2.1.2.2.1.16",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "unit": "octets",
                "poll_interval": 60,
                "threshold": {},
                "severity_default": "info",
                "description": "端口出方向字节数（Counter32，需差分计算速率）",
            },
            {
                "device_type": "network",
                "metric_key": "if_in_errors",
                "category": "if_in_errors",
                "display_name": "入错包",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifInErrors",
                "oid": "1.3.6.1.2.1.2.2.1.14",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "端口入方向错包数（超阈值触发告警）",
            },
            {
                "device_type": "network",
                "metric_key": "if_out_errors",
                "category": "if_out_errors",
                "display_name": "出错包",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifOutErrors",
                "oid": "1.3.6.1.2.1.2.2.1.20",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "端口出方向错包数（超阈值触发告警）",
            },
            {
                "device_type": "network",
                "metric_key": "if_in_discards",
                "category": "if_in_discards",
                "display_name": "入丢包",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifInDiscards",
                "oid": "1.3.6.1.2.1.2.2.1.13",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "端口入方向丢包数（IF-MIB ifInDiscards，超阈值触发告警）",
            },
            {
                "device_type": "network",
                "metric_key": "if_out_discards",
                "category": "if_out_discards",
                "display_name": "出丢包",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifOutDiscards",
                "oid": "1.3.6.1.2.1.2.2.1.19",
                "index_kind": "ifIndex",
                "metric_type": "counter",
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "端口出方向丢包数（IF-MIB ifOutDiscards，超阈值触发告警）",
            },
            {
                "device_type": "network",
                "metric_key": "if_utilization",
                "category": "if_utilization",
                "display_name": "端口利用率",
                "source": "snmp",
                "mib": "IF-MIB",
                "oid_symbol": "ifHCInOctets/ifHCOutOctets",
                "oid": "1.3.6.1.2.1.31.1.1.1.6",
                "index_kind": "ifIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "端口带宽利用率（基于 ifHCInOctets/ifHCOutOctets 64位计数器差分）",
            },
            {
                "device_type": "network",
                "metric_key": "sys_uptime",
                "category": "system_uptime",
                "display_name": "系统运行时间",
                "source": "snmp",
                "mib": "SNMPv2-MIB",
                "oid_symbol": "sysUpTime",
                "oid": "1.3.6.1.2.1.1.3.0",
                "index_kind": None,
                "metric_type": "gauge",
                "unit": "timeticks",
                "threshold": {},
                "severity_default": "info",
                "description": "设备启动后的运行时间（重启检测：当前值 < 上次值）",
            },
            {
                "device_type": "network",
                "metric_key": "cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率",
                "source": "snmp",
                "mib": "HOST-RESOURCES-MIB",
                "oid_symbol": "hrProcessorLoad",
                "oid": "1.3.6.1.2.1.25.3.3.1.2",
                "index_kind": "hrDeviceIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "CPU 利用率（HOST-RESOURCES-MIB 通用，华为/H3C/思科均支持）",
            },
            {
                "device_type": "network",
                "metric_key": "memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率",
                "source": "snmp",
                "mib": "HOST-RESOURCES-MIB",
                "oid_symbol": "hrStorageUsed/hrStorageSize",
                "oid": "1.3.6.1.2.1.25.2.3.1.6",
                "index_kind": "hrStorageIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 85, "crit": 95},
                "severity_default": "warn",
                "description": "内存利用率（HOST-RESOURCES-MIB::hrStorageTable）",
            },
            {
                "device_type": "network",
                "metric_key": "cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率(华为)",
                "source": "snmp",
                "vendor": "2011",
                "mib": "HUAWEI-MIB",
                "oid_symbol": "hwCpuDevUsage",
                "oid": "1.3.6.1.4.1.2011.6.3.11.1.3.0",
                "index_kind": None,
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "华为设备 CPU 利用率（HUAWEI-MIB::hwCpuDevUsage）",
            },
            {
                "device_type": "network",
                "metric_key": "memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率(华为)",
                "source": "snmp",
                "vendor": "2011",
                "mib": "HUAWEI-MIB",
                "oid_symbol": "hwMemUsage",
                "oid": "1.3.6.1.4.1.2011.6.1.2.1.1.8.0",
                "index_kind": None,
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 85, "crit": 95},
                "severity_default": "warn",
                "description": "华为设备内存利用率（HUAWEI-MIB::hwMemUsage）",
            },
            {
                "device_type": "network",
                "metric_key": "temperature",
                "category": "temperature",
                "display_name": "温度(华为)",
                "source": "snmp",
                "vendor": "2011",
                "mib": "HUAWEI-MIB",
                "oid_symbol": "hwEntityTemperature",
                "oid": "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11",
                "index_kind": "hwEntityIndex",
                "metric_type": "gauge",
                "unit": "Celsius",
                "threshold": {"warn": 60, "crit": 75},
                "severity_default": "warn",
                "description": "华为设备温度（HUAWEI-MIB::hwEntityTemperature）",
            },
            {
                "device_type": "network",
                "metric_key": "cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率(H3C)",
                "source": "snmp",
                "vendor": "25506",
                "mib": "HH3C-OAM-MIB",
                "oid_symbol": "hh3cDevMgrCPUUtil",
                "oid": "1.3.6.1.4.1.25506.2.6.1.1.1.1.6",
                "index_kind": "hh3cDevMgrIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "H3C 设备 CPU 利用率（HH3C-OAM-MIB::hh3cDevMgrCPUUtil）",
            },
            {
                "device_type": "network",
                "metric_key": "memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率(H3C)",
                "source": "snmp",
                "vendor": "25506",
                "mib": "HH3C-OAM-MIB",
                "oid_symbol": "hh3cDevMgrMemoryUtil",
                "oid": "1.3.6.1.4.1.25506.2.6.1.1.1.1.8",
                "index_kind": "hh3cDevMgrIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 85, "crit": 95},
                "severity_default": "warn",
                "description": "H3C 设备内存利用率（HH3C-OAM-MIB::hh3cDevMgrMemoryUtil）",
            },
            {
                "device_type": "network",
                "metric_key": "cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率(思科)",
                "source": "snmp",
                "vendor": "9",
                "mib": "CISCO-PROCESS-MIB",
                "oid_symbol": "cpmCPUTotal5secRev",
                "oid": "1.3.6.1.4.1.9.9.109.1.1.1.1.6",
                "index_kind": "cpmCPUTotalIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "思科设备 CPU 利用率（CISCO-PROCESS-MIB::cpmCPUTotal5secRev）",
            },
            {
                "device_type": "network",
                "metric_key": "memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率(思科)",
                "source": "snmp",
                "vendor": "9",
                "mib": "CISCO-MEMORY-POOL-MIB",
                "oid_symbol": "ciscoMemoryPoolUsed/ciscoMemoryPoolFree",
                "oid": "1.3.6.1.4.1.9.9.48.1.1.1.5",
                "index_kind": "ciscoMemoryPoolIndex",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 85, "crit": 95},
                "severity_default": "warn",
                "description": "思科设备内存利用率（CISCO-MEMORY-POOL-MIB）",
            },
            {
                "device_type": "network",
                "metric_key": "temperature",
                "category": "temperature",
                "display_name": "温度(思科)",
                "source": "snmp",
                "vendor": "9",
                "mib": "CISCO-ENVMON-MIB",
                "oid_symbol": "ciscoEnvMonTemperatureValue",
                "oid": "1.3.6.1.4.1.9.9.13.1.3.1.3",
                "index_kind": "ciscoEnvMonTemperatureIndex",
                "metric_type": "gauge",
                "unit": "Celsius",
                "threshold": {"warn": 60, "crit": 75},
                "severity_default": "warn",
                "description": "思科设备温度（CISCO-ENVMON-MIB::ciscoEnvMonTemperatureValue）",
            },
            {
                "device_type": "server",
                "metric_key": "temperature",
                "category": "temperature",
                "display_name": "温度",
                "source": "snmp",
                "mib": "ENTITY-SENSOR-MIB",
                "oid_symbol": "entPhySensorValue",
                "oid": "1.3.6.1.2.1.99.1.1.1.5",
                "metric_type": "gauge",
                "unit": "Celsius",
                "threshold": {"warn": 60, "crit": 70},
                "severity_default": "warn",
                "description": "温度传感器告警（超阈值触发）",
            },
            {
                "device_type": "server",
                "metric_key": "raid_failure",
                "category": "raid_failure",
                "display_name": "RAID 故障",
                "source": "ipmi",
                "mib": None,
                "oid_symbol": "SEL",
                "metric_type": "event",
                "threshold": {},
                "severity_default": "crit",
                "description": "IPMI SEL 磁盘/存储故障事件告警",
            },
            {
                "device_type": "server",
                "metric_key": "disk_failure",
                "category": "disk_failure",
                "display_name": "硬盘故障",
                "source": "ipmi",
                "mib": None,
                "oid_symbol": "SEL",
                "metric_type": "event",
                "threshold": {},
                "severity_default": "crit",
                "description": "硬盘故障事件告警",
            },
            {
                "device_type": "server",
                "metric_key": "cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率",
                "source": "zabbix",
                "zabbix_item_key": "system.cpu.util",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "Zabbix 采集 CPU 利用率（system.cpu.util，多核返回多实例）",
            },
            {
                "device_type": "server",
                "metric_key": "memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率",
                "source": "zabbix",
                "zabbix_item_key": "vm.memory.size[pavailable]",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 15, "crit": 5},
                "severity_default": "warn",
                "description": "Zabbix 采集内存可用率（vm.memory.size[pavailable]，低于阈值告警）",
            },
            {
                "device_type": "server",
                "metric_key": "zabbix_temperature",
                "category": "temperature",
                "display_name": "温度(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "sensor.temp.value",
                "metric_type": "gauge",
                "unit": "Celsius",
                "poll_interval": 60,
                "threshold": {"warn": 60, "crit": 75},
                "severity_default": "warn",
                "description": "Zabbix 采集温度传感器（sensor.temp.value，多传感器返回多实例）",
            },
            {
                "device_type": "server",
                "metric_key": "fan_speed",
                "category": "fan_speed",
                "display_name": "风扇转速",
                "source": "zabbix",
                "zabbix_item_key": "fan.speed",
                "metric_type": "gauge",
                "unit": "RPM",
                "poll_interval": 60,
                "threshold": {"warn": 1000},
                "severity_default": "warn",
                "description": "Zabbix 采集风扇转速（fan.speed，低于阈值告警）",
            },
            {
                "device_type": "server",
                "metric_key": "sys_uptime",
                "category": "system_uptime",
                "display_name": "系统运行时间",
                "source": "zabbix",
                "zabbix_item_key": "system.uptime",
                "metric_type": "gauge",
                "unit": "s",
                "poll_interval": 60,
                "threshold": {},
                "severity_default": "info",
                "description": "Zabbix 采集系统运行时间（system.uptime，重启检测：当前值 < 上次值）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_cpu_usage",
                "category": "cpu_usage",
                "display_name": "CPU 利用率(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "system.cpu.util",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 80, "crit": 95},
                "severity_default": "warn",
                "description": "Zabbix 采集网络设备 CPU 利用率（system.cpu.util）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_memory_usage",
                "category": "memory_usage",
                "display_name": "内存利用率(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "vm.memory.utilization",
                "metric_type": "gauge",
                "unit": "%",
                "poll_interval": 60,
                "threshold": {"warn": 85, "crit": 95},
                "severity_default": "warn",
                "description": "Zabbix 采集网络设备内存利用率（vm.memory.utilization）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_temperature",
                "category": "temperature",
                "display_name": "温度(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "sensor.temp.value",
                "metric_type": "gauge",
                "unit": "Celsius",
                "poll_interval": 60,
                "threshold": {"warn": 60, "crit": 75},
                "severity_default": "warn",
                "description": "Zabbix 采集网络设备温度（sensor.temp.value）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_sys_uptime",
                "category": "system_uptime",
                "display_name": "系统运行时间(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "system.uptime",
                "metric_type": "gauge",
                "unit": "s",
                "poll_interval": 60,
                "threshold": {},
                "severity_default": "info",
                "description": "Zabbix 采集网络设备系统运行时间（system.uptime）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_if_in_errors",
                "category": "if_in_errors",
                "display_name": "入错包(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "net.if.in.errors",
                "metric_type": "counter",
                "poll_interval": 60,
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "Zabbix 采集网络端口入方向错包数（net.if.in.errors[<if>]，多端口返回多实例）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_if_out_errors",
                "category": "if_out_errors",
                "display_name": "出错包(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "net.if.out.errors",
                "metric_type": "counter",
                "poll_interval": 60,
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "Zabbix 采集网络端口出方向错包数（net.if.out.errors[<if>]，多端口返回多实例）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_if_in_discards",
                "category": "if_in_discards",
                "display_name": "入丢包(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "net.if.in.discards",
                "metric_type": "counter",
                "poll_interval": 60,
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "Zabbix 采集网络端口入方向丢包数（net.if.in.discards[<if>]，多端口返回多实例）",
            },
            {
                "device_type": "network",
                "metric_key": "zabbix_if_out_discards",
                "category": "if_out_discards",
                "display_name": "出丢包(Zabbix)",
                "source": "zabbix",
                "zabbix_item_key": "net.if.out.discards",
                "metric_type": "counter",
                "poll_interval": 60,
                "threshold": {"warn": 100},
                "severity_default": "warn",
                "description": "Zabbix 采集网络端口出方向丢包数（net.if.out.discards[<if>]，多端口返回多实例）",
            },
        ]

    def seed_defaults(self) -> int:
        created = 0
        for spec in self.default_seed_specs():
            exists = (
                self.session.query(MonitorMetricTemplate)
                .filter(
                    MonitorMetricTemplate.device_type == spec["device_type"],
                    MonitorMetricTemplate.metric_key == spec["metric_key"],
                    MonitorMetricTemplate.vendor == spec.get("vendor"),
                )
                .first()
            )
            if exists is not None:
                continue
            self.upsert(**spec)
            created += 1
        self.session.flush()
        return created
