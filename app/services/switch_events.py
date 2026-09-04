from __future__ import annotations
# -*- coding: utf-8 -*-
"""
端口变更事件发布模块（Flask 侧，仅发布，不再服务 SSE）

架构变更说明（见重构评审报告）：
    原来本模块同时承担"发布"和"SSE 服务"两个职责，SSE 生成器
    （event_stream/global_event_stream）在同步 Flask worker 里长时间占用线程，
    且序列号(_next_seq)/环形缓冲区(_device_rings)是进程内内存态——gunicorn -w N
    多进程部署下，不同 worker 各自维护一份，同一 device 的 seq 会跨进程重复，
    断线重连大概率被路由到另一个 worker，历史事件对不上，"断线重放"名不副实。

    现在 SSE 服务完全移交给独立的 ASGI 推送网关（见 realtime_gateway/），
    该网关是 Redis Pub/Sub 的订阅者之一（可多副本）。seq 分配和环形缓冲区
    由本模块（发布侧）负责：seq 用 Redis INCR 原子分配（多 worker/多副本安全），
    ring 用 Redis List + Lua 原子写入（LPUSH+LTRIM+EXPIRE 滑动 TTL），
    多副本网关共享同一份 ring，断线重连路由到任一副本都能重放。本模块只保留
    "发布"职责：组装事件 payload，不再自己维护 Queue/线程/进程内环形缓冲区。

    Redis 从"可选优化"变成硬依赖：本模块不再有进程内内存 Queue 兜底模式，
    因为发布方（Flask）和消费方（ASGI 网关）现在总是不同进程。
    本地开发环境需要跑一个 Redis（docker-compose 加一个 redis 服务即可），
    REDIS_URL 未配置时会记录一条 ERROR 并静默丢弃事件（不影响主业务流程，
    但实时推送会完全不可用，见 _get_redis 的注释）。

架构约定：本模块统一使用 device_id（devices.id）作为交换机标识，
与 network_ports / switch_port_status / switch_port_ips 等表保持一致。

注意：事件携带发布侧分配的 seq（Redis INCR，网关透传不重新分配），
同时携带 event_id（uuid，供前端去重）。
"""
import json
import os
from app.utils.logging import get_logger
import time
import uuid as _uuid_mod

logger = get_logger(__name__)

_GLOBAL_REDIS_CHANNEL = "events:global"

RING_BUFFER_SIZE = int(os.environ.get("SSE_RING_BUFFER_SIZE", "200"))
RING_TTL_SECONDS = int(os.environ.get("SSE_RING_TTL_SECONDS", "3600"))

_RING_LUA = """
redis.call('LPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], 0, ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
"""

_ring_script = None

_PUBLISH_ATTEMPTS = 3
_PUBLISH_RETRY_DELAY = 0.05  # 秒

_publish_drop_stats: dict[str, int] = {
    "device_publish": 0,   # 设备事件最终投递失败（含有界重试耗尽）
    "global_publish": 0,   # 全局事件投递失败
    "redis_unavailable": 0,  # Redis 不可用导致的事件丢弃
}
_last_unavailable_log = 0.0  # 节流：不可用告警 60s 一次，防故障期刷屏


def get_publish_drop_stats() -> dict[str, int]:
    """返回各类事件投递失败累计计数（供运维端点 / 排障读取）。"""
    return dict(_publish_drop_stats)


def _warn_redis_unavailable() -> None:
    """Redis 不可用的节流告警（首次及每 60s 提醒一次）。"""
    global _last_unavailable_log
    now = time.monotonic()
    if now - _last_unavailable_log < 60:
        return
    _last_unavailable_log = now
    logger.error(
        "Redis 不可用，事件发布被丢弃（累计 %d 条；本条每 60s 提醒一次）",
        _publish_drop_stats["redis_unavailable"],
    )



def _get_redis():
    """获取 Redis 客户端（委托全局单例入口）。

    与旧版不同：这里不再是"可选优化，连不上就退回内存模式"——
    退无可退，因为本进程（Flask）不再自己服务 SSE，事件必须经 Redis
    才能到达 ASGI 网关。REDIS_URL 未配置或连接失败时，事件会被静默丢弃
    （只记日志），但不会抛异常影响调用方的主业务事务。
    """
    from app.utils.redis_client import get_redis_client
    return get_redis_client()


