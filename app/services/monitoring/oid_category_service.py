# -*- coding: utf-8 -*-
"""OID 分类打标服务

探测后对每条 OID 按 monitor_oid_category_rules 规则打 category 标签。
规则匹配用点分隔符锚定（oid == prefix or oid.startswith(prefix + '.')），
避免 1.7 误命中 1.70。

优化：
- vendor_id 锚定：从 sysObjectID 提取 enterprise 号，先匹配厂商规则再匹配通用
- priority 降序 + 短路 break：命中高优先级即止
- Redis 缓存：规则变更低频，缓存 5 分钟，规则 CRUD 时主动失效
"""
import json
from app.utils.logging import get_logger
from typing import Any

logger = get_logger(__name__)

_RULES_CACHE_TTL = 300  # 5 分钟
_RULES_CACHE_PREFIX = "monitor:oid-rules:"
_RECOMMEND_CACHE_PREFIX = "monitor:recommend-config:"


def _get_redis():
    """获取 Redis 客户端，不可用返回 None"""
    try:
        from app.services.scan_redis import get_scan_redis_client
        return get_scan_redis_client()
    except Exception:  # noqa: BLE001
        logger.warning("获取 Redis 客户端失败", exc_info=True)
        return None


def _extract_vendor_id(raw_oids: list[dict]) -> str | None:
    """从 walk 结果中找 sysObjectID（1.3.6.1.2.1.1.2.0），提取 enterprise 号。

    sysObjectID 的值可能是：
    - pysnmp prettyPrint: "SNMPv2-SMI::enterprises.674.10892.5"
    - 纯数字 OID: "1.3.6.1.4.1.674.10892.5"
    enterprise 号是厂商标识（674=DELL, 232=HP, 10876=Supermicro, 19046=Lenovo）。
    解析逻辑复用 snmp_mib_service._extract_enterprise，避免两处重复。
    """
    for row in raw_oids:
        if row.get("oid") == "1.3.6.1.2.1.1.2.0":
            from app.services.monitoring.snmp_mib_service import _extract_enterprise
            return _extract_enterprise(str(row.get("value", "")))
    return None


def extract_vendor_id(raw_oids: list[dict]) -> str | None:
    """公共接口：从 walk 结果提取设备 enterprise 号（供 MIB 扫描返回透传）。"""
    return _extract_vendor_id(raw_oids)


def _load_rules(vendor_id: str | None, device_type: str | None = None) -> list[dict]:
    """加载规则（Redis 缓存 → DB），按 priority 降序。

    匹配 vendor_id 相同的 + vendor_id IS NULL 的通用规则。
    device_type 可选过滤：传值时排除 device_type 不匹配的规则。
    """
    cache_key = f"{_RULES_CACHE_PREFIX}{vendor_id or 'common'}:{device_type or 'any'}"
    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:  # noqa: BLE001
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)

    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    rule_repo = MonitorOidCategoryRuleRepository()
    rows = rule_repo.find_enabled_by_vendor(vendor_id, device_type=device_type)
    rules = [
        {
            "prefix": row.prefix,
            "category": row.category,
            "label": row.label,
            "priority": row.priority,
        }
        for row in rows
    ]

    if r is not None:
        try:
            r.set(cache_key, json.dumps(rules), ex=_RULES_CACHE_TTL)
        except Exception:  # noqa: BLE001
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)
    return rules


def _load_rule_prefixes() -> list[str]:
    """加载所有启用的规则前缀（不分 vendor/device_type），供 _filter_noise_oids 判断
    父 OID 是否有规则保护（有规则则不判为序号表，避免误杀温度/电压探针索引表）。
    """
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    rule_repo = MonitorOidCategoryRuleRepository()
    from extensions import db
    from app.models.monitor_oid_category_rule import MonitorOidCategoryRule
    rows = db.session.query(MonitorOidCategoryRule.prefix).filter_by(enabled=1).all()
    return [r[0] for r in rows]


def _match_oid(oid: str, prefix: str) -> bool:
    """点分隔符锚定匹配：oid == prefix 或 oid 以 prefix + '.' 开头"""
    return oid == prefix or oid.startswith(prefix + ".")


