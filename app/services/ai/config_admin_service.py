# -*- coding: utf-8 -*-
"""AI 配置管理服务：读取/运行时修改 AI Provider 配置。

安全设计：
- GET 返回 api_key 脱敏（仅末 4 位）
- PUT 修改运行时 Config 类属性 + 持久化到 Redis（I6 修复：多 worker 一致性）
- api_key 仅接受非空字符串，空字符串视为不修改

C1 修复（多 worker 配置跨进程同步）：
- update_config 写 Redis（key=ai:config）+ 发布 pub/sub 事件 + 更新当前进程 Config
- 各 worker 启动时订阅 pub/sub 频道，收到事件后重载 Redis 快照到本进程
- get_config 优先从 Redis 加载到当前进程，再读取
- worker 启动钩子 start_config_sync 主动拉一次 Redis 快照（消除冷启动窗口）
- Redis 不可用时降级为仅当前进程生效（单 worker 部署正确）

C3 修复（防止擦除已存密钥）：
- update_config 构建快照时，若本进程 AI_API_KEY 为空，则从 Redis 已存快照
  原样保留 api_key_enc，避免冷 worker 把空串写回 Redis 覆盖有效密钥。

Phase 0 修复（Celery 异步化配套，方案 C1 加固）：**env 优先于 Redis**。
- 优先级：部署级（环境变量）> 运行时（UI 修改 → Redis 快照）。
- 原因：Celery worker 是独立进程，env 是唯一能同时覆盖 gunicorn 与 celery
  两类进程的注入手段；若 Redis 快照里的旧值优先，部署侧下发的配置会被静默
  顶掉，冷 worker 因此误报「AI 未配置」。
- env 未设置（或空串）时 Redis 快照照常生效，UI 修改能力不受影响。
"""
import json
import os
import threading
from typing import Any, Dict

from config import Config


_CONFIG_FIELDS = {
    "provider": "AI_PROVIDER",
    "base_url": "AI_BASE_URL",
    "model": "AI_MODEL",
    "timeout": "AI_TIMEOUT",
    "stream_timeout": "AI_STREAM_TIMEOUT",
    "max_tokens": "AI_MAX_TOKENS",
    "temperature": "AI_TEMPERATURE",
}

_CONFIG_ENV_VARS = {attr: attr for attr in _CONFIG_FIELDS.values()}
_CONFIG_ENV_VARS["AI_API_KEY"] = "AI_API_KEY"


def _capture_env_overrides() -> Dict[str, str]:
    """采集模块加载时由 env 提供的配置值。

    必须在**模块导入时**采集：Config 的属性会随后被 Redis 快照 / UI 修改覆盖，
    那时已无法区分「值来自 env」还是「值来自运行时」。

    空串视为未提供——`AI_MODEL=` 是部署脚本常见写法，若当作已提供会把该字段
    永久冻结，UI 将无法再修改。

    Returns:
        {Config 属性名: env 值}，仅含非空值。
    """
    overrides = {}
    for attr, env_var in _CONFIG_ENV_VARS.items():
        val = os.getenv(env_var)
        if val:  # 空串/None 均视为未提供
            overrides[attr] = val
    return overrides


_ENV_OVERRIDES: Dict[str, str] = _capture_env_overrides()

_REDIS_KEY = "ai:config"
_REDIS_CHANNEL = "ai:config:changed"
_subscriber_thread: threading.Thread | None = None
_subscriber_started = False

_config_lock = threading.RLock()


def _get_redis():
    """复用 AI 层 Redis 接入点，失败返回 None。"""
    try:
        from app.services.ai._runtime import get_redis_client
        return get_redis_client()
    except Exception:  # noqa: BLE001
        return None