def _get_ring_script(r):
    """懒注册 ring Lua 脚本（与 Redis 客户端单例绑定）。"""
    global _ring_script
    if _ring_script is None:
        _ring_script = r.register_script(_RING_LUA)
    return _ring_script


def _publish_device_event(device_id: int, event_dict: dict) -> None:
    """设备事件发布：INCR 分配 seq → Lua 原子落 ring → PUBLISH。

    seq 由发布侧分配（Redis INCR 原子，多 gunicorn worker 安全），
    网关副本只消费不分配——这是网关多副本部署的硬性前提。

    ⚠️ 顺序硬约束：必须先落 ring 再 PUBLISH。若先 publish，客户端可能在
    publish 之后、ring 写入完成之前断线重连，该事件既不在 ring
    （LRANGE 读不到）、也未建立实时订阅，导致永久丢失。

    Args:
        device_id:  交换机 devices.id
        event_dict: 事件 dict（不含 seq，本函数负责分配并注入）
    """
    r = _get_redis()
    if not r:
        _publish_drop_stats["redis_unavailable"] += 1
        _warn_redis_unavailable()
        return
    try:
        seq_key = f"seq:{device_id}"
        r.set(seq_key, int(time.time()), nx=True)
        event_dict["seq"] = r.incr(seq_key)
        payload = json.dumps(event_dict, ensure_ascii=False)

        _get_ring_script(r)(
            keys=[f"ring:{device_id}"],
            args=[payload, RING_BUFFER_SIZE - 1, RING_TTL_SECONDS],
        )

        for attempt in range(1, _PUBLISH_ATTEMPTS + 1):
            try:
                r.publish(f"sw:{device_id}", payload)
                break
            except Exception as exc:
                if attempt == _PUBLISH_ATTEMPTS:
                    _publish_drop_stats["device_publish"] += 1
                    logger.error(
                        "Redis 设备事件 publish 失败（已重试 %d 次，放弃；累计丢弃 %d 条；"
                        "事件已在 ring，重连客户端可重放补收）device=%s seq=%s: %s",
                        _PUBLISH_ATTEMPTS, _publish_drop_stats["device_publish"],
                        device_id, event_dict.get("seq"), exc,
                    )
                else:
                    time.sleep(_PUBLISH_RETRY_DELAY)
    except Exception as exc:
        _publish_drop_stats["device_publish"] += 1
        logger.error("Redis 设备事件发布失败（累计丢弃 %d 条）: %s",
                     _publish_drop_stats["device_publish"], exc)


def _redis_publish_global(payload: str) -> None:
    """通过 Redis Pub/Sub 广播全局事件。"""
    r = _get_redis()
    if not r:
        _publish_drop_stats["redis_unavailable"] += 1
        _warn_redis_unavailable()
        return
    try:
        r.publish(_GLOBAL_REDIS_CHANNEL, payload)
    except Exception as exc:
        _publish_drop_stats["global_publish"] += 1
        logger.error("Redis global publish 失败（累计丢弃 %d 条）: %s",
                     _publish_drop_stats["global_publish"], exc)



def emit_resource_change(
    device_id:            int,
    op_type:              str,
    *,
    affected_ports:       list[str] = None,
    affected_vlans:       list[int] = None,
    affected_lags:        list[int] = None,
    affected_connections: list[int] = None,
    extra:                dict      = None,
) -> None:
    """发布结构化资源变更事件（替代 emit_port_change）

    必须在 db.session.commit() 成功之后调用。

    Args:
        device_id:            交换机 devices.id
        op_type:              操作类型（见 OpType 常量）
        affected_ports:       变更的端口名列表
        affected_vlans:       变更的 VLAN 数据库 ID 列表（vlans.id，非 vlan_id 号码）
        affected_lags:        变更的 LAG 数据库 ID 列表
        affected_connections: 变更的连接 ID 列表
        extra:                额外上下文（task_id、success、error 等）
    """
    event_dict = {
        "event_id":            str(_uuid_mod.uuid4()),
        "device_id":           device_id,
        "op_type":             op_type,
        "ts":                  int(time.time() * 1000),
        "affected_ports":      affected_ports       or [],
        "affected_vlans":      affected_vlans       or [],
        "affected_lags":       affected_lags        or [],
        "affected_connections": affected_connections or [],
        **(extra or {}),
    }
    _publish_device_event(device_id, event_dict)