_HEURISTIC_RULES = [
    {"segment": ".5.4.300.40",  "category": "temperature",  "label": "温度"},
    {"segment": ".5.4.600.20",  "category": "voltage",      "label": "电压"},
    {"segment": ".5.4.700.12",  "category": "fan",          "label": "风扇转速"},
    {"segment": ".5.4.700.20",  "category": "fan",          "label": "风扇转速"},
    {"segment": ".5.4.1100.80", "category": "power_supply", "label": "电源"},
    {"segment": ".5.4.200.10",  "category": "memory",       "label": "内存"},
    {"segment": ".5.4.200.20",  "category": "memory",       "label": "内存"},
    {"segment": ".5.4.40.10",   "category": "storage",      "label": "存储"},
    {"segment": ".5.4.40.20",   "category": "storage",      "label": "存储"},
    {"segment": ".5.4.40.30",   "category": "storage",      "label": "存储"},
]
_ENTERPRISE_PREFIX = "1.3.6.1.4.1."

_STANDARD_MIB_RULES = [
    {"prefix": "1.3.6.1.2.1.1.3.",   "category": "system_uptime",   "label": "系统运行时间"},  # sysUpTime (SNMPv2-MIB，交换机/路由器普遍支持)
    {"prefix": "1.3.6.1.2.1.25.1.1.", "category": "system_uptime",   "label": "系统运行时间"},  # hrSystemUptime (HOST-RESOURCES-MIB，服务器支持)
    {"prefix": "1.3.6.1.2.1.2.2.1.8.",  "category": "if_status",      "label": "端口状态"},      # ifOperStatus
    {"prefix": "1.3.6.1.2.1.2.2.1.10.", "category": "if_in_octets",   "label": "入向流量"},      # ifInOctets
    {"prefix": "1.3.6.1.2.1.2.2.1.16.", "category": "if_out_octets",  "label": "出向流量"},      # ifOutOctets
    {"prefix": "1.3.6.1.2.1.2.2.1.14.", "category": "if_in_errors",   "label": "入向错误包"},
    {"prefix": "1.3.6.1.2.1.2.2.1.20.", "category": "if_out_errors",  "label": "出向错误包"},
    {"prefix": "1.3.6.1.2.1.2.2.1.13.", "category": "if_in_discards", "label": "入向丢弃包"},
    {"prefix": "1.3.6.1.2.1.2.2.1.19.", "category": "if_out_discards","label": "出向丢弃包"},
    {"prefix": "1.3.6.1.2.1.99.1.1.1.5.", "category": "entity_sensor", "label": "物理传感器"},
]

_ENTITY_SENSOR_TYPE_MAP = {
    1: "other",
    2: "unknown",
    3: "voltage",
    4: "current",
    5: "power",
    6: "frequency",
    8: "temperature",     # celsius
    9: "humidity",
    10: "fan",            # rpm
    15: "power_supply",   # boolean on/off
}

_LOW_VALUE_CATEGORIES = frozenset({
    "threshold_descriptor",
})


def _match_standard_mib(oid: str) -> dict | None:
    """标准 MIB-2 层匹配：识别 IF-MIB / HOST-RESOURCES-MIB 等标准子树。

    与启发式（仅私有子树）互补，覆盖标准 MIB-2 OID（如 ifOperStatus、hrSystemUptime），
    使其即使无精确规则也能打 category 标签。
    """
    for rule in _STANDARD_MIB_RULES:
        if oid.startswith(rule["prefix"]):
            return {"category": rule["category"], "label": rule["label"]}
    return None


def _match_heuristic(oid: str) -> dict | None:
    """启发式语义匹配：识别企业私有子树内符合通用 DCIM 布局的 OID。

    仅对 ``1.3.6.1.4.1.`` 开头的私有子树 OID 生效；命中返回
    ``{"category", "label"}``，否则返回 None。OID 末尾可能带实例下标
    （如 .300.40.1.2.1.1），segment 用「包含」而非前缀锚定以兼容。
    """
    if not oid.startswith(_ENTERPRISE_PREFIX):
        return None
    for rule in _HEURISTIC_RULES:
        if rule["segment"] in oid:
            return {"category": rule["category"], "label": rule["label"]}
    return None


