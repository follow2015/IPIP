# -*- coding: utf-8 -*-
"""动态配置服务：Redis Hash + DB 双写，支持 Worker 热重载读取。

读取路径: MonitorDynamicConfig.get(key)
    -> Redis HGET monitor:dynamic_config <key>
    -> miss 则 DB fallback -> 回填 Redis（HSETNX 并发保护）
    -> 再 miss 返回 None（调用方 _cfg 回退 current_app.config）

写入路径: set(key, value, updated_by)
    -> Redis HSET（即时生效，进程间共享）
    -> DB upsert（持久化，防 Redis 重启丢失）

启动路径: load_all_from_db()
    -> DB 全量 -> 批量 HSET 回填 Redis

命名约束（重要）：
- 内部全部使用大写 MONITOR_* config_key，与现有 MonitorService._cfg() 调用点零映射；
- API 边界的驼峰字段名由 monitor_routes 负责转换（见 CAMEL_TO_KEY / KEY_TO_CAMEL），
  本模块不知道驼峰，避免双层映射导致「线上改了但读取端 key 对不上、不生效」。
"""
import json
import threading
import weakref
from typing import Any, Dict, Optional

from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.persistence.monitor_dynamic_config_repository import (
    MonitorDynamicConfigRepository,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_redis_cache_lock = threading.Lock()
_redis_clients: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def reset_dynamic_config_redis_cache() -> None:
    """测试/重载专用：清空 Redis 客户端缓存。"""
    with _redis_cache_lock:
        _redis_clients.clear()

REDIS_KEY = "monitor:dynamic_config"


class _Entry:
    """白名单条目。"""

    def __init__(
        self,
        key: str,
        type_: str,
        default: Any,
        description: str,
        editable: bool,
        min_: Optional[int] = None,
        max_: Optional[int] = None,
        camel: Optional[str] = None,
    ):
        self.key = key
        self.type = type_
        self.default = default
        self.description = description
        self.editable = editable
        self.min = min_
        self.max = max_
        self.camel = camel  # API 边界驼峰字段名


_WHITELIST: Dict[str, _Entry] = {
    "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD": _Entry(
        "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", "int", 2,
        "连续失败阈值（达到后判定不可达并告警）", True, 1, 100,
        "consecutive_failures_threshold",
    ),
    "MONITOR_REALERT_INTERVAL_MINUTES": _Entry(
        "MONITOR_REALERT_INTERVAL_MINUTES", "int", 360,
        "重告警间隔（分钟）", True, 10, 1440, "realert_interval_minutes",
    ),
    "MONITOR_FALLBACK_ROLE": _Entry(
        "MONITOR_FALLBACK_ROLE", "string", "admin",
        "兜底角色（责任人缺失时兜底接收告警）", True, camel="fallback_role",
    ),
    "MONITOR_BLINDSPOT_ROLE": _Entry(
        "MONITOR_BLINDSPOT_ROLE", "string", "admin",
        "盲区应急组（兜底角色无活跃用户时二次兜底）", True, camel="blindspot_role",
    ),
    "MONITOR_THREAD_POOL_SIZE": _Entry(
        "MONITOR_THREAD_POOL_SIZE", "int", 20,
        "探测线程池大小", True, 1, 100, "thread_pool_size",
    ),
    "MONITOR_TIMEOUT_SECONDS": _Entry(
        "MONITOR_TIMEOUT_SECONDS", "int", 5,
        "探测超时（秒）", True, 1, 60, "timeout_seconds",
    ),
    "MONITOR_INTERVAL_SNMP": _Entry(
        "MONITOR_INTERVAL_SNMP", "int", 60,
        "SNMP 轮询间隔（秒）", True, 10, 3600, "interval_snmp",
    ),
    "MONITOR_INTERVAL_BMC": _Entry(
        "MONITOR_INTERVAL_BMC", "int", 60,
        "BMC 轮询间隔（秒）", True, 10, 3600, "interval_bmc",
    ),
    "MONITOR_INTERVAL_ZABBIX": _Entry(
        "MONITOR_INTERVAL_ZABBIX", "int", 60,
        "Zabbix 轮询间隔（秒）", True, 10, 3600, "interval_zabbix",
    ),
    "MONITOR_OUTBOX_INTERVAL": _Entry(
        "MONITOR_OUTBOX_INTERVAL", "int", 5,
        "告警发件箱轮询间隔（秒）", True, 1, 3600, "outbox_interval",
    ),
    "MONITOR_NON_MANAGED_PORT_SYNC": _Entry(
        "MONITOR_NON_MANAGED_PORT_SYNC", "bool", False,
        "非网管网络设备端口自动同步（默认关闭，开启后按 IF-MIB/Zabbix 全量替换端口表）",
        True, camel="non_managed_port_sync",
    ),
    "SCAN_AUTO_ENABLED": _Entry(
        "SCAN_AUTO_ENABLED", "bool", False,
        "自动扫描总开关", True, camel="scan_auto_enabled",
    ),
    "SCAN_AUTO_INTERVAL": _Entry(
        "SCAN_AUTO_INTERVAL", "int", 21600,
        "扫描间隔（秒），默认 6 小时", True, 600, 86400, "scan_auto_interval",
    ),
    "SCAN_AUTO_ROOM_IDS": _Entry(
        "SCAN_AUTO_ROOM_IDS", "string", "",
        "启用自动扫描的物理机房ID列表（逗号分隔）", True, camel="scan_auto_room_ids",
    ),
    "SCAN_AUTO_VR_IDS": _Entry(
        "SCAN_AUTO_VR_IDS", "string", "",
        "启用自动扫描的虚拟机房ID列表（逗号分隔）", True, camel="scan_auto_vr_ids",
    ),
    "SCAN_AUTO_CLEANUP_INTERVAL": _Entry(
        "SCAN_AUTO_CLEANUP_INTERVAL", "int", 1800,
        "陈旧度清理间隔（秒），默认 30 分钟", True, 300, 7200, "scan_auto_cleanup_interval",
    ),
    "SCAN_AUTO_GRACE_PERIOD": _Entry(
        "SCAN_AUTO_GRACE_PERIOD", "int", 64800,
        "inactive降级宽限期（秒），默认 18 小时", True, 3600, 259200, "scan_auto_grace_period",
    ),
}

_NON_EDITABLE: Dict[str, _Entry] = {
    "MONITOR_WORKER_IN_PROCESS": _Entry(
        "MONITOR_WORKER_IN_PROCESS", "bool", True,
        "进程内 Worker（进程模型变更需重启）", False, camel="worker_in_process",
    ),
}


def whitelist_entries() -> Dict[str, _Entry]:
    """可编辑白名单（PUT 校验用）。"""
    return dict(_WHITELIST)


def all_entries() -> Dict[str, _Entry]:
    """全部条目（含不可编辑，GET 展示用）。"""
    return {**_WHITELIST, **_NON_EDITABLE}


CAMEL_TO_KEY: Dict[str, str] = {
    e.camel: k for k, e in all_entries().items() if e.camel
}
KEY_TO_CAMEL: Dict[str, str] = {
    k: e.camel for k, e in all_entries().items() if e.camel
}


def _coerce(raw: str, type_: str) -> Any:
    """按类型解析动态配置原始字符串。

    P2-5：包 try/except 回退 None——Redis/DB 被手工写入脏值（如 `HSET key abc`）
    时，原 `int(raw)` 抛 ValueError 会经 `_cfg` → `apply_result` → `check_device`
    冒泡，使该设备（乃至 worker 主循环）每轮探测异常、永久静默。解析失败回退 None
    后，`MonitorDynamicConfig.get` 返回 None，`_cfg` 据此回退 current_app.config 默认值，
    单点脏值不再拖垮探测。
    """
    try:
        if type_ == "int":
            return int(raw)
        if type_ == "float":
            return float(raw)
        if type_ == "bool":
            return str(raw).lower() in ("1", "true", "yes", "on")
        if type_ == "json":
            return json.loads(raw)
        return raw
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning(
            "动态配置类型转换失败：raw=%r type=%s，回退 None（走默认值）", raw, type_
        )
        return None


def _stringify(value: Any, type_: str) -> str:
    if type_ == "json":
        return json.dumps(value, ensure_ascii=False)
    if type_ == "bool":
        return "true" if value else "false"
    return str(value)


class MonitorDynamicConfig:
    """进程间共享的动态配置存储。

    必须在 Flask app context 内调用（Redis 客户端依赖 current_app）。
    """

    @staticmethod
    def _redis(app=None):
        from flask import current_app
        from app.services.monitoring.monitor_worker import _redis_client

        if app is None:
            target_app = current_app._get_current_object()
        else:
            target_app = app
        fn_id = id(_redis_client)
        with _redis_cache_lock:
            entry = _redis_clients.get(target_app)
            if entry is not None and entry[0] == fn_id:
                return entry[1]
            client = _redis_client(target_app)
            _redis_clients[target_app] = (fn_id, client)
            return client

    @classmethod
    def get(cls, key: str, app=None, session=None) -> Optional[Any]:
        """读取动态配置值（已按 value_type 解析）。

        miss（Redis 与 DB 皆无）返回 None，由 MonitorService._cfg 回退 current_app.config。

        `session`：可选注入的 SQLAlchemy Session（每任务独立 Session 场景）。传入时 DB
        回退读走该 session，避免与调用方独立事务争用 StaticPool 单连接（测试 / 批量路径）；
        缺省回落到 scoped db.session。
        """
        entry = all_entries().get(key)
        if entry is None:
            return None

        r = None
        try:
            r = cls._redis(app)
        except Exception as e:  # Redis 不可用：降级到 DB
            logger.warning("动态配置读 Redis 失败 key=%s: %s", key, e)

        if r is not None:
            try:
                raw = r.hget(REDIS_KEY, key)
            except Exception as e:  # Redis 不可达：降级到 DB fallback
                logger.warning("动态配置读 Redis 失败 key=%s: %s", key, e)
                raw = None
            if raw is not None:
                coerced = _coerce(raw, entry.type)
                if coerced is not None:
                    return coerced
                logger.warning(
                    "动态配置 Redis 值脏，降级到 DB fallback key=%s raw=%r", key, raw
                )

        from extensions import db

        repo = MonitorDynamicConfigRepository(
            session=session if session is not None else db.session
        )
        val = repo.get_value(key)
        if val is None:
            return None

        if r is not None:
            try:
                r.hsetnx(REDIS_KEY, key, val)
            except Exception:
                logger.warning("dynamic_config Redis hsetnx 失败", exc_info=True)
        return _coerce(val, entry.type)

    @classmethod
    def get_batch(cls, keys: list[str], app=None, session=None) -> Dict[str, Optional[Any]]:
        """批量读取动态配置值（单次 HMGET 替代 N 次 HGET）。

        返回 {key: parsed_value}，miss 的 key 值为 None（由调用方回退默认值）。
        Redis 不可用时逐个降级到 DB fallback。

        用途：monitor_service.check_device 每设备读 4 个配置项，
        N=2000 设备时从 8000 次 HGET 降至 2000 次 HMGET。
        """
        entries = all_entries()
        valid_keys = [k for k in keys if k in entries]
        if not valid_keys:
            return {k: None for k in keys}

        r = None
        try:
            r = cls._redis(app)
        except Exception as e:
            logger.warning("动态配置批量读 Redis 失败: %s", e)

        redis_vals: Dict[str, Optional[str]] = {}
        if r is not None:
            try:
                raw_list = r.hmget(REDIS_KEY, valid_keys)
                redis_vals = {k: v for k, v in zip(valid_keys, raw_list)}
            except Exception as e:
                logger.warning("动态配置批量读 Redis HMGET 失败: %s", e)

        result: Dict[str, Optional[Any]] = {}
        from extensions import db
        repo = MonitorDynamicConfigRepository(
            session=session if session is not None else db.session
        )

        for k in valid_keys:
            entry = entries[k]
            raw = redis_vals.get(k)
            if raw is not None:
                coerced = _coerce(raw, entry.type)
                if coerced is not None:
                    result[k] = coerced
                    continue
            val = repo.get_value(k)
            if val is not None:
                if r is not None:
                    try:
                        r.hsetnx(REDIS_KEY, k, val)
                    except Exception:
                        logger.warning("动态配置 hsetnx 失败 key=%s", k, exc_info=True)
                result[k] = _coerce(val, entry.type)
            else:
                result[k] = None

        for k in keys:
            if k not in result:
                result[k] = None

        return result

    @classmethod
    def set(cls, key: str, value: Any, updated_by: str = "", app=None) -> None:
        """双写 Redis + DB。调用方需保证 key 在白名单且 editable（API 层校验）。

        DB 侧的 commit 由外层事务（PUT 路由的 @transactional）收口。
        """
        entry = all_entries().get(key)
        if entry is None:
            raise ValidationError(f"配置项 {key} 不在白名单内")
        if not entry.editable:
            raise BusinessLogicError(f"配置项 {key} 不可在线修改（需重启服务）")

        sval = _stringify(value, entry.type)

        from extensions import db

        repo = MonitorDynamicConfigRepository(session=db.session)
        repo.upsert(key, sval, entry.type, entry.description, updated_by)

        try:
            r = cls._redis(app)
            r.hset(REDIS_KEY, key, sval)
        except Exception as e:
            logger.warning("动态配置写 Redis 失败 key=%s: %s", key, e)

    @classmethod
    def load_all_from_db(cls, app=None) -> None:
        """启动路径：DB 全量加载 -> 批量 HSET 回填 Redis。

        `app` 省略时回退到 `current_app`（与 `_redis()` 语义一致）；既无显式
        app 又不在 app context 内则明确报错，而不是抛晦涩的 AttributeError。
        """
        from extensions import db
        from flask import current_app, has_app_context

        if app is None:
            if not has_app_context():
                raise RuntimeError(
                    "load_all_from_db 需要显式传入 app，或调用时处于 app context 内"
                )
            app = current_app._get_current_object()

        with app.app_context():
            repo = MonitorDynamicConfigRepository(session=db.session)
            rows = repo.find_all()

        try:
            r = cls._redis(app)
        except Exception as e:
            logger.warning("动态配置启动加载写 Redis 失败: %s", e)
            return
        mapping = {row.config_key: row.config_value for row in rows}
        if mapping:
            try:
                r.hset(REDIS_KEY, mapping=mapping)
            except Exception as e:  # Redis 不可达：放弃回填，下次读走 DB fallback
                logger.warning("动态配置启动回填 Redis 失败: %s", e)


def get_all() -> dict:
    """返回当前生效的全部监控运行参数（I11：route handler 不再编排业务逻辑）。"""
    from flask import current_app
    data = {}
    for key, entry in all_entries().items():
        val = MonitorDynamicConfig.get(key)
        if val is None:
            val = current_app.config.get(key, entry.default)
        data[entry.camel] = {
            "value": val,
            "editable": entry.editable,
            "type": entry.type,
            "description": entry.description,
        }
    return data


def update_batch(updates: dict, updated_by: str = "unknown") -> list:
    """批量在线修改监控运行参数（I12：route handler 不再编排业务逻辑）。

    返回已更新的 camel key 列表。
    """
    updated = []
    for camel, value in updates.items():
        key = CAMEL_TO_KEY[camel]
        MonitorDynamicConfig.set(key, value, updated_by=updated_by)
        updated.append(camel)
    return updated