def emit_port_action_result(
    device_id: int, port: str, task_id: str, action: str,
    success: bool, message: str = "", error: str = "",
    detail_op_type: str = "",
) -> None:
    """发布端口操作结果事件（供异步端口操作使用）。

    与 emit_resource_change 对齐结构化事件格式（seq 由 _publish_device_event
    发布侧分配），确保前端 DeviceEventBus 能正确分发到 'ports' 监听器。

    Args:
        device_id:      交换机 device_id（devices.id）
        port:           端口名称
        task_id:        异步任务 ID
        action:         操作类型（如 enable_port / set_port_vlan）
        success:        操作是否成功
        message:        成功消息
        error:          失败错误信息
        detail_op_type: 原始操作类型（如 enable / vlan_set），供前端精确缓存失效
    """
    event_dict = {
        "event_id":            str(_uuid_mod.uuid4()),
        "device_id":           device_id,
        "op_type":             "port_action_result",
        "ts":                  int(time.time() * 1000),
        "affected_ports":      [port] if port else [],
        "affected_vlans":      [],
        "affected_lags":       [],
        "affected_connections": [],
        "port":                port,
        "task_id":             task_id,
        "action":              action,
        "success":             success,
        "message":             message,
        "error":               error,
        "detail_op_type":      detail_op_type,
    }
    _publish_device_event(device_id, event_dict)



def emit_resource_change_global(
    resource: str,
    op: str,
    *,
    ids: list[int] | None = None,
    extra: dict | None = None,
) -> None:
    """发布全局资源变更事件（不绑定特定交换机）。

    用于设备、机柜、机房、客户等非交换机实体的 CRUD 变更通知，
    通过 events:global channel 推送，前端 useGlobalEvents 消费后
    自动失效对应 TanStack Query 缓存。

    批量操作只发一条汇总事件（op 带 batch_ 前缀，ids 包含所有受影响 ID）。

    必须在 db.session.commit() 成功之后调用。

    Args:
        resource: 资源类型（device / cabinet / room / customer / user / network / ip / virtual_room）
        op:       操作类型（create / update / delete / batch_create / batch_update / batch_delete / status_change / location_change）
        ids:      受影响的资源 ID 列表
        extra:    额外上下文
    """
    data = json.dumps({
        "event_type": "resource_change",
        "payload": {
            "resource": resource,
            "op": op,
            "ids": ids or [],
            "extra": extra or {},
        },
        "ts": int(time.time() * 1000),
    }, ensure_ascii=False)
    _redis_publish_global(data)



def emit_global_event(event_type: str, payload: dict | None = None) -> None:
    """广播全局事件（不绑定特定交换机）。

    用于机房扫描完成、批量配置变更等影响多页面的场景。

    Args:
        event_type: 事件类型（如 room_scan_complete / bulk_config_change）
        payload:    附加数据
    """
    data = json.dumps({
        "event_type": event_type,
        "payload": payload or {},
        "ts": int(time.time() * 1000),
    }, ensure_ascii=False)
    _redis_publish_global(data)


def emit_global_event_with_targets(
    event_type: str,
    payload: dict | None = None,
    target_user_ids: list[int] | None = None,
) -> None:
    """广播带目标过滤的全局事件。

    与 emit_global_event 类似，但携带 target_user_ids 字段：
    网关侧 _handle_global_event 会按订阅连接的 user_id 过滤 fan-out，
    target_user_ids 为 None（或不传）时仍全局广播，对既有事件零影响。

    Args:
        event_type:      事件类型
        payload:         附加数据
        target_user_ids: 目标用户 id 列表；None = 全局广播
    """
    data = json.dumps({
        "event_type": event_type,
        "payload": payload or {},
        "target_user_ids": target_user_ids,  # None = 全局广播
        "ts": int(time.time() * 1000),
    }, ensure_ascii=False)
    _redis_publish_global(data)
