# -*- coding: utf-8 -*-
"""Zabbix 监控适配器（集中式拉取模型）。

与 SNMP/Redfish/IPMI 的 per-device 推送不同：Zabbix 通过 JSON-RPC API
批量拉取主机可用性 + 活跃问题，进程级缓存使单轮 N 设备仅 2 次 API 调用。
probe() 命中缓存时 O(1) 字典查找，未命中时重建索引。

设计契合 Route A 独立 async 进程：probe() 是同步方法，在
`StandaloneMonitorService.check_one` 的 `run_in_executor` worker 线程内执行，
无需任何 async 化；网络 I/O（连 Zabbix server）全在 session 外，落库才进独立 Session。
"""
import hashlib
import itertools
import logging
import threading
import time
from typing import Any

import requests

from app.exceptions.system import ExternalServiceError
from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    MonitorProtocolCode,
    ProbeResult,
    _record_orphan,
    monitor_timeout_seconds,
)
from app.core.enums import ProbeErrorCode

logger = logging.getLogger(__name__)

_zabbix_cache: dict[str, tuple[float, dict[str, dict]]] = {}
_cache_lock = threading.Lock()  # ThreadPoolExecutor 并发 probe 共享缓存
_rebuilding: set[str] = set()  # 正在重建索引的 cache_key 集合，防并发重复重建


def _cache_key(api_url: str, credential: dict) -> str:
    """缓存复合 key：api_url + token 短哈希，区分同一 api_url 下不同凭据。"""
    token = credential.get("api_token", "")
    token_fp = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"{api_url}::{token_fp}"


class _ZabbixEmptyHostError(Exception):
    """host.get 返回空主机列表（token 无权限 / server 无主机）。

    属配置错误而非设备宕机，由 probe() 转为 zabbix_empty_host_list，
    不进可达性状态机批量告警（见 v4-final §17 L3/E2）。
    """


