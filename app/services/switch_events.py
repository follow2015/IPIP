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
    该网关是 Redis Pub/Sub 的唯一订阅者，seq 分配和环形缓冲区在网关侧
    单进程持有，天然全局唯一、天然支持重放。本模块只保留"发布"职责：
    组装事件 payload，通过 Redis Pub/Sub 广播出去，不再关心谁在订阅、
    不再自己维护 Queue/线程/环形缓冲区。

    Redis 从"可选优化"变成硬依赖：本模块不再有进程内内存 Queue 兜底模式，
    因为发布方（Flask）和消费方（ASGI 网关）现在总是不同进程。
    本地开发环境需要跑一个 Redis（docker-compose 加一个 redis 服务即可），
    REDIS_URL 未配置时会记录一条 ERROR 并静默丢弃事件（不影响主业务流程，
    但实时推送会完全不可用，见 _get_redis 的注释）。

架构约定：本模块统一使用 device_id（devices.id）作为交换机标识，
与 network_ports / switch_port_status / switch_port_ips 等表保持一致。

注意：事件里不再携带 seq（由网关分配），只携带 event_id（uuid，供网关/前端去重）。
"""
import json
from app.utils.logging import get_logger
import threading
import time
import uuid as _uuid_mod

logger = get_logger(__name__)

_GLOBAL_REDIS_CHANNEL = "events:global"

_redis_client = None
_redis_init_lock = threading.Lock()  # 防止多线程并发初始化（double-checked locking）
_redis_unavailable_logged = False  # 防止 REDIS_URL 未配置时日志刷屏（仅首次 ERROR，后续 DEBUG）


def _get_redis():
    """懒加载 Redis 客户端。

    与旧版不同：这里不再是"可选优化，连不上就退回内存模式"——
    退无可退，因为本进程（Flask）不再自己服务 SSE，事件必须经 Redis
    才能到达 ASGI 网关。REDIS_URL 未配置或连接失败时，事件会被静默丢弃
    （只记日志），但不会抛异常影响调用方的主业务事务。
    """
    global _redis_client, _redis_unavailable_logged
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            from config import get_config
            _config = get_config()
            config_instance = _config() if isinstance(_config, type) else _config
            redis_url = config_instance.REDIS_URL
        except Exception:
            redis_url = None
        if not redis_url:
            if not _redis_unavailable_logged:
                logger.error("REDIS_URL 未配置，实时事件推送不可用（事件将被静默丢弃）")
                _redis_unavailable_logged = True
            else:
                logger.debug("REDIS_URL 未配置，实时事件推送不可用")
            return None
        try:
            import redis as _redis_lib
            _redis_client = _redis_lib.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                socket_keepalive=True,
            )
            _redis_client.ping()
            logger.info("SSE Redis Pub/Sub 已启用: %s", redis_url)
            return _redis_client
        except Exception as exc:
            logger.warning("REDIS_URL 已配置但连接失败，事件将被静默丢弃: %s", exc)
            return None


def _redis_publish(device_id: int, payload: str) -> None:
    """通过 Redis Pub/Sub 广播事件。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.publish(f"sw:{device_id}", payload)
    except Exception as exc:
        logger.warning("Redis publish 失败: %s", exc)


def _redis_publish_global(payload: str) -> None:
    """通过 Redis Pub/Sub 广播全局事件。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.publish(_GLOBAL_REDIS_CHANNEL, payload)
    except Exception as exc:
        logger.warning("Redis global publish 失败: %s", exc)



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
    payload = json.dumps(event_dict, ensure_ascii=False)
    _redis_publish(device_id, payload)


def emit_port_action_result(
    device_id: int, port: str, task_id: str, action: str,
    success: bool, message: str = "", error: str = "",
    detail_op_type: str = "",
) -> None:
    """发布端口操作结果事件（供异步端口操作使用）。

    与 emit_resource_change 对齐结构化事件格式（不含 seq，由网关分配），
    确保前端 DeviceEventBus 能正确分发到 'ports' 监听器。

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
    payload = json.dumps(event_dict, ensure_ascii=False)
    _redis_publish(device_id, payload)



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