def _persist_to_redis(snapshot: Dict[str, Any]) -> None:
    """将配置快照持久化到 Redis（best-effort，失败仅告警）。"""
    r = _get_redis()
    if r is None:
        return
    try:
        r.set(_REDIS_KEY, json.dumps(snapshot, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        from app.utils.logging import get_logger
        get_logger(__name__).warning("ai.config.persist_failed %s", e)


def _load_from_redis() -> Dict[str, Any] | None:
    """从 Redis 加载配置快照，不存在或 Redis 不可用返回 None。"""
    r = _get_redis()
    if r is None:
        return None
    try:
        val = r.get(_REDIS_KEY)
        if val is None:
            return None
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        return json.loads(val)
    except Exception as e:  # noqa: BLE001
        from app.utils.logging import get_logger
        get_logger(__name__).warning("ai.config.load_failed %s", e)
        return None


def _apply_to_config(snapshot: Dict[str, Any]) -> None:
    """将 Redis 快照应用到当前进程 Config 类属性（best-effort）。

    Phase 0：`_ENV_OVERRIDES` 中存在的字段**跳过**——env 是部署级配置，优先级
    高于 Redis 里的运行时快照（详见模块 docstring）。

    A6 修复：整段应用过程持 `_config_lock`，保证并发调用方（get_config 读路径
    同步 vs pub/sub 重载线程）不会写出半新半旧的 Config。
    """
    from app.utils.logging import get_logger
    _logger = get_logger(__name__)
    with _config_lock:
        for field, attr in _CONFIG_FIELDS.items():
            if field not in snapshot:
                continue
            if attr in _ENV_OVERRIDES:
                continue  # env 优先：Redis 不得覆盖部署级配置
            try:
                setattr(Config, attr, snapshot[field])
            except Exception as e:  # noqa: BLE001
                _logger.warning("ai.config.apply_field_failed %s=%s: %s", field, attr, e)
        api_key_enc = snapshot.get("api_key_enc")
        if api_key_enc and "AI_API_KEY" not in _ENV_OVERRIDES:
            try:
                from app.utils.security.encryption import decrypt
                setattr(Config, "AI_API_KEY", decrypt(api_key_enc))
            except Exception as e:  # noqa: BLE001
                _logger.warning("ai.config.api_key_decrypt_failed %s", e)


def _publish_config_changed() -> None:
    """C1 修复：发布 Redis pub/sub 事件，通知其他 worker 重载配置。"""
    r = _get_redis()
    if r is None:
        return
    try:
        r.publish(_REDIS_CHANNEL, "1")
    except Exception as e:  # noqa: BLE001
        from app.utils.logging import get_logger
        get_logger(__name__).warning("ai.config.publish_failed %s", e)


def _config_subscriber_loop() -> None:
    """C1 修复：pub/sub 订阅循环，收到事件后从 Redis 重载快照到本进程。"""
    from app.utils.logging import get_logger
    _logger = get_logger(__name__)
    try:
        r = _get_redis()
        if r is None:
            return
        pubsub = r.pubsub()
        pubsub.subscribe(_REDIS_CHANNEL)
        _logger.info("ai.config.subscriber_started channel=%s", _REDIS_CHANNEL)
        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                snapshot = _load_from_redis()
                if snapshot is not None:
                    _apply_to_config(snapshot)
                    from app.services.ai.llm_factory import invalidate_client_cache
                    invalidate_client_cache()
                    _logger.debug("ai.config.reloaded_from_pubsub")
            except Exception as e:  # noqa: BLE001
                _logger.warning("ai.config.subscriber_handle_failed %s", e)
    except Exception as e:  # noqa: BLE001
        _logger.warning("ai.config.subscriber_loop_exit %s", e)


def start_config_sync() -> None:
    """C1 修复：worker 启动钩子——主动拉一次 Redis 快照 + 启动 pub/sub 订阅。

    在 create_app 中调用，消除冷 worker 永远读不到配置的窗口。
    幂等：多次调用只启动一个订阅线程。
    """
    global _subscriber_thread, _subscriber_started
    from app.utils.logging import get_logger
    _logger = get_logger(__name__)
    try:
        snapshot = _load_from_redis()
        if snapshot is not None:
            _apply_to_config(snapshot)
            _logger.info("ai.config.boot_synced_from_redis")
    except Exception as e:  # noqa: BLE001
        _logger.warning("ai.config.boot_sync_failed %s", e)
    with _config_lock:
        if _subscriber_started:
            return
        try:
            r = _get_redis()
            if r is None:
                return  # Redis 不可用，降级为单进程模式
            _subscriber_thread = threading.Thread(
                target=_config_subscriber_loop, name="ai-config-subscriber", daemon=True
            )
            _subscriber_thread.start()
            _subscriber_started = True
        except Exception as e:  # noqa: BLE001
            _logger.warning("ai.config.subscriber_start_failed %s", e)


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


def get_config() -> Dict[str, Any]:
    """读取当前 AI 配置（api_key 脱敏）。

    I6 修复：优先从 Redis 同步到当前进程，确保多 worker 间配置一致。
    S3 完整修复：api_key 加密后落 Redis（api_key_enc），_apply_to_config
    解密恢复到 Config.AI_API_KEY，故重启/其他 worker 均可同步。
    api_key_local_only 保留为兜底：解密失败时仍提示"本进程未同步"。
    """
    snapshot = _load_from_redis()
    if snapshot is not None:
        _apply_to_config(snapshot)
    configured_elsewhere = bool((snapshot or {}).get("api_key_configured"))
    with _config_lock:
        configured_here = bool(Config.AI_API_KEY)
        return {
            "provider": Config.AI_PROVIDER,
            "base_url": Config.AI_BASE_URL,
            "model": Config.AI_MODEL,
            "timeout": Config.AI_TIMEOUT,
            "stream_timeout": Config.AI_STREAM_TIMEOUT,
            "max_tokens": Config.AI_MAX_TOKENS,
            "temperature": Config.AI_TEMPERATURE,
            "api_key_masked": _mask_key(Config.AI_API_KEY),
            "api_key_configured": configured_here,
            "api_key_local_only": configured_elsewhere and not configured_here,
        }


def _apply_updates_to_config(updates: Dict[str, Any],
                             changed: list, locked: list) -> None:
    """把校验通过的更新写入 Config 类属性（调用方必须持有 `_config_lock`）。

    分离出来是为了让 `update_config` 的锁区间只覆盖内存写——持久化到 Redis 与
    发布 pub/sub 事件是网络 I/O，不应占着配置锁（A6）。

    Args:
        updates: 待更新字段。
        changed: 出参，实际写入的字段名。
        locked:  出参，被部署环境变量锁定而跳过的字段名。

    Raises:
        ValueError: 字段类型/范围校验失败，或 provider 未注册。
    """
    for field, attr in _CONFIG_FIELDS.items():
        if field not in updates:
            continue
        if attr in _ENV_OVERRIDES:
            locked.append(field)
            continue
        val = updates[field]
        try:
            if attr in ("AI_TIMEOUT", "AI_STREAM_TIMEOUT", "AI_MAX_TOKENS"):
                val = int(val)
                if val <= 0:
                    raise ValueError(f"{field} 必须为正整数")
                if attr == "AI_MAX_TOKENS" and val > 32768:
                    raise ValueError(f"{field} 不能超过 32768")
                if attr in ("AI_TIMEOUT", "AI_STREAM_TIMEOUT") and val > 600:
                    raise ValueError(f"{field} 不能超过 600 秒")
            elif attr == "AI_TEMPERATURE":
                val = float(val)
                if not 0.0 <= val <= 2.0:
                    raise ValueError("temperature 必须在 0.0 ~ 2.0 之间")
            elif attr in ("AI_PROVIDER", "AI_BASE_URL", "AI_MODEL"):
                val = str(val)
                if not val:
                    raise ValueError(f"{field} 不能为空")
                if attr == "AI_PROVIDER":
                    from app.services.ai.llm_factory import list_providers
                    registered = list_providers()
                    if val not in registered:
                        raise ValueError(
                            f"provider {val!r} 未注册，已注册: {registered}"
                        )
        except (TypeError, ValueError) as e:
            raise ValueError(f"字段 {field} 校验失败：{e}") from e
        setattr(Config, attr, val)
        changed.append(field)

    if "api_key" in updates and updates["api_key"]:
        if "AI_API_KEY" in _ENV_OVERRIDES:
            locked.append("api_key")
        else:
            setattr(Config, "AI_API_KEY", str(updates["api_key"]))
            changed.append("api_key")


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """运行时更新 AI 配置。返回更新后的配置（脱敏）。

    可更新字段：provider/base_url/model/timeout/stream_timeout/max_tokens/temperature/api_key

    I6 修复：更新当前进程 Config + 持久化到 Redis，其他 worker 在下次 get_config 时同步。
    api_key 不持久化到 Redis（敏感凭据，仅当前进程生效，其他 worker 从环境变量读取）。
    """
    changed: list[str] = []
    locked: list[str] = []
    with _config_lock:
        _apply_updates_to_config(updates, changed, locked)

    if not changed:
        raise ValueError("无有效更新字段")

    api_key_enc = ""
    if getattr(Config, "AI_API_KEY", None):
        try:
            from app.utils.security.encryption import encrypt
            api_key_enc = encrypt(Config.AI_API_KEY)
        except Exception as e:  # noqa: BLE001
            from app.utils.logging import get_logger
            get_logger(__name__).warning("ai.config.api_key_encrypt_failed %s", e)
    elif "api_key" not in updates or not updates.get("api_key"):
        existing = _load_from_redis() or {}
        api_key_enc = existing.get("api_key_enc", "")
    snapshot = {
        "provider": Config.AI_PROVIDER,
        "base_url": Config.AI_BASE_URL,
        "model": Config.AI_MODEL,
        "timeout": Config.AI_TIMEOUT,
        "stream_timeout": Config.AI_STREAM_TIMEOUT,
        "max_tokens": Config.AI_MAX_TOKENS,
        "temperature": Config.AI_TEMPERATURE,
        "api_key_configured": bool(getattr(Config, "AI_API_KEY", None)) or bool(api_key_enc),
        "api_key_enc": api_key_enc,
    }
    _persist_to_redis(snapshot)
    _publish_config_changed()

    from app.services.ai.llm_factory import invalidate_client_cache
    invalidate_client_cache()

    result = get_config()
    result["changed"] = changed
    result["locked"] = locked
    return result
