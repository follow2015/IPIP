# -*- coding: utf-8 -*-
"""本地 MIB 可用性与 OID 可解析性审计（P2-6）。

现状（2026-09-20 逐条实证，不是推测）
====================================
* **pysnmp 7 自带的 MIB 只有 29 个**，全是 SNMP 框架类（SNMPv2-MIB、RFC1213-MIB、
  SNMP-FRAMEWORK-MIB …）。``IF-MIB`` / ``ENTITY-SENSOR-MIB`` / ``HOST-RESOURCES-MIB``
  **都不在里面**，厂商 MIB 更不可能有。实测 ``MibBuilder().load_modules("IF-MIB")``
  直接抛 ``MibNotFoundError``。
* ``snmp_adapter._snmp_walk_table_async`` 的 docstring 写着"厂商私有 MIB 需放入
  pysnmp MIB 搜索路径（见 ``mibs/vendor/`` 说明），否则 OID 解析失败返回空"——
  但**代码从未把该目录加进搜索路径**，``mibs/vendor/`` 也**不存在**。
  ⇒ 那句指引是**纸面的**：运维把 MIB 文件拷进去也不会生效。
* 真库（生产配置）口径：``monitor_metric_templates`` 共 239 条，
  其中 ``source='snmp'`` 224 条**全部带数字 OID**（0 条依赖 MIB 符号解析）；
  ``source='ipmi'`` 2 条（``oid_symbol='SEL'``，走 IPMI 采集）、
  ``source='zabbix'`` 13 条。⇒ **当前没有一条模板真的采不到**。

所以本模块交付的不是"修好了几条坏模板"，而是：

1. **把纸面指引变成机制**（``ensure_vendor_mib_source``）：``mibs/vendor/`` 真正
   接进 pysnmp 搜索路径，且 ``(mib, symbol)`` 模板会先用本地 MIB 树解析成数字
   OID 再采集（``resolve_symbol_oid``）—— 否则即便 MIB 文件在，采集路径用的是
   ``lookupMib=False``，符号永远解析不出来，表现为"采集成功但指标缺几项"。
2. **让"解析不了"可见**（``audit_templates``）：离线判断每个模板的 OID 能不能
   解析，给出机器可读的 ``reason`` + 面向人的 ``reason_label``。
   离线是关键：排障现场常常连不上设备，而"本地没有这个 MIB"这件事与设备无关。

如何新增厂商 MIB（把这条写进用户能看到的 ``reason_label`` 里，
而不是只写在代码注释里）
===========================
把厂商 MIB 放进 ``app/services/monitoring/mibs/vendor/`` 即可 —— 目录由本模块
自动创建并接入 pysnmp 搜索路径。**但必须是可以被 pysnmp 直接加载的模块**：

⚠️ **实测（2026-09-20，pysnmp 7.1.27）**：pysnmp 的 ``DirMibSource`` **只认
``{名字}.py[co]``**。把厂商官网下载的纯文本 MIB（``XXX-MIB.txt`` / ``XXX-MIB``）
放进搜索路径后，``load_modules`` 依然抛::

    MibNotFoundError: MIB file "XXX-MIB.py[co]" not found in search path (...)

所以文本 MIB 需要先编译成 ``.py``（``pysmi`` 自带 ``mibdump`` 工具可做）。
本模块**不代为编译**，理由有三，全部实测：

1. 编译要跑一遍 pysmi 的 parser/codegen，放在采集路径上有成本与失败面；
2. ``pysmi.searcher`` 在本仓的 Python 3.14 下**不能第一个 import**
   （``pyfile.py`` 依赖已被移除的 ``imp``，且假定 ``importlib.util`` /
   ``importlib.machinery`` 已被别人导入过 —— 属顺序依赖的地雷：
   ``python -c "import pysmi.searcher"`` 必炸，而 ``pysmi.scripts.mibdump``
   因为先 import 了 ``pysmi.reader`` 反而能用）；
3. 编译一个厂商 MIB **不是单文件的事**：它 IMPORT 的一串依赖 MIB 也必须有源文件
   （实测 ``mibdump --mib-source=file://... --mib-stub=SNMPv2-SMI`` 仍报
   ``no module "SNMPv2-SMI" in symbolTable``；官方 mibdump 的默认解法是从
   mibs.pysnmp.com 联网借）。在一个不该联网的采集进程里做这件事，方向就是错的。

正因如此，本模块把"文件在但没编译"与"文件根本不在"分成两个 reason
（``mib_uncompiled`` / ``mib_missing``）—— 这两件事的下一步动作完全不同，
混成一句"缺 MIB"就会让运维在目录里明明看得见文件的状态下反复怀疑自己。
而两条路都走不通时，**最省事的正解是给模板填数字 OID**，
本仓已有 ``flask snmp-mib-scan`` 可以扫出设备实际支持的 OID。

**注意各厂商 MIB 的再分发许可**：本仓刻意不预置、也不自动下载厂商 MIB，
请从设备官网/厂商支持站点自行获取。
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from app.utils.logging import get_logger

logger = get_logger(__name__)

VENDOR_MIB_DIR: Path = Path(__file__).resolve().parent / "mibs" / "vendor"

_MIB_TEXT_SUFFIXES = (".mib.txt", ".asn1", ".mi2", ".smi", ".txt", ".mib", ".my")
_MIB_COMPILED_SUFFIXES = (".py", ".pyc")

REASON_NUMERIC_OID = "numeric_oid"
REASON_FALLBACK_TABLE = "fallback_table"
REASON_LOCAL_MIB = "local_mib"
REASON_OTHER_SOURCE = "other_source"
REASON_MIB_MISSING = "mib_missing"
REASON_MIB_UNCOMPILED = "mib_uncompiled"
REASON_SYMBOL_NOT_IN_MIB = "symbol_not_in_mib"
REASON_SYMBOL_WITHOUT_MIB = "symbol_without_mib"
REASON_NO_OID_SOURCE = "no_oid_source"
REASON_UNKNOWN = "unknown"

RESOLVED_REASONS = frozenset({
    REASON_NUMERIC_OID,
    REASON_FALLBACK_TABLE,
    REASON_LOCAL_MIB,
    REASON_OTHER_SOURCE,
})

REASON_LABELS: Dict[str, str] = {
    REASON_NUMERIC_OID: "模板直接填了数字 OID，不依赖任何 MIB，可正常采集",
    REASON_FALLBACK_TABLE: "命中内置 (MIB, 符号) → 数字 OID 兜底表，可正常采集",
    REASON_LOCAL_MIB: "本地 MIB 树已能解析该符号，可正常采集",
    REASON_OTHER_SOURCE: "非 SNMP 来源（IPMI/Zabbix 等），不受 SNMP OID 解析影响",
    REASON_MIB_MISSING: (
        "本地既没有该 MIB 的编译产物、也没有源文件，OID 解析不出来 ⇒ 这条指标永远采不到。"
        "两条落地路径 —— ①最省事：直接给该模板填**数字 OID**（零依赖），"
        "可用 `flask snmp-mib-scan <设备IP>` 扫出设备实际支持的 OID 再回填；"
        f"②把厂商 MIB 放进 {VENDOR_MIB_DIR}（注意厂商再分发许可，请从设备官网自行获取）"
        "并编译成 pysnmp 能加载的 .py"
    ),
    REASON_MIB_UNCOMPILED: (
        f"MIB 源文件已在 {VENDOR_MIB_DIR} 里，但缺少编译产物 `<MIB名>.py` ⇒ pysnmp 加载不到它。"
        "实测：pysnmp 的 MIB 搜索路径只认预编译模块，纯文本 MIB 不会被自动编译；"
        "且离线编译一个厂商 MIB 还需备齐它依赖的一串 MIB 源文件（联网借或一并通过 pysnmp 的 "
        "mibdump 处理）。最省事的做法是直接给该模板填**数字 OID**，"
        "可用 `flask snmp-mib-scan <设备IP>` 扫出来"
    ),
    REASON_SYMBOL_NOT_IN_MIB: (
        "MIB 文件在，但里面没有这个符号 ⇒ 检查符号名拼写或 MIB 版本是否匹配"
    ),
    REASON_SYMBOL_WITHOUT_MIB: (
        "只填了 OID 符号、没填 MIB 名，无从解析 ⇒ 补 MIB 名，或直接填数字 OID"
    ),
    REASON_NO_OID_SOURCE: "SNMP 源却既没有数字 OID 也没有符号 ⇒ 这条模板没有采集依据",
    REASON_UNKNOWN: "缺少 OID / 符号信息，无法判断",
}

_builder = None
_builder_lock = threading.RLock()
_loaded: Dict[str, Tuple[bool, float]] = {}
_resolved: Dict[Tuple[str, str], Tuple[Tuple[Optional[str], str], float]] = {}
_vendor_registered = False

_MIB_CACHE_TTL_SECONDS = 300.0
_MIB_CACHE_MAXSIZE = 512

_now = time.monotonic

_CACHE_MISS = object()


def _cache_get(cache: dict, key: Any) -> Any:
    """TTL 感知读：过期即视为未命中，并**顺手删掉**（否则过期项仍会无界占位）。"""
    entry = cache.get(key)
    if entry is None:
        return _CACHE_MISS
    value, expires_at = entry
    if expires_at <= _now():
        cache.pop(key, None)
        return _CACHE_MISS
    return value


def _cache_put(cache: dict, key: Any, value: Any) -> None:
    """写入并维持容量上限：先清过期项，仍超限则丢"最早过期"的那条。"""
    now = _now()
    cache[key] = (value, now + _MIB_CACHE_TTL_SECONDS)
    if len(cache) <= _MIB_CACHE_MAXSIZE:
        return
    for stale in [k for k, (_v, exp) in cache.items() if exp <= now]:
        cache.pop(stale, None)
    while len(cache) > _MIB_CACHE_MAXSIZE:
        oldest = min(cache.items(), key=lambda kv: kv[1][1])[0]
        cache.pop(oldest, None)


def ensure_vendor_mib_source() -> Optional[str]:
    """把 ``mibs/vendor/`` 接进 pysnmp 的 MIB 搜索路径（幂等）。

    返回已接入的目录路径字符串；目录不可用时返回 None（并**不**抛异常 ——
    SNMP 采集不该因为一个目录建不出来就整体失败）。

    为什么必须显式做：pysnmp 的默认搜索路径只有它自带的目录与工作目录下的
    ``pysnmp_mibs``。**把文件拷进任意目录并不会让它被找到**，必须有代码
    ``add_mib_sources(DirMibSource(dir))``。原实现只有 docstring 里的口头承诺。
    """
    global _vendor_registered
    if _vendor_registered:
        return str(VENDOR_MIB_DIR)
    try:
        VENDOR_MIB_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:  # noqa: BLE001 - 只读文件系统/权限不足时降级
        logger.warning("厂商 MIB 目录不可用，跳过搜索路径注册: %s", VENDOR_MIB_DIR)
        return None
    try:
        from pysnmp.smi import builder as _builder_mod

        _get_builder().add_mib_sources(_builder_mod.DirMibSource(str(VENDOR_MIB_DIR)))
    except Exception:  # noqa: BLE001 - pysnmp 缺失/API 变化都不该阻断采集
        logger.warning("注册厂商 MIB 搜索路径失败: %s", VENDOR_MIB_DIR, exc_info=True)
        return None
    _vendor_registered = True
    logger.info("已注册厂商 MIB 搜索路径: %s", VENDOR_MIB_DIR)
    return str(VENDOR_MIB_DIR)


def _vendor_text_mib_modules() -> set:
    """vendor 目录里**只放了源文件、没有编译产物**的 MIB 模块名集合。

    为什么值得单独识别（实测，2026-09-20 / pysnmp 7.1.27）：``DirMibSource``
    只认 ``{名字}.py[co]``。把 ``XXX-MIB.txt`` 放进搜索路径后
    ``load_modules("XXX-MIB")`` 仍抛
    ``MibNotFoundError: MIB file "XXX-MIB.py[co]" not found in search path``。

    于是"我把 MIB 拷进去了"和"我根本没拷"在排障现场长得**一模一样**，
    而这两件事的下一步动作完全不同：前者要编译，后者要去找文件。
    混成一句"缺 MIB"就会让运维在目录里明明看得见文件的状态下反复怀疑自己。

    目录不存在/不可读时返回空集合（此时归因只能是"文件不在"，不猜）。

    同名既有源文件又有编译产物时**不算**未编译 —— 那是已经处理好的状态，
    报出来会让运维去重复编译一个本来就好的 MIB。
    """
    modules = set()
    compiled = set()
    try:
        entries = list(VENDOR_MIB_DIR.iterdir())
    except OSError:
        return modules
    for path in entries:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        name = path.name
        if name.endswith(_MIB_COMPILED_SUFFIXES):
            compiled.add(name[: name.rfind(".")])
            continue
        for suffix in _MIB_TEXT_SUFFIXES:
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
        if name:
            modules.add(name)
    return modules - compiled


def _get_builder():
    """懒加载并缓存 MibBuilder（已带厂商搜索路径）。"""
    global _builder
    if _builder is None:
        with _builder_lock:
            if _builder is None:
                from pysnmp.smi import builder as _builder_mod

                _builder = _builder_mod.MibBuilder()
    return _builder


def mib_loadable(mib: str) -> bool:
    """该 MIB 能否在本地加载（结果缓存 —— 加载要读盘并解析，代价不低）。

    ⚠️ ``ensure_vendor_mib_source()`` **必须在拿 ``_builder_lock`` 之前调用**。
    它不是"顺手放外面"：该助手内部会调 ``_get_builder()``，而 ``_get_builder``
    同样要拿这把锁 —— 放在临界区里就是**自死锁**（实测：pytest 120s 超时，
    堆栈停在 ``_get_builder`` 的 ``with _builder_lock``）。

    生产路径一度**侥幸躲过**这枚雷：``snmp_adapter._get_pysnmp_async()`` 会在
    建引擎时先调一次 ``ensure_vendor_mib_source()``，之后 ``_vendor_registered``
    为真、这里是空转。但 **P2-6 的审计端点是全新入口**，它不走适配器那条路径 ⇒
    进程内第一次审计就会永久挂住。这条注释就是防它被"优化"回去。
    """
    cached = _cache_get(_loaded, mib)
    if cached is not _CACHE_MISS:
        return cached
    with _builder_lock:
        ensure_vendor_mib_source()
        cached = _cache_get(_loaded, mib)  # 双检：锁外那次检查可能被别的线程抢先
        if cached is not _CACHE_MISS:
            return cached
        try:
            _get_builder().load_modules(mib)
            ok = True
        except Exception:  # noqa: BLE001 - MibNotFoundError / SmiError 均视为不可用
            ok = False
        _cache_put(_loaded, mib, ok)
    return ok


def resolve_symbol_oid(mib: Optional[str], symbol: Optional[str]) -> Tuple[Optional[str], str]:
    """把 ``(mib, symbol)`` 解析成数字 OID 字符串。返回 ``(oid|None, reason)``。

    纯本地：不连设备、不发包。这是"厂商 MIB 缺失"唯一可离线判定的地方 ——
    真连设备时，"设备没有这个 OID"与"我们根本没解析出要问的 OID"在返回的
    空结果上**长得一模一样**，那正是 P2-6 要消灭的黑洞。
    """
    if not symbol:
        return None, REASON_NO_OID_SOURCE
    if not mib:
        return None, REASON_SYMBOL_WITHOUT_MIB
    key = (mib, symbol)
    cached = _cache_get(_resolved, key)
    if cached is not _CACHE_MISS:
        return cached

    if not mib_loadable(mib):
        reason = (
            REASON_MIB_UNCOMPILED
            if mib in _vendor_text_mib_modules()
            else REASON_MIB_MISSING
        )
        result: Tuple[Optional[str], str] = (None, reason)
    else:
        try:
            from pysnmp.smi import view as _view_mod

            oid, _label, _suffix = _view_mod.MibViewController(
                _get_builder()
            ).get_node_name_by_desc(symbol, mib)
            result = (".".join(str(x) for x in oid), REASON_LOCAL_MIB)
        except Exception:  # noqa: BLE001 - 符号不在该 MIB 里
            result = (None, REASON_SYMBOL_NOT_IN_MIB)
    _cache_put(_resolved, key, result)
    return result


def _field(tpl: Any, name: str) -> Any:
    """同时接受 ORM 对象与扁平 dict（适配器拿到的是展平后的 dict）。"""
    if isinstance(tpl, dict):
        return tpl.get(name)
    return getattr(tpl, name, None)


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def audit_template(tpl: Any, fallback_table: Optional[dict] = None) -> Dict[str, Any]:
    """判定单个模板的 OID 能否解析，返回含 ``reason`` / ``reason_label`` 的 dict。

    ``fallback_table`` 默认取适配器的 ``_MIB_SYMBOL_OID_FALLBACK``；显式传入
    便于测试与"口径同源"（两边同一份表，不是各抄一份）。
    """
    if fallback_table is None:
        from app.services.monitoring.adapters.snmp_adapter import (
            _MIB_SYMBOL_OID_FALLBACK,
        )

        fallback_table = _MIB_SYMBOL_OID_FALLBACK

    metric_key = _clean(_field(tpl, "metric_key"))
    device_type = _clean(_field(tpl, "device_type"))
    source = _clean(_field(tpl, "source")) or "snmp"
    mib = _clean(_field(tpl, "mib"))
    symbol = _clean(_field(tpl, "oid_symbol"))
    oid = _clean(_field(tpl, "oid"))

    base = {
        "metric_key": metric_key,
        "device_type": device_type,
        "source": source,
        "mib": mib,
        "oid_symbol": symbol,
        "oid": oid,
    }
    if source != "snmp":
        return {
            **base,
            "resolvable": True,
            "reason": REASON_OTHER_SOURCE,
            "reason_label": REASON_LABELS[REASON_OTHER_SOURCE],
            "resolved_oid": oid,
        }
    if oid:
        return {
            **base,
            "resolvable": True,
            "reason": REASON_NUMERIC_OID,
            "reason_label": REASON_LABELS[REASON_NUMERIC_OID],
            "resolved_oid": oid,
        }
    if mib and symbol and (mib, symbol) in fallback_table:
        return {
            **base,
            "resolvable": True,
            "reason": REASON_FALLBACK_TABLE,
            "reason_label": REASON_LABELS[REASON_FALLBACK_TABLE],
            "resolved_oid": fallback_table[(mib, symbol)],
        }
    resolved, reason = resolve_symbol_oid(mib, symbol)
    return {
        **base,
        "resolvable": reason in RESOLVED_REASONS,
        "reason": reason,
        "reason_label": REASON_LABELS.get(reason, REASON_LABELS[REASON_UNKNOWN]),
        "resolved_oid": resolved,
    }


def audit_templates(templates: Iterable[Any]) -> Dict[str, Any]:
    """批量审计，返回**逐条明细** + 汇总 + 不可解析清单（P2-6 要暴露的就是后者）。

    为什么 ``items``（逐条）与 ``unresolved_items``（过滤后）都返回，而不只返回
    不可解析的那批：前者让列表页**逐行**标出"这一条能不能采到"，后者让汇总卡片
    直接拿到"要处理的那几张单子"。只给后者的话，前端得把 ``items`` 自己过滤一遍
    —— 那份过滤逻辑一旦与后端判定漂移，就会出现"卡片说 3 条坏、表里标了 5 条红"。

    ``missing_mibs`` 按 MIB 名归并："缺 3 个 MIB 影响 40 条指标"比
    "40 条指标解析失败"更可行动 —— 运维只需要去拿 3 个文件。
    """
    items = [audit_template(t) for t in templates]
    unresolved = [it for it in items if not it["resolvable"]]
    missing_mibs: Dict[str, list] = {}
    for it in unresolved:
        if it["mib"]:
            missing_mibs.setdefault(it["mib"], []).append(it["metric_key"])
    counts = Counter(it["reason"] for it in items)
    return {
        "total": len(items),
        "resolvable": len(items) - len(unresolved),
        "unresolved": len(unresolved),
        "items": items,
        "unresolved_items": unresolved,
        "missing_mibs": {k: sorted(v) for k, v in sorted(missing_mibs.items())},
        "reason_counts": dict(sorted(counts.items())),
        "reason_labels": {
            r: REASON_LABELS.get(r, REASON_LABELS[REASON_UNKNOWN]) for r in sorted(counts)
        },
        "vendor_mib_dir": str(VENDOR_MIB_DIR),
        "vendor_uncompiled_mibs": sorted(_vendor_text_mib_modules()),
    }