class ZabbixAdapter(MonitorAdapter):
    """Zabbix 协议适配器（集中式拉取 + 批量缓存）。"""

    protocol = MonitorProtocolCode.ZABBIX

    def __init__(self):
        super().__init__()
        self._session = requests.Session()

    def probe(self, device, credential) -> ProbeResult:
        """探测单设备：从批量缓存查 Zabbix 主机可用性 + 活跃问题。

        credential (共享 Zabbix API 凭据) 形状:
            {api_url, api_token, verify_ssl, match_by}
        """
        host_ref = self._resolve_host_ref(device, credential)
        if not host_ref:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_HOST_REF.value)

        api_url = credential.get("api_url")
        if not api_url:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_API_URL.value)

        ckey = _cache_key(api_url, credential)

        with _cache_lock:
            _entry = _zabbix_cache.get(ckey)
            _now = time.monotonic()
            _ttl = self._cache_ttl()
            _cache_hit = _entry and (_now - _entry[0]) < _ttl
        if _cache_hit:
            start = time.monotonic()
            try:
                host_data, from_cache = self._get_host_data(ckey, api_url, credential, host_ref)
            except _ZabbixEmptyHostError:
                return ProbeResult(reachable=False, error=ProbeErrorCode.ZABBIX_EMPTY_HOST_LIST.value)
            except Exception as e:
                logger.warning("Zabbix 缓存命中查询失败 %s: %s", host_ref, e)
                return ProbeResult(reachable=False, error=ProbeErrorCode.ZABBIX_API_ERROR.value)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if host_data is None:
                return ProbeResult(reachable=False, error=ProbeErrorCode.HOST_NOT_IN_ZABBIX.value)
            return self._to_probe_result(host_data, elapsed_ms, from_cache=from_cache)

        holder: dict = {}
        err_holder: dict = {}

        def _run():
            try:
                host_data, from_cache = self._get_host_data(ckey, api_url, credential, host_ref)
                holder["v"] = host_data
                holder["from_cache"] = from_cache
            except _ZabbixEmptyHostError:
                holder["empty"] = True
            except Exception as e:  # 缓存重建异常 → 单设备失败不影响整轮
                err_holder["e"] = e

        start = time.monotonic()
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=monitor_timeout_seconds() * 3)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if t.is_alive():
            _record_orphan("zabbix")
            return ProbeResult(reachable=False, error=ProbeErrorCode.PROBE_TIMEOUT.value)
        if "e" in err_holder:
            logger.warning("Zabbix 查询失败 %s: %s", host_ref, err_holder["e"])
            return ProbeResult(reachable=False, error="zabbix_api_error")
        if holder.get("empty"):
            return ProbeResult(reachable=False, error="zabbix_empty_host_list")
        host_data = holder.get("v")
        if host_data is None:
            return ProbeResult(reachable=False, error="host_not_in_zabbix")

        from_cache = holder.get("from_cache", False)
        return self._to_probe_result(host_data, elapsed_ms, from_cache=from_cache)

    def _resolve_host_ref(self, device, credential: dict) -> str | None:
        """按 credential.match_by 决定用 hostname 还是 management_ip 匹配 Zabbix 主机。"""
        match_by = credential.get("match_by", "host")
        if match_by == "ip":
            return getattr(device, "management_ip", None)
        return getattr(device, "hostname", None) or getattr(device, "management_ip", None)

    def _get_host_data(self, ckey: str, api_url: str, credential: dict, host_ref: str) -> "tuple[dict | None, bool]":
        """返回 (host_data, from_cache)。

        from_cache=True 表示数据来自本地缓存（未触发 Zabbix API I/O），此时
        probe() 会把 latency_ms 置 0（缓存命中无网络延迟），并标记 from_cache=True，
        避免趋势图把缓存字典查找时间误判为设备网络延迟。未命中（重建索引）则
        from_cache=False。

        并发保护：当线程 A 正在重建时，线程 B 发现 _rebuilding 中有该 ckey，
        直接返回旧缓存数据（降级），避免多线程同时触发 _rebuild_index 浪费 API 调用。
        """
        ttl = self._cache_ttl()
        with _cache_lock:
            entry = _zabbix_cache.get(ckey)
            now = time.monotonic()
            if entry and (now - entry[0]) < ttl:
                return entry[1].get(host_ref), True
            if ckey in _rebuilding:
                return (entry[1] if entry else {}).get(host_ref), True
            _rebuilding.add(ckey)
            stale = entry[1] if entry else {}
        try:
            fresh = self._rebuild_index(api_url, credential)  # 耗时 I/O 在锁外
            with _cache_lock:
                _zabbix_cache[ckey] = (time.monotonic(), fresh)
            return fresh.get(host_ref, stale.get(host_ref)), False
        finally:
            with _cache_lock:
                _rebuilding.discard(ckey)

    def _rebuild_index(self, api_url: str, credential: dict) -> dict[str, dict]:
        """一次 host.get + 一次 problem.get 重建 {host_ref: host_data} 索引。

        L1 修正：索引建多路 key（host / name / interface ip），使 match_by="ip"
        也能命中——IP 不再只存 value，也作为 key，修复原先 match_by="ip" 永远 miss 的 bug。
        E2 修正：host.get 返回空列表（token 无权限/server 无主机）时抛 _ZabbixEmptyHostError，
        由 probe() 转为 zabbix_empty_host_list 配置错误，不进可达性状态机批量告警。
        E3 修正：problem.get 失败时降级为空 problems，不让非关键 API 失败拖垮可达性判定。
        """
        hosts = self._zabbix_call(api_url, credential, "host.get", {
            "output": ["hostid", "host", "name", "status"],
            "selectInterfaces": ["ip", "available", "type"],
        }) or []
        if not hosts:  # E2: 空主机列表 = 配置/权限错误，非设备宕机
            raise _ZabbixEmptyHostError(api_url)

        try:
            problems = self._zabbix_call(api_url, credential, "problem.get", {
                "output": ["eventid", "objectid", "name", "severity"],
                "sortfield": ["eventid"], "sortorder": "DESC", "limit": 50,
            }) or []
            trigger_ids = [p.get("objectid") for p in problems if p.get("objectid")]
            trig_to_hosts: dict[str, list[str]] = {}
            if trigger_ids:
                triggers = self._zabbix_call(api_url, credential, "trigger.get", {
                    "output": ["triggerid"],
                    "triggerids": trigger_ids,
                    "selectHosts": ["hostid"],
                }) or []
                for t in triggers:
                    tid = t.get("triggerid")
                    trig_to_hosts[tid] = [h["hostid"] for h in t.get("hosts", [])]
        except Exception as exc:
            logger.warning("problem.get 失败，降级为空问题列表: %s", exc)
            problems = []
            trig_to_hosts = {}

        prob_by_host: dict[str, list] = {}
        for p in problems:
            tid = p.get("objectid")
            for hostid in trig_to_hosts.get(tid, []):
                prob_by_host.setdefault(hostid, []).append({
                    "name": p.get("name"), "severity": int(p.get("severity", 0) or 0),
                })

        index: dict[str, dict] = {}
        for h in hosts:
            iface = (h.get("interfaces") or [{}])[0]
            data = {
                "hostid": h.get("hostid"),
                "host_status": int(h.get("status", 1) or 1),  # 0=monitored 1=not monitored
                "available": int(iface.get("available", 0) or 0),  # or 0 防 "" → int("") 崩
                "ip": iface.get("ip"),
                "active_problems": prob_by_host.get(h.get("hostid"), []),
            }
            for key in (h.get("host"), h.get("name"), iface.get("ip")):
                if key:
                    index[key] = data
        return index

    _rpc_id = itertools.count(0)

    def _next_rpc_id(self) -> int:
        return next(ZabbixAdapter._rpc_id)

    def _zabbix_call(self, api_url: str, credential: dict, method: str, params: dict) -> Any:
        """Zabbix JSON-RPC 2.0 单次调用（API Token Bearer 鉴权）。"""
        headers = {"Content-Type": "application/json-rpc"}
        token = credential.get("api_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_rpc_id(),
        }
        verify_ssl = credential.get("verify_ssl", True)
        resp = self._session.post(
            api_url, json=body, headers=headers,
            timeout=monitor_timeout_seconds(), verify=verify_ssl,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ExternalServiceError("zabbix", operation=method, message=f"zabbix {method} error: {data['error']}")
        return data.get("result")

    def _to_probe_result(self, host_data: dict, elapsed_ms: int, from_cache: bool = False) -> ProbeResult:
        """Zabbix 主机数据 → 统一 ProbeResult（见 v4-final §7 映射表）。

        from_cache=True（命中本地缓存、未触发 Zabbix API I/O）时，latency_ms 置 0
        并在 extra 标注 from_cache=True——缓存命中无真实网络延迟，避免趋势图误判为
        设备网络延迟（P11 修复）。
        """
        available = host_data.get("available", 0)
        monitored = host_data.get("host_status", 1) == 0
        reachable = monitored and (available == 1)
        effective_latency = 0 if from_cache else elapsed_ms
        extra = {
            "zabbix_hostid": host_data.get("hostid"),
            "zabbix_host_status": host_data.get("host_status"),
            "zabbix_available": available,
            "active_problems": host_data.get("active_problems", []),
            "problem_count": len(host_data.get("active_problems", [])),
            "source": "zabbix",
            "from_cache": from_cache,
        }
        error = None
        if not reachable:
            if available == 0:
                error = "zabbix_unknown_availability"
            elif available == 2:
                error = "zabbix_unavailable"
            elif not monitored:
                error = "zabbix_not_monitored"
        return ProbeResult(reachable=reachable, latency_ms=effective_latency, extra=extra, error=error)

    def _cache_ttl(self) -> int:
        """从 current_app.config 取缓存 TTL，无上下文回退 30s。"""
        try:
            from flask import current_app
            return int(current_app.config.get("MONITOR_ZABBIX_CACHE_TTL", 30))
        except (RuntimeError, TypeError, ValueError):
            return 30


    def _resolve_hostid_for_metrics(self, api_url: str, credential: dict, device) -> str | None:
        """按设备 IP/hostname 匹配 Zabbix host，返回 hostid（供 item.get 查询）。"""
        host_ref = self._resolve_host_ref(device, credential)
        if not host_ref:
            return None
        try:
            hosts = self._zabbix_call(api_url, credential, "host.get", {
                "output": ["hostid", "host"],
                "selectInterfaces": ["ip"],
            }) or []
        except Exception:
            logger.warning("zabbix metrics host.get 失败 api_url=%s", api_url, exc_info=True)
            return None
        matched = next(
            (h for h in hosts
             if any(i.get("ip") == host_ref for i in h.get("interfaces", []))),
            None,
        )
        host = matched or (hosts[0] if hosts else None)
        return host.get("hostid") if host else None

    def collect_metrics(self, device, credential, templates: list) -> dict:
        """按指标模板采集 Zabbix 指标（连通性之外的业务指标采集）。

        供 worker 指标采集循环调用（与 SNMP collect_metrics 对齐）。templates 为
        ``[{metric_key, zabbix_item_key, metric_type, ...}]``，仅处理含 zabbix_item_key 的模板。

        流程：
        1. 解析 hostid（host.get 按 IP/hostname 匹配）
        2. 对每个模板，item.get 按 hostids + search key_ 找 itemid（可能多个实例）
        3. history.get 拉每个 item 最新值（limit=1, sortfield=clock, sortorder=DESC）
        4. 返回 ``{metric_key: {item_name: value}}``，item_name 作为 index

        采集失败/无模板返回空 dict，不抛出（与 SNMP 一致，静默降级）。
        """
        api_url = credential.get("api_url")
        if not api_url or not templates:
            return {}
        zabbix_templates = [t for t in templates if t.get("zabbix_item_key")]
        if not zabbix_templates:
            return {}

        hostid = self._resolve_hostid_for_metrics(api_url, credential, device)
        if not hostid:
            return {}

        result: dict = {}
        for tpl in zabbix_templates:
            metric_key = tpl["metric_key"]
            item_key = tpl["zabbix_item_key"]
            try:
                items = self._zabbix_call(api_url, credential, "item.get", {
                    "hostids": hostid,
                    "output": ["itemid", "name", "key_", "value_type", "units"],
                    "search": {"key_": item_key},
                    "startSearch": True,
                }) or []
            except Exception:
                logger.warning(
                    "zabbix metrics item.get 失败 metric_key=%s item_key=%s hostid=%s",
                    metric_key, item_key, hostid, exc_info=True,
                )
                continue
            if not items:
                continue

            index_map: dict = {}
            for item in items:
                itemid = item.get("itemid")
                value_type = int(item.get("value_type", 0))
                index_name = item.get("name") or item.get("key_", "") or itemid
                try:
                    points = self._zabbix_call(api_url, credential, "history.get", {
                        "itemids": itemid,
                        "history": value_type,
                        "sortfield": "clock",
                        "sortorder": "DESC",
                        "limit": 1,
                        "output": "extend",
                    }) or []
                except Exception:
                    logger.warning(
                        "zabbix metrics history.get 失败 itemid=%s", itemid, exc_info=True,
                    )
                    continue
                if not points:
                    try:
                        trends = self._zabbix_call(api_url, credential, "trend.get", {
                            "itemids": itemid,
                            "sortfield": "clock",
                            "sortorder": "DESC",
                            "limit": 1,
                            "output": "extend",
                        }) or []
                    except Exception:
                        trends = []
                    if not trends:
                        continue
                    val = trends[0].get("value_avg") or trends[0].get("value_max")
                else:
                    val = points[0].get("value")
                try:
                    val_num = float(val) if val is not None else None
                except (TypeError, ValueError):
                    val_num = None
                if val_num is not None:
                    index_map[index_name] = val_num
            if index_map:
                result[metric_key] = index_map
        return result