def categorize_oids(
    raw_oids: list[dict],
    device_type: str | None = None,
    sensor_type_map: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """对探测结果打 category 标签（三级匹配）。

    匹配顺序（一级命中即止，越靠前越准）：
    1. 精确规则：monitor_oid_category_rules（vendor 锚定，人工/沉淀的规则）
    2. 启发式：通用 DCIM 子树布局兜底（P0，跨品牌，换品牌零手工）
    3. 标准层：标准 MIB-2 子树（IF-MIB / HOST-RESOURCES-MIB / ENTITY-SENSOR-MIB 等）
    4. 兜底：无标签（category=None）

    Args:
        raw_oids: scan_device 返回的 detected 列表，每条有 oid/value/type
        device_type: 可选，设备类型 network/server/other；传值时精确规则按 device_type 过滤
        sensor_type_map: 可选，entPhySensorType 的 index→type 值映射，
            用于 ENTITY-SENSOR-MIB 联表细分（温度/电压/风扇/电源）。

    Returns:
        (tagged_oids, category_summary)
        - tagged_oids: 每条多 category/category_label 字段
        - category_summary: {category: count} 聚合统计
    """
    if not raw_oids:
        return [], {}

    vendor_id = _extract_vendor_id(raw_oids)
    rules = _load_rules(vendor_id, device_type=device_type)

    category_summary: dict[str, int] = {}
    for row in raw_oids:
        oid = row.get("oid", "")
        row["category"] = None
        row["category_label"] = None
        row["category_source"] = None
        for rule in rules:
            if _match_oid(oid, rule["prefix"]):
                row["category"] = rule["category"]
                row["category_label"] = rule["label"]
                row["category_source"] = "rule"
                category_summary[rule["category"]] = category_summary.get(rule["category"], 0) + 1
                break
        if row["category"]:
            continue
        heuristic = _match_heuristic(oid)
        if heuristic:
            row["category"] = heuristic["category"]
            row["category_label"] = heuristic["label"]
            row["category_source"] = "heuristic"
            category_summary[heuristic["category"]] = category_summary.get(heuristic["category"], 0) + 1
            continue
        standard = _match_standard_mib(oid)
        if standard:
            row["category"] = standard["category"]
            row["category_label"] = standard["label"]
            row["category_source"] = "standard_mib"
            if standard["category"] == "entity_sensor" and sensor_type_map:
                idx = oid.rsplit(".", 1)[-1]
                type_val = sensor_type_map.get(idx)
                if type_val is not None:
                    refined = _ENTITY_SENSOR_TYPE_MAP.get(type_val)
                    if refined:
                        row["category"] = refined
            category_summary[row["category"]] = category_summary.get(row["category"], 0) + 1

    if _LOW_VALUE_CATEGORIES:
        kept = [r for r in raw_oids if r.get("category") not in _LOW_VALUE_CATEGORIES]
        for cat in _LOW_VALUE_CATEGORIES:
            category_summary.pop(cat, None)
        return kept, category_summary

    return raw_oids, category_summary


def get_recommended_categories(device_type: str) -> list[str]:
    """获取设备类型推荐的 category 列表（Redis 缓存 → DB）"""
    cache_key = f"{_RECOMMEND_CACHE_PREFIX}{device_type}"
    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:  # noqa: BLE001
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)

    from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
    recommend_repo = MonitorDeviceTypeRecommendRepository()
    row = recommend_repo.find_by_device_type(device_type)
    categories = row.categories if row else []

    if r is not None:
        try:
            r.set(cache_key, json.dumps(categories), ex=_RULES_CACHE_TTL)
        except Exception:  # noqa: BLE001
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)
    return categories


def invalidate_rules_cache(vendor_id: str | None = None) -> None:
    """规则 CRUD 后主动失效缓存"""
    r = _get_redis()
    if r is None:
        return
    try:
        for key in r.scan_iter(f"{_RULES_CACHE_PREFIX}*"):
            r.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("invalidate_rule_cache 失败", exc_info=True)


def invalidate_recommend_cache() -> None:
    """推荐配置 CRUD 后主动失效缓存"""
    r = _get_redis()
    if r is None:
        return
    try:
        for key in r.scan_iter(f"{_RECOMMEND_CACHE_PREFIX}*"):
            r.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("invalidate_recommend_cache 失败", exc_info=True)



def list_rules() -> list:
    """列出全部 OID 分类规则。"""
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    repo = MonitorOidCategoryRuleRepository()
    return [r.to_dict() for r in repo.list_all()]


