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
    PORT_CREATE      = "port_create"
    PORT_UPDATE      = "port_update"
    PORT_DELETE      = "port_delete"
    PORT_ENABLE      = "port_enable"
    PORT_DISABLE     = "port_disable"
    PORT_SYNC        = "port_sync"

    VLAN_CREATE      = "vlan_create"
    VLAN_UPDATE      = "vlan_update"
    VLAN_DELETE      = "vlan_delete"
    VLAN_MEMBER_SET  = "vlan_member_set"

    LAG_CREATE       = "lag_create"
    LAG_UPDATE       = "lag_update"
    LAG_DELETE       = "lag_delete"
    LAG_MEMBER_SET   = "lag_member_set"

    CONNECTION_CREATE = "connection_create"
    CONNECTION_UPDATE = "connection_update"
    CONNECTION_DELETE = "connection_delete"

    PORT_VLAN_CONFIG  = "port_vlan_config"
    PORT_IP_SET       = "port_ip_set"
    PORT_SPEED_LIMIT  = "port_speed_limit"
    PORT_CLEAR_CONFIG = "port_clear_config"

    PORT_ACTION_RESULT = "port_action_result"
