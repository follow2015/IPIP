# -*- coding: utf-8 -*-
"""安全策略读写：进程内 5s 缓存 → Redis Hash → DB → 注册表默认值。

设计依据：总纲 §6.2（读路径）/ §6.3（失败语义）、一期文档 §4.1。


读路径任何一环失败都**回退到注册表默认值**而不是抛异常：安全策略是"闸门"的输入，
让缓存/DB 抖动把登录或凭据保存整条链路打挂，代价远大于"这次按默认值判"。
"默认值 = 现状"（由 `policy_registry` 的测试钉住）因此也是失败语义的安全网 ——
最坏情况退化为升级前的行为。


DB-first（含乐观锁与审计 `before`/`after`）→ 再刷 Redis 与进程缓存。
反过来的话，Redis 写成功而 DB 失败会造成"缓存里的策略与库里不一致且无人知道"。
Redis 写失败只告警（DB 已是权威源，下次缓存过期仍读得到正确值）。
"""
import json
import time

from app.models.security_policy import SecurityPolicy
from app.persistence.security_policy_repository import SecurityPolicyRepository
from app.services.security.policy_registry import POLICIES, get_item
from app.utils import redis_keys
from app.utils.logging import get_logger
from app.utils.redis_client import get_redis_client
from extensions import db

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 5.0
_cache: dict = {}


def _redis_client():
    """取 Redis 客户端；不可用返回 None（读路径据此回退 DB）。"""
    try:
        return get_redis_client()
    except Exception:
        logger.warning("安全策略：Redis 客户端不可用，回退 DB", exc_info=True)
        return None


def _raw_from_redis(keys: list) -> dict:
    """HMGET 取原始字符串值；失败返回空 dict。"""
    if not keys:
        return {}
    client = _redis_client()
    if client is None:
        return {}
    try:
        values = client.hmget(redis_keys.SECURITY_POLICY_KEY, keys)
        return {k: (v.decode() if isinstance(v, bytes) else v)
                for k, v in zip(keys, values, strict=False) if v is not None}
    except Exception:
        logger.warning("安全策略：读 Redis 失败，回退 DB", exc_info=True)
        return {}


def _raw_from_db(keys: list) -> dict:
    """读 DB 覆盖行并回填 Redis；DB 也失败返回空 dict（= 全用默认值）。"""
    if not keys:
        return {}
    try:
        rows = SecurityPolicyRepository().find_by_keys(keys)
    except Exception:
        logger.warning("安全策略：读 DB 失败，回退注册表默认值", exc_info=True)
        return {}
    data = {row.policy_key: json.dumps(row.value_json, ensure_ascii=False) for row in rows}
    client = _redis_client()
    if client is not None and data:
        try:
            client.hset(redis_keys.SECURITY_POLICY_KEY, mapping=data)
        except Exception:
            logger.warning("安全策略：回填 Redis 失败（忽略，DB 是权威源）", exc_info=True)
    return data


def _decode(raw, item):
    """原始字符串 → 值；解析失败或缺失时回注册表默认值。"""
    if raw is None:
        return item.default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("安全策略 %s 的值无法解析，回退默认值", item.key, exc_info=True)
        return item.default


def clear_cache() -> None:
    """清空策略缓存（进程内字典 + Redis Hash），强制下次读取回源 DB。

    为什么两层都要清：读路径是 **进程缓存 → Redis → DB**，只清进程字典的话下次仍会
    命中 Redis 里的旧值，"强制回读"名不副实。Redis 只是缓存层、DB 才是权威源 —— 清掉
    `security:policies` 无副作用，只是下次读多一次 DB 查询（见 redis_keys 登记）。

    用途：测试隔离（这两层都不随 `_db_transaction` 的 DB 回滚而失效），以及运维排查时
    强制回读。生产中不必调用 —— 缓存 TTL 只有 5s。
    """
    _cache.clear()
    client = _redis_client()
    if client is not None:
        try:
            client.delete(redis_keys.SECURITY_POLICY_KEY)
        except Exception:
            logger.warning("安全策略：清 Redis 缓存失败（忽略，DB 是权威源）", exc_info=True)


def get_value(key: str):
    """读单个策略值（任何异常都回注册表默认值，不抛）。

    Args:
        key: 策略键（必须在注册表中，否则 KeyError）。

    Returns:
        策略值；无覆盖行时为注册表默认值。
    """
    item = get_item(key)
    hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
        return hit[1]
    raw = _raw_from_redis([key])
    if key not in raw:
        raw.update(_raw_from_db([key]))
    value = _decode(raw.get(key), item)
    _cache[key] = (time.monotonic(), value)
    return value