def create_rule(data: dict) -> dict:
    """新增 OID 分类规则。"""
    from app.models.monitor_oid_category_rule import MonitorOidCategoryRule
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    from app.exceptions.validation import ValidationError
    prefix = data.get("prefix")
    category = data.get("category")
    if not prefix or not category:
        raise ValidationError("prefix / category 必填")
    repo = MonitorOidCategoryRuleRepository()
    rule = MonitorOidCategoryRule(
        prefix=prefix,
        category=category,
        label=data.get("label"),
        device_type=data.get("device_type"),
        vendor_id=data.get("vendor_id"),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
    )
    repo.add(rule)
    invalidate_rules_cache()
    return {"id": rule.id}


def _heuristic_rule_prefix(oid: str) -> str | None:
    """从启发式命中的 OID 推导精确规则前缀（P1 沉淀用）。

    给定 ``1.3.6.1.4.1.674.10892.5.4.300.40.1.2.1.1``，匹配 segment
    ``.5.4.300.40``，生成精确到 fieldId 的前缀：
    - 读数（.1.2）→ ``1.3.6.1.4.1.674.10892.5.4.300.40.1.2``
    - 状态（.1.11）→ ``...1.11``
    规则命中后能覆盖该设备的全部同类读数/状态实例（probeIndex 在下标层）。
    返回 None 表示该 OID 不匹配任何启发式规则。
    """
    for rule in _HEURISTIC_RULES:
        seg = rule["segment"]
        if seg in oid:
            base = oid.split(seg, 1)[0] + seg
            rest = oid.split(seg, 1)[1]
            return base + (".1.11" if ".1.11" in rest else ".1.2")
    return None


def persist_heuristic_rule(oid: str, device_type: str, vendor_id: str | None = None) -> dict:
    """把启发式命中的类别沉淀为精确规则（P1）。

    将某次探测里由「通用 DCIM 布局启发式」打标的 OID，固化成 vendor 专属的
    ``monitor_oid_category_rules`` 精确前缀规则，下次探测直接命中（不再走
    启发式），规则库随探测设备自动生长。

    Args:
        oid: 探测结果里某条 OID（须已被启发式打标）
        device_type: 设备类型 network/server/other
        vendor_id: 设备 enterprise 号（如 674）；None 则存为通用规则

    Returns:
        {"id": rule_id}
    """
    from app.exceptions.validation import ValidationError

    heuristic = _match_heuristic(oid)
    prefix = _heuristic_rule_prefix(oid)
    if not heuristic or not prefix:
        raise ValidationError("该 OID 不匹配可沉淀的启发式类别，无法存为规则")
    return create_rule(
        {
            "prefix": prefix,
            "category": heuristic["category"],
            "label": heuristic["label"],
            "device_type": device_type,
            "vendor_id": vendor_id,
            "priority": 100,
            "enabled": True,
        }
    )


def update_rule(rule_id: int, data: dict) -> dict:
    """更新 OID 分类规则。"""
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorOidCategoryRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("OID 分类规则不存在", status_code=404)
    for k in ("prefix", "category", "label", "device_type", "vendor_id", "priority", "enabled"):
        if k in data:
            setattr(rule, k, data[k])
    repo.flush()
    invalidate_rules_cache()
    return {"id": rule.id}


def delete_rule(rule_id: int) -> dict:
    """删除 OID 分类规则。"""
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorOidCategoryRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("OID 分类规则不存在", status_code=404)
    repo.delete(rule)
    invalidate_rules_cache()
    return {"id": rule_id}


def list_recommends() -> list:
    """列出全部设备类型推荐配置。"""
    from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
    repo = MonitorDeviceTypeRecommendRepository()
    return [r.to_dict() for r in repo.list_all()]


def update_recommend(device_type: str, categories: list) -> dict:
    """更新设备类型推荐配置（upsert）。"""
    from app.models.monitor_device_type_recommend import MonitorDeviceTypeRecommend
    from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
    from app.exceptions.validation import ValidationError
    if not isinstance(categories, list):
        raise ValidationError("categories 必须为数组")
    repo = MonitorDeviceTypeRecommendRepository()
    row = repo.find_by_device_type(device_type)
    if row:
        row.categories = categories
    else:
        row = MonitorDeviceTypeRecommend(device_type=device_type, categories=categories)
        repo.add(row)
    repo.flush()
    invalidate_recommend_cache()
    return {"device_type": device_type, "categories": categories}


