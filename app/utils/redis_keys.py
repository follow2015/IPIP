# -*- coding: utf-8 -*-
"""Redis 键空间登记处（M8）

此前键名以字面量散落在十余个模块：`ring:{id}`、`seq:{id}`、`ratelimit:{key}`、
`monitor:lock:{loop}`、`voice:call:{id}`、`cooldown:{…}` …… 各有各的命名习惯，且
**绕过缓存的 `_make_key`，不受 `CACHE_KEY_PREFIX` 管辖**。后果很具体：运维想按前缀
清一批限流计数时，得先知道计数到底叫 `ratelimit:sw:` 还是 `sw:ratelimit:`；想评估
"清掉 monitor:* 会不会打掉正在用的锁"时，只能逐个文件 grep。

本模块把全部族集中登记，使键空间可以一眼看完。**本次只登记、不改键名** —— 统一
成 `${APP}:v1:{…}` 是破坏性变更（旧键全部失效：限流计数清零、ring 断流、锁消失），
必须配双写迁移与灰度，不在这次顺手做。登记是那次迁移的前置条件。

登记处必须**只增不改**：改一个键名等于让旧数据无声失效。要改就走迁移（双写 →
切读 → 清理旧键），并在 `tests/test_redis_key_inventory.py` 的 golden 里同步。

约定：
- 构造函数返回值即最终键名（不含任何环境前缀），与历史字面量**逐字一致**；
- 需要按前缀扫描清理的族，同时提供 `*_PREFIX` 常量（`scan_iter(match=…)` 用）；
- 新增族请写清 TTL 与"清掉会怎样"，否则下一个人还是不敢动。

**不在本模块的族**（别重复登记，也别误以为这里漏了）：
- ``token:revoked:{md5|token}`` —— 走 ``cache_manager``，受 ``CACHE_KEY_PREFIX``
  管辖，属"缓存族"而非本模块这批"绕过前缀"的键。它的跨包一致性
  （Flask 写入 / realtime_gateway 读取）由
  ``tests/test_p0_gateway_revocation_key_contract.py`` 专门钉住，此处不重复。
- 评审 M8 原文还点名了 ``sse_ticket:{jti}``：那是**JWT payload 的 type 字段**
  （``"type": "sse_ticket"``）与一次性消费键的 jti，不是独立键族，2026-10-02 核实。
"""
from __future__ import annotations


def seq_key(device_id: int) -> str:
    """设备事件流的 seq 计数器键（永久键，不设 TTL）。"""
    return f"seq:{device_id}"


def ring_key(device_id: int) -> str:
    """设备事件流的 ring 缓冲键（滑动 TTL）。"""
    return f"ring:{device_id}"


def device_channel(device_id: int) -> str:
    """设备事件的 Redis Pub/Sub 频道名（不是键，但同属命名空间）。"""
    return f"sw:{device_id}"


GLOBAL_SEQ_KEY = "seq:global"
GLOBAL_RING_KEY = "ring:global"
GLOBAL_CHANNEL = "events:global"


RATELIMIT_PREFIX = "ratelimit:"


def ratelimit_key(scope: str, key: str) -> str:
    """限流计数键。scope ∈ {sw, fw, tb}（滑动窗口 / 防火墙 / 令牌桶）。"""
    return f"ratelimit:{scope}:{key}"


def notify_cooldown_key(type_: str, source_module: str | None, channel_name: str) -> str:
    """通知渠道冷却键（防同一渠道被同一告警连击）。"""
    return f"cooldown:{type_}:{source_module or ''}:{channel_name}"


NOTIFY_RECOVER_LOCK_KEY = "notify:recover:lock"


def voice_call_key(call_id: str) -> str:
    return f"voice:call:{call_id}"


def voice_budget_key(provider: str, span: str, phone: str, bucket: int) -> str:
    return f"voice:budget:{provider}:{span}:{phone}:{bucket}"


def voice_callback_key(call_id: str, event: str) -> str:
    """语音回调事件去重键（nx=True 占位）。"""
    return f"voice:cb:{call_id}:{event}"


VOICE_PENDING_PREFIX = "pending:"


def monitor_suppress_key(dedup_key: str) -> str:
    return f"monitor:suppress:{dedup_key}"


def monitor_maint_key(device_id: int) -> str:
    return f"monitor:maint:{device_id}"


def monitor_probe_cooldown_key(device_id: int) -> str:
    return f"monitor:probe:cooldown:{device_id}"


