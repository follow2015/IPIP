# -*- coding: utf-8 -*-
"""
交换机变更事件 Schema

所有 SSE 事件必须通过 emit_resource_change() 发布，
禁止直接调用旧的 emit_port_change（已删除）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class DeviceChangeEvent:
    """结构化设备变更事件

    Attributes:
        event_id:            UUID，用于前端去重
        device_id:           交换机 devices.id
        op_type:             操作类型（见 OpType 常量）
        seq:                 单设备递增序列号，用于断线重放
        ts:                  毫秒时间戳
        affected_ports:      变更的端口名列表（network_ports.port_name）
        affected_vlans:      变更的 VLAN 数据库 ID 列表（vlans.id）
        affected_lags:       变更的 LAG 数据库 ID 列表（link_aggregation_groups.id）
        affected_connections: 变更的连接 ID 列表（device_connections.id）
        extra:               额外上下文（如 task_id、success、error）
    """
    device_id:            int
    op_type:              str
    seq:                  int = 0
    ts:                   int = 0
    event_id:             str = field(default_factory=lambda: str(uuid.uuid4()))
    affected_ports:       list[str] = field(default_factory=list)
    affected_vlans:       list[int] = field(default_factory=list)
    affected_lags:        list[int] = field(default_factory=list)
    affected_connections: list[int] = field(default_factory=list)
    extra:                dict     = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为 dict，extra 字段展开到顶层"""
        return {
            "event_id":            self.event_id,
            "device_id":           self.device_id,
            "op_type":             self.op_type,
            "seq":                 self.seq,
            "ts":                  self.ts,
            "affected_ports":      self.affected_ports,
            "affected_vlans":      self.affected_vlans,
            "affected_lags":       self.affected_lags,
            "affected_connections": self.affected_connections,
            **self.extra,
        }


class OpType:
    """操作类型常量，供 emit_resource_change() 和前端使用"""
    PORT_CREATE      = "port_create"
    PORT_UPDATE      = "port_update"
    PORT_DELETE      = "port_delete"
    PORT_ENABLE      = "port_enable"
    PORT_DISABLE     = "port_disable"
    PORT_SYNC        = "port_sync"        # SSH 全量采集

    VLAN_CREATE      = "vlan_create"
    VLAN_UPDATE      = "vlan_update"
    VLAN_DELETE      = "vlan_delete"
    VLAN_MEMBER_SET  = "vlan_member_set"  # 成员端口变更

    LAG_CREATE       = "lag_create"
    LAG_UPDATE       = "lag_update"
    LAG_DELETE       = "lag_delete"
    LAG_MEMBER_SET   = "lag_member_set"   # 成员端口变更

    CONNECTION_CREATE = "connection_create"
    CONNECTION_UPDATE = "connection_update"
    CONNECTION_DELETE = "connection_delete"

    PORT_VLAN_CONFIG  = "port_vlan_config"
    PORT_IP_SET       = "port_ip_set"
    PORT_SPEED_LIMIT  = "port_speed_limit"
    PORT_CLEAR_CONFIG = "port_clear_config"  # 清除端口配置（恢复默认）

    PORT_ACTION_RESULT = "port_action_result"