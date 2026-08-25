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

_RULES_CACHE_TTL = 300
_RULES_CACHE_PREFIX = "monitor:oid-rules:"
_RECOMMEND_CACHE_PREFIX = "monitor:recommend-config:"


def _get_redis():
    try:
        from app.services.scan_redis import get_scan_redis_client
        return get_scan_redis_client()
    except Exception:
        logger.warning("获取 Redis 客户端失败", exc_info=True)
        return None


def _extract_vendor_id(raw_oids: list[dict]) -> str | None:
    for row in raw_oids:
        if row.get("oid") == "1.3.6.1.2.1.1.2.0":
            from app.services.monitoring.snmp_mib_service import _extract_enterprise
            return _extract_enterprise(str(row.get("value", "")))
    return None


def extract_vendor_id(raw_oids: list[dict]) -> str | None:
    return _extract_vendor_id(raw_oids)


def _load_rules(vendor_id: str | None, device_type: str | None = None) -> list[dict]:
    cache_key = f"{_RULES_CACHE_PREFIX}{vendor_id or 'common'}:{device_type or 'any'}"
    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
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
        except Exception:
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)
    return rules


def _load_rule_prefixes() -> list[str]:
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    rule_repo = MonitorOidCategoryRuleRepository()
    from extensions import db
    from app.models.monitor_oid_category_rule import MonitorOidCategoryRule
    rows = db.session.query(MonitorOidCategoryRule.prefix).filter_by(enabled=1).all()
    return [r[0] for r in rows]


def _match_oid(oid: str, prefix: str) -> bool:
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
    {"prefix": "1.3.6.1.2.1.1.3.",   "category": "system_uptime",   "label": "系统运行时间"},
    {"prefix": "1.3.6.1.2.1.25.1.1.", "category": "system_uptime",   "label": "系统运行时间"},
    {"prefix": "1.3.6.1.2.1.2.2.1.8.",  "category": "if_status",      "label": "端口状态"},
    {"prefix": "1.3.6.1.2.1.2.2.1.10.", "category": "if_in_octets",   "label": "入向流量"},
    {"prefix": "1.3.6.1.2.1.2.2.1.16.", "category": "if_out_octets",  "label": "出向流量"},
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
    8: "temperature",
    9: "humidity",
    10: "fan",
    15: "power_supply",
}

_LOW_VALUE_CATEGORIES = frozenset({
    "threshold_descriptor",
})


def _match_standard_mib(oid: str) -> dict | None:
    for rule in _STANDARD_MIB_RULES:
        if oid.startswith(rule["prefix"]):
            return {"category": rule["category"], "label": rule["label"]}
    return None


def _match_heuristic(oid: str) -> dict | None:
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
    cache_key = f"{_RECOMMEND_CACHE_PREFIX}{device_type}"
    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)

    from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
    recommend_repo = MonitorDeviceTypeRecommendRepository()
    row = recommend_repo.find_by_device_type(device_type)
    categories = row.categories if row else []

    if r is not None:
        try:
            r.set(cache_key, json.dumps(categories), ex=_RULES_CACHE_TTL)
        except Exception:
            logger.warning("oid_category_service 缓存操作失败", exc_info=True)
    return categories


def invalidate_rules_cache(vendor_id: str | None = None) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        for key in r.scan_iter(f"{_RULES_CACHE_PREFIX}*"):
            r.delete(key)
    except Exception:
        logger.warning("invalidate_rule_cache 失败", exc_info=True)


def invalidate_recommend_cache() -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        for key in r.scan_iter(f"{_RECOMMEND_CACHE_PREFIX}*"):
            r.delete(key)
    except Exception:
        logger.warning("invalidate_recommend_cache 失败", exc_info=True)


def list_rules() -> list:
    from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
    repo = MonitorOidCategoryRuleRepository()
    return [r.to_dict() for r in repo.list_all()]


def create_rule(data: dict) -> dict:
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
    for rule in _HEURISTIC_RULES:
        seg = rule["segment"]
        if seg in oid:
            base = oid.split(seg, 1)[0] + seg
            rest = oid.split(seg, 1)[1]
            return base + (".1.11" if ".1.11" in rest else ".1.2")
    return None


def persist_heuristic_rule(oid: str, device_type: str, vendor_id: str | None = None) -> dict:
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
    from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
    repo = MonitorDeviceTypeRecommendRepository()
    return [r.to_dict() for r in repo.list_all()]


def update_recommend(device_type: str, categories: list) -> dict:
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
    "temperature":    {"warn": 70, "crit": 85},
    "disk_temperature": {"warn": 45, "crit": 60},
    "cpu_usage":      {"warn": 85, "crit": 95},
    "fan":            {"min": 500},
    "if_status":      {"expected": "up"},
    "power_supply":   {"expected": "ok"},
    "if_in_errors":   {"warn": 0},
    "if_out_errors":  {"warn": 0},
    "if_in_discards": {"warn": 0},
    "if_out_discards":{"warn": 0},
}


def batch_import_templates(items: list) -> dict:
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