def get_all_items() -> list:
    """全部策略项（当前值 / 默认值 / 范围 / 说明 / 覆盖行版本），供策略页渲染。"""
    keys = list(POLICIES)
    raw = _raw_from_redis(keys)
    missing = [k for k in keys if k not in raw]
    if missing:
        raw.update(_raw_from_db(missing))
    rows = {}
    try:
        rows = SecurityPolicyRepository().map_by_keys(keys)
    except Exception:
        logger.warning("安全策略：读覆盖行版本失败（忽略）", exc_info=True)

    items = []
    for key, item in POLICIES.items():
        row = rows.get(key)
        items.append({
            "key": key,
            "value": _decode(raw.get(key), item),
            "default": item.default,
            "type": item.type,
            "min": item.min,
            "max": item.max,
            "choices": list(item.choices),
            "description": item.description,
            "tag": item.tag,
            "editable": item.editable,
            "version": row.version if row is not None else None,
            "updated_by": row.updated_by if row is not None else None,
        })
    return items


def _validate_value(item, value) -> None:
    """类型 / 范围 / 跨项一致性校验。

    Raises:
        ValidationError: 值不合法。
    """
    import ipaddress

    from app.exceptions import ValidationError

    if item.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{item.key} 必须是整数")
        if item.min is not None and value < item.min:
            raise ValidationError(f"{item.key} 不得小于 {item.min}")
        if item.max is not None and value > item.max:
            raise ValidationError(f"{item.key} 不得大于 {item.max}")
    elif item.type == "bool":
        if not isinstance(value, bool):
            raise ValidationError(f"{item.key} 必须是布尔值")
    elif item.type == "choice":
        if value not in item.choices:
            raise ValidationError(f"{item.key} 仅允许 {list(item.choices)}")
    elif item.type == "json":
        if item.key == "snmp.allowed_versions":
            if not isinstance(value, list) or not value:
                raise ValidationError("snmp.allowed_versions 必须是非空列表")
            if set(value) - {"v2c", "v3"}:
                raise ValidationError("snmp.allowed_versions 的元素只能是 v2c / v3")
        elif item.key == "login.trusted_networks":
            if not isinstance(value, list):
                raise ValidationError("login.trusted_networks 必须是列表")
            for cidr in value:
                try:
                    ipaddress.ip_network(str(cidr), strict=False)
                except ValueError as exc:
                    raise ValidationError(f"login.trusted_networks 含非法 CIDR: {cidr}") from exc
        else:
            raise ValidationError(f"{item.key} 的类型 {item.type} 尚未支持校验")
    else:
        raise ValidationError(f"{item.key} 的类型 {item.type} 尚未支持")


def set_value(key: str, value, updated_by=None, expected_version=None) -> dict:
    """写策略：校验 → 乐观锁 → 落库 → 刷缓存 → 审计（before/after）。

    Args:
        key: 策略键。
        value: 新值（按注册表类型校验）。
        updated_by: 操作人 users.id。
        expected_version: 前端传来的版本号（乐观锁）；不匹配则拒绝。

    Raises:
        ValidationError: 值非法 / 项不可改 / 版本冲突。

    Returns:
        {"key": ..., "value": ..., "version": ...}
    """
    from app.exceptions import ValidationError
    from app.services.audit_service import AuditService

    item = get_item(key)
    if not item.editable:
        raise ValidationError(f"{key} 不可在线修改")
    _validate_value(item, value)

    before = get_value(key)
    row = db.session.get(SecurityPolicy, key)
    if row is None:
        row = SecurityPolicy(policy_key=key, value_json=value, version=1, updated_by=updated_by)
        db.session.add(row)
    else:
        if expected_version is not None and row.version != expected_version:
            raise ValidationError(
                f"策略已被他人修改（当前版本 {row.version}），请刷新后重试"
            )
        row.value_json = value
        row.version = row.version + 1
        row.updated_by = updated_by
    db.session.commit()

    _cache.pop(key, None)
    client = _redis_client()
    if client is not None:
        try:
            client.hset(redis_keys.SECURITY_POLICY_KEY, key, json.dumps(value, ensure_ascii=False))
        except Exception:
            logger.warning("安全策略：刷 Redis 失败（忽略，DB 是权威源）", exc_info=True)

    AuditService().log(
        user_id=updated_by,
        action="security.policy.update",
        resource="security_policy",
        resource_id=None,
        detail={"key": key, "before": before, "after": value},
    )
    return {"key": key, "value": value, "version": row.version}


def load_all_from_db(app=None) -> None:
    """启动期把 DB 覆盖行全量刷进 Redis（best-effort，失败不影响启动）。"""
    keys = list(POLICIES)
    try:
        raw = _raw_from_db(keys)
        logger.info("安全策略已在启动期回填 Redis（%d 条覆盖行）", len(raw))
    except Exception:
        if app is not None:
            app.logger.warning("安全策略启动回填失败（忽略）", exc_info=True)
        else:
            logger.warning("安全策略启动回填失败（忽略）", exc_info=True)