_CATEGORY_DEFAULTS = {
    "temperature":    ("gauge",  "Celsius", "温度",       "warn"),
    "disk_temperature": ("gauge", "Celsius", "磁盘温度",  "warn"),
    "voltage":        ("gauge",  "V",       "电压",       "warn"),
    "fan":            ("gauge",  "RPM",     "风扇转速",   "warn"),
    "power_supply":   ("state",  None,      "电源状态",   "crit"),
    "memory":         ("gauge",  "MB",      "内存",       "warn"),
    "storage":        ("state",  None,      "存储状态",   "crit"),
    "cpu_usage":      ("gauge",  "%",       "CPU利用率",  "warn"),
    "storage_size":   ("gauge",  "MB",      "存储总量",   None),
    "storage_used":   ("gauge",  "MB",      "存储已用",   None),
    "system_uptime":  ("gauge",  "s",       "系统运行时间", None),
    "if_status":      ("state",  None,      "端口状态",   "warn"),
    "if_in_octets":   ("counter", "bps",    "入流量",     None),
    "if_out_octets":  ("counter", "bps",    "出流量",     None),
    "if_in_errors":   ("counter", None,     "入错包",     "warn"),
    "if_out_errors":  ("counter", None,     "出错包",     "warn"),
    "if_in_discards": ("counter", None,     "入丢包",     "warn"),
    "if_out_discards":("counter", None,     "出丢包",     "warn"),
    "if_speed":       ("gauge",  "bps",     "端口速率",   None),
}

_CATEGORY_DEFAULT_THRESHOLDS = {
    "temperature":    {"warn": 70, "crit": 85},      # ℃，机箱/CPU 环境温度
    "disk_temperature": {"warn": 45, "crit": 60},    # ℃，磁盘温度（阈值更严）
    "cpu_usage":      {"warn": 85, "crit": 95},      # %
    "fan":            {"min": 500},                  # RPM，低于此值告警（风扇停转/过慢）
    "if_status":      {"expected": "up"},            # 端口期望 up
    "power_supply":   {"expected": "ok"},            # 电源期望 ok
    "if_in_errors":   {"warn": 0},                   # 错包 >0 即告警
    "if_out_errors":  {"warn": 0},
    "if_in_discards": {"warn": 0},
    "if_out_discards":{"warn": 0},
}


def batch_import_templates(items: list) -> dict:
    """批量导入 OID 为指标模板（I9：route handler 不再构造 Model + 调 repo）。

    自动填充逻辑（前端未显式传值时）：
    - category：从前端透传（MIB 扫描时已由 categorize_oids 打标）
    - metric_type / unit / display_name / severity_default：按 category 默认推断
    - vendor：从前端透传（设备厂商，用于模板匹配过滤）
    """
    from app.models.monitor_metric_template import MonitorMetricTemplate
    from app.persistence.monitor_metric_template_repository import MonitorMetricTemplateRepository
    from app.persistence.monitor_vendor_brand_repository import MonitorVendorBrandRepository
    from app.exceptions.validation import ValidationError
    if not isinstance(items, list):
        raise ValidationError("items 必须为数组")
    repo = MonitorMetricTemplateRepository()
    vendor_repo = MonitorVendorBrandRepository()
    imported = []
    for it in items:
        metric_key = it.get("metric_key")
        device_type = it.get("device_type")
        oid = it.get("oid")
        if not metric_key or not device_type or not oid:
            continue
        vendor_input = it.get("vendor")
        if vendor_input and not str(vendor_input).isdigit():
            brand = vendor_repo.find_by_brand_name(str(vendor_input))
            vendor_normalized = brand.enterprise_no if brand else vendor_input
        else:
            vendor_normalized = vendor_input
        category = it.get("category")
        defaults = _CATEGORY_DEFAULTS.get(category or "", (None, None, None, None))
        threshold_input = it.get("threshold")
        if not threshold_input or threshold_input == {}:
            threshold = _CATEGORY_DEFAULT_THRESHOLDS.get(category or "")
        else:
            threshold = threshold_input
        tpl = repo.upsert(
            device_type=device_type,
            metric_key=metric_key,
            vendor=vendor_normalized,
            category=category,
            display_name=it.get("display_name") or defaults[2],
            source="snmp",
            oid_symbol=it.get("oid_symbol"),
            oid=oid,
            metric_type=it.get("metric_type") or defaults[0] or "gauge",
            unit=it.get("unit") or defaults[1],
            severity_default=it.get("severity_default") or defaults[3],
            threshold=threshold,
            description=it.get("description"),
            enabled=True,
        )
        imported.append({"id": tpl.id, "metric_key": metric_key, "oid": oid})
    return {"imported": imported, "count": len(imported)}