def monitor_lock_key(loop_name: str) -> str:
    """监控轮询循环互斥锁（TTL = 2 × interval，看门狗续期）。"""
    return f"monitor:lock:{loop_name}"


def monitor_rate_key(loop_name: str) -> str:
    """监控轮询最小间隔闸门（锁只保证互斥，不保证限速）。"""
    return f"monitor:rate:{loop_name}"


def monitor_threshold_override_key(device_id: int, metric_key: str) -> str:
    return f"monitor:threshold_override:{device_id}:{metric_key}"


def monitor_threshold_override_prefix(device_id: int) -> str:
    """按设备清理阈值覆盖时用（scan_iter match）。"""
    return f"monitor:threshold_override:{device_id}:"


MONITOR_DEP_RULES_ACTIVE_KEY = "monitor:dep_rules:active"
MONITOR_SILENCE_ACTIVE_KEY = "monitor:silence:active"
MONITOR_DYNAMIC_CONFIG_KEY = "monitor:dynamic_config"
MONITOR_OID_RULES_PREFIX = "monitor:oid-rules:"
MONITOR_RECOMMEND_CONFIG_PREFIX = "monitor:recommend-config:"
MONITOR_MIB_PROBE_PREFIX = "monitor:mib-probe:"
MONITOR_ROUNDS_NS = "monitor:rounds"


HEARTBEAT_NS_PREFIX = "ipip:heartbeat:"


def heartbeat_prefix(environment: str) -> str:
    """进程心跳键前缀（后缀是 service 名）。清掉会怎样：失联告警误报。"""
    return f"{HEARTBEAT_NS_PREFIX}{environment}:"


AI_TASK_KEY_PREFIX = "ai:task:"


def ai_task_key(task_id: str) -> str:
    """AI 任务进度状态键（TTL 1h）。清掉 = 前端拿不到进度，任务照跑。"""
    return f"ai:task:{task_id}"


AI_IDEM_PREFIX = "ai:idem:"


def ai_idem_key(user_id: int, key: str) -> str:
    return f"{AI_IDEM_PREFIX}{user_id}:{key}"


AI_CB_PREFIX = "ai:cb:"
AI_CB_INDEX_KEY = f"{AI_CB_PREFIX}_index"


def ai_cb_key(name: str) -> str:
    return f"{AI_CB_PREFIX}{name}"


def ai_cb_probe_key(name: str) -> str:
    return f"{AI_CB_PREFIX}{name}:probe"


def scan_mac_index_key(scope: str, mac: str) -> str:
    return f"mac_index:{scope}:{mac}"


def scan_port_mac_key(scope: str, sw_id: int, port: str) -> str:
    return f"port_mac:{scope}:{sw_id}:{port}"


def scan_port_ip_key(scope: str) -> str:
    return f"port_ip:{scope}"


def scan_no_auth_fallback_key(scope: str) -> str:
    return f"no_auth_fallback:{scope}"


def scan_lock_key(switch_id: int) -> str:
    return f"scan_lock:{switch_id}"


def scan_switch_lock_key(device_id: int) -> str:
    """整机扫描互斥锁（TTL 1800s）。清掉 = 同一交换机并发扫描。"""
    return f"ipm:lock:scan_switch:{device_id}"


def device_op_lock_key(device_id: int) -> str:
    """设备写操作租约锁。清掉 = 两台操作可以并发下发（配置打架）。"""
    return f"device_op_lock:{device_id}"


def device_op_lock_ro_key(device_id: int) -> str:
    """设备只读诊断锁（与写锁分开：诊断不应阻塞配置下发，反之亦然）。"""
    return f"device_op_lock:ro:{device_id}"


def ipm_lock_key(prefix: str, lock_key_value: str) -> str:
    """通用幂等/操作锁族 `ipm:lock:{prefix}:{value}`，prefix 如 sync_ports。

    清掉会怎样：正在跑的同步/扫描失去互斥保护，可能并发重入。
    """
    return f"ipm:lock:{prefix}:{lock_key_value}"


def qr_session_key(scene_id: str) -> str:
    return f"qr_session:{scene_id}"


def error_stats_key(error_type: str) -> str:
    return f"error_stats:{error_type}"



def snmp_snapshot_key(device_id: int) -> str:
    """单台设备的 SNMP 全表快照（JSON 序列化）。"""
    return f"snmp:snap:{device_id}"
