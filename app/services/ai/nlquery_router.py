# -*- coding: utf-8 -*-
"""NL 入口：LLM 从技能目录选一个技能 + 填参数，交给 WorkflowEngine 或 AgenticSkillRunner 执行。

本身不含业务逻辑，只做"选择 + 分发"，因此不做成技能（避免技能选技能的自指结构）。

Phase 2.5：扩展支持 agentic skill 路由。LLM 同时看到 Tier1 catalog 和 agentic catalog，
选中 agentic skill（category=agentic）时路由到 AgenticSkillRunner，否则路由到 WorkflowEngine。
"""
import json
import logging
import re
from typing import Callable, List, Optional

from app.services.ai.skills.engine import WorkflowEngine
from app.services.ai.skills.permission import check_skill_permission, SkillPermissionDenied
from app.services.ai.skills.loader import default_skill_dirs, default_agentic_dirs
from app.services.ai.skills.visibility import get_allowed_skill_names
from app.services.ai.capabilities.registry import get_capability
from app.services.ai.llm_factory import create_llm_client
from app.services.ai.ai_errors import AINotConfiguredError

logger = logging.getLogger(__name__)


def _skill_dirs() -> List[str]:
    """a5：技能目录**调用时**读取，而非模块 import 时固化成常量。

    固化会让 Config 热改（AI_BUILTIN_SKILLS_DIR / AI_CUSTOM_SKILLS_DIR）
    在进程重启前完全不生效——新增/迁移技能目录必须重启才能被发现。
    对齐 skill_admin_service._skill_dirs 的调用时读取做法。
    """
    return default_skill_dirs()


def _agentic_dirs() -> List[str]:
    """a5：同上，agentic 技能目录调用时读取。"""
    return default_agentic_dirs()

_SYSTEM = (
    "你是网络运维数据助手。根据用户问题和下面的技能目录，选择一个最匹配的技能并填好参数，"
    '只返回 JSON：{"skill": "<技能名>", "category": "<general|agentic>", "args": {...}}。'
    "选择要求：仅当某技能的 description / triggers 与问题**语义高度匹配**时才选它；"
    "只是沾边、或需要拼凑多个技能才能回答时，一律返回 {\"skill\": null}——"
    "硬选不相关的技能只会返回答非所问的空结果。"
    "严禁编造技能目录中不存在的技能名。"
    '深度诊断/根因分析/故障排查类问题优先选 category=agentic 的技能。'
    "参数要求：args 必须严格使用技能目录里该技能 params 声明的参数名（name），"
    "必填项（required=true）必须填满，取值格式遵循 description；"
    "不要自己推测参数名（例如把 cidr 写成 subnet / network）——那会被判为缺少该参数。"
    "若问题确实未提供必填值且无法可靠推断（例如只给了 IP 未给子网掩码），"
    '不要硬猜——返回 {"skill": null, "need_info": "用一句话说明需要用户补充什么"}。'
    "选了技能却填错或留空参数，只会让用户收到一句看不懂的报错。"
)


class NLQueryRouter:
    """薄调度层：LLM 选技能 + 填参数 → 权限校验 → WorkflowEngine/AgenticSkillRunner 执行。"""

    def __init__(self, client=None, engine: Optional[WorkflowEngine] = None,
                 load_catalog_fn: Optional[Callable] = None,
                 load_skill_fn: Optional[Callable] = None):
        self.client = client or create_llm_client()
        self.engine = engine or WorkflowEngine(get_capability=get_capability)
        self._load_catalog = load_catalog_fn or _default_load_catalog
        self._load_skill = load_skill_fn or _default_load_skill
        self.last_session_id: Optional[int] = None

    def ask(self, question: str, user_id: int, user_permissions: set) -> str:
        self.last_session_id = None
        if not self.client.is_configured():
            raise AINotConfiguredError(operation="nl_query")

        tier1_catalog = self._load_catalog(_skill_dirs())
        agentic_catalog = self._load_agentic_catalog(_agentic_dirs())
        merged = list(tier1_catalog) + list(agentic_catalog)

        allowed = get_allowed_skill_names(
            merged, user_permissions, _visibility_filter())
        if allowed is not None:
            before = len(merged)
            merged = [c for c in merged if c.get("name") in allowed]
            logger.info("skill.visibility.filtered total=%d visible=%d",
                        before, len(merged))

        from app.services.ai.prompt_guard import sanitize_user_input
        safe_question = sanitize_user_input(question)

        mode = _routing_mode()
        menu_catalog = _build_menu_catalog(
            merged, safe_question, mode, _recall_topk())
        from app.services.ai.metrics import record_skill_menu
        record_skill_menu(mode, len(menu_catalog), len(merged))
        menu = json.dumps([_menu_entry(c) for c in menu_catalog], ensure_ascii=False)
        raw = self.client.chat(_SYSTEM, f"技能目录：{menu}\n用户问题：{safe_question}")
        try:
            decision = json.loads(_strip_fence(raw))
        except (json.JSONDecodeError, ValueError):
            return "抱歉，我无法理解该问题。"

        skill_name = decision.get("skill")
        if not skill_name:
            hint = decision.get("need_info")
            if isinstance(hint, str) and hint.strip():
                return hint.strip()[:300]
            return "暂无对应能力，请换种问法。"

        category = decision.get("category", "general")

        if category == "agentic":
            return self._run_agentic(skill_name, question, user_id, user_permissions)

        try:
            skill = self._load_skill(skill_name, _skill_dirs())
        except KeyError:
            return f"未找到技能：{skill_name}"

        try:
            check_skill_permission(skill, user_permissions)
        except SkillPermissionDenied as e:
            return f"抱歉，该操作需要额外权限（{'/'.join(e.missing)}）。"

        from app.services.ai.skills.schema import validate_skill_args, SkillArgsError
        args = decision.get("args", {})
        try:
            validate_skill_args(skill, args)
        except SkillArgsError as e:
            return _friendly_args_error(skill, e)

        import time as _time

        from app.services.ai._runtime import bind_scenario
        from app.services.ai.metrics import record_skill_run

        _t0 = _time.monotonic()
        _status = "ok"
        try:
            with bind_scenario(f"skill.{skill_name}"):
                result = self.engine.run(
                    skill, args,
                    user_id=user_id, user_permissions=user_permissions,
                )
        except ValueError as e:
            _status = "error"
            return f"查询条件有误：{e}"
        except Exception:
            _status = "error"
            raise
        finally:
            record_skill_run(skill_name=skill_name, status=_status,
                             duration_seconds=_time.monotonic() - _t0)
        if result is None:
            return "该查询暂无数据，请换种问法或调整筛选条件。"
        report = result.get("report") if isinstance(result, dict) else None
        if isinstance(report, str) and report.strip():
            return report.strip()
        return result if isinstance(result, str) else _format_result_cn(result)

    def _run_agentic(self, skill_name: str, question: str,
                     user_id: int, user_permissions: set) -> str:
        """路由到 AgenticSkillRunner 执行 agentic 技能。"""
        import time as _time

        from app.services.ai._runtime import bind_scenario
        from app.services.ai.agentic.loader import load_agentic_skill
        from app.services.ai.agentic.runner import AgenticSkillRunner
        from app.services.ai.metrics import record_skill_run

        try:
            spec, instructions = load_agentic_skill(skill_name, _agentic_dirs())
        except KeyError:
            return f"未找到 agentic 技能：{skill_name}"

        runner = AgenticSkillRunner()
        _t0 = _time.monotonic()
        _status = "ok"
        try:
            with bind_scenario(f"agentic.{skill_name}"):
                answer = runner.run(spec, instructions, question,
                                    user_id=user_id, user_permissions=user_permissions)
        except Exception:
            _status = "error"
            raise
        finally:
            record_skill_run(skill_name=f"agentic.{skill_name}", status=_status,
                             duration_seconds=_time.monotonic() - _t0)
        self.last_session_id = runner.last_session_id
        return answer

    def _load_agentic_catalog(self, dirs: List[str]) -> List[dict]:
        """加载 agentic 技能目录（惰性 import 避免循环依赖）。"""
        from app.services.ai.agentic.loader import load_agentic_catalog
        return load_agentic_catalog(dirs)


def _default_load_catalog(dirs: List[str]) -> List[dict]:
    """加载技能目录。

    缓存说明（B6 核实结论：**无需额外缓存**，此处保持直调）：
    - `load_catalog`（skills/loader.py:49）内部已实现**基于文件 mtime 的缓存**：
      仅当任一 YAML 的 mtime 变化时才重新读盘解析，未变则返回内存中的 catalog；
    - `reload_catalog()`（skill_admin_service.py:144）已调用
      `loader.invalidate_catalog_cache()` 主动失效，热重载链路完整；
    - `create_llm_client()`（llm_factory.py:65）亦有按配置维度的进程级单例缓存。

    故在此处再包一层缓存属冗余，且会引入**双缓存不一致**风险：外层缓存无法被
    loader 的失效函数感知，技能热重载后 /ask 仍会拿到旧目录。保持直调即可。
    """
    from app.services.ai.skills.loader import load_catalog
    return load_catalog(dirs)


def _default_load_skill(name: str, dirs: List[str]):
    from app.services.ai.skills.loader import load_skill
    return load_skill(name, dirs)


def _strip_fence(text: str) -> str:
    """剥离 LLM 可能包裹的 ```json ... ``` 围栏。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def _prefilter_by_triggers(catalog: List[dict], question: str) -> List[dict]:
    """triggers 关键词零成本粗筛：返回 triggers 子串命中问题的技能。

    L0 路由优化（技能膨胀治理）：用现成的 triggers 字段做关键词匹配，把注入 prompt
    的技能集从"全量"缩到"相关候选"，避免技能数线性放大 prompt 导致 LLM 注意力稀释。
    不做语义匹配（零 LLM 调用、零额外依赖），仅子串命中，阈值与回退交给 _select_menu_catalog。
    """
    q = (question or "").lower()
    if not q:
        return []
    return [c for c in catalog if any(t.lower() in q for t in c.get("triggers", []))]


def _select_menu_catalog(catalog: List[dict], question: str,
                         enabled: bool, top_k: int) -> List[dict]:
    """按 triggers 粗筛结果决定注入 prompt 的技能集（与总数解耦的开关）。

    - enabled=False：直接全量（等价于现网行为，便于一键回退）。
    - 命中为空：回退全量（问题未命中任何 triggers，不裁剪，避免漏选）。
    - 命中数 > top_k：回退全量（命中过多说明 triggers 过宽或问题含多关键词，裁剪会
      误伤，交给 LLM 在全量中精选更安全）。
    - 其余：仅用命中集，prompt 体积最小。
    """
    if not enabled:
        return catalog
    pref = _prefilter_by_triggers(catalog, question)
    if pref and len(pref) <= top_k:
        return pref
    return catalog


def _prefilter_enabled() -> bool:
    """路由粗筛开关（调用时读取 Config，与 _skill_dirs 同口径）。"""
    from config import Config
    return getattr(Config, "AI_SKILL_TRIGGER_PREFILTER", True)


def _recall_topk() -> int:
    """粗筛命中数上限：超过则回退全量（见 _select_menu_catalog）。"""
    from config import Config
    return getattr(Config, "AI_SKILL_RECALL_TOPK", 8)


def _visibility_filter() -> bool:
    """L2 入口可见性裁剪开关（调用时读取 Config，与 _skill_dirs 同口径）。"""
    from config import Config
    return getattr(Config, "AI_SKILL_VISIBILITY_FILTER", False)


def _friendly_args_error(skill, err) -> str:
    """把参数校验错误转成运维可读的补充指引。

    /ask 是自然语言入口：直接把「缺少必填参数：cidr」抛给运维，他既不知道 cidr 是
    什么、也不知道该怎么补（线上反馈：用户问"10.100.10.0 这个网段使用率"，收到这句
    技术文案后无法自助）。这里把技能 params 的 description（含格式示例）拼进提示，
    让报错变得可行动。
    """
    hints = {p.name: (p.description or "")
             for p in (getattr(skill, "params", None) or [])}
    parts = []
    for msg in getattr(err, "errors", None) or [str(err)]:
        m = re.search(r"缺少必填参数：(\S+)", msg)
        if m:
            name = m.group(1)
            desc = hints.get(name)
            parts.append(f"缺少 {name}" + (f"（{desc}）" if desc else ""))
        else:
            parts.append(msg)
    return "需要补充信息才能查询：" + "；".join(parts) + "。请补充后重试。"


def _menu_entry(c: dict) -> dict:
    """构造注入 prompt 的单个技能条目（含 params 定义）。

    params 必须带上：LLM 要替用户填 args，目录里若没有参数定义（参数名 / 是否必填 /
    格式说明），它只能靠猜——线上反馈「10.100.10.0/24 这个网段使用率是多少」明明给了
    完整 CIDR，却报「缺少 cidr」，即 LLM 猜了别的参数名（subnet / network 之类）。
    catalog 本就带 params 字段（loader.load_catalog），此前只是没透传给 LLM。

    字段精简为 name/type/required/description：既够 LLM 判断，又不把 default、enum
    等用不上的字段塞进 prompt（目录已按 L0/L1 裁剪，体积增量可控）。
    """
    entry = {k: c.get(k)
             for k in ("name", "title", "description", "category", "triggers")}
    entry["params"] = [
        {k: p.get(k) for k in ("name", "type", "required", "description")}
        for p in (c.get("params") or []) if isinstance(p, dict)
    ]
    return entry


_LABEL_CN = {
    "cidr": "网段", "subnet": "网段", "network": "网段",
    "total": "总数", "count": "数量", "num": "数量",
    "active": "活跃", "inactive": "离线", "offline": "离线",
    "blocked": "封禁", "banned": "封禁", "unused": "空闲", "free": "空闲",
    "used": "已用", "usage": "已用", "utilization": "利用率",
    "rate": "比率", "ratio": "占比", "percent": "占比",
    "ip": "IP", "ip_address": "IP 地址", "mac": "MAC", "mac_address": "MAC 地址",
    "device_id": "设备 ID", "device_name": "设备名", "hostname": "主机名",
    "name": "名称", "title": "标题", "status": "状态", "state": "状态",
    "room": "机房", "room_id": "机房 ID", "room_name": "机房",
    "cabinet": "机柜", "cabinet_id": "机柜 ID", "cabinet_name": "机柜",
    "port": "端口", "ports": "端口", "vlan": "VLAN", "vlans": "VLAN",
    "customer": "客户", "customers": "客户", "customer_name": "客户名",
    "cpu": "CPU", "memory": "内存", "mem": "内存", "disk": "磁盘",
    "time": "时间", "timestamp": "时间", "date": "日期",
    "reason": "原因", "message": "信息", "detail": "详情", "details": "详情",
    "result": "结果", "summary": "结论", "conclusion": "结论",
    "alert_type": "告警类型", "severity": "级别", "metric": "指标",
    "value": "值", "unit": "单位", "reachable": "是否可达", "online": "是否在线",
    "available": "可用", "idle": "空闲", "uplink": "上行", "path": "路径",
}


def _indent(text: str) -> str:
    """嵌套内容整体缩进两格，体现层级。"""
    return "\n".join("  " + line for line in text.split("\n"))


def _format_result_cn(value) -> str:
    """把技能的结构化结果渲染成可读中文（递归处理嵌套 dict / list）。

    /ask 面向运维，技能 return 多为底层 capability 的原始 dict（34 个技能里 31 个
    如此），直接 json.dumps 会得到一整行 JSON。此处按字段名映射成中文标签逐行呈现；
    布尔值翻成是/否，列表编号列出。
    """
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            label = _LABEL_CN.get(str(k).lower(), str(k))
            if isinstance(v, (dict, list)) and v:
                parts.append(f"{label}：\n{_indent(_format_result_cn(v))}")
            else:
                parts.append(f"{label}：{_format_result_cn(v)}")
        return "\n".join(parts)
    if isinstance(value, list):
        return "\n".join(
            f"{i}. {_format_result_cn(v)}".replace("\n", "\n   ")
            for i, v in enumerate(value, 1))
    if value is True:
        return "是"
    if value is False:
        return "否"
    return str(value)



_SKILL_DOMAIN = "skill_catalog"
_SKILL_INDEX_SIGNATURE = None  # 模块级缓存：catalog 内容指纹，变化时重建索引


def _routing_mode() -> str:
    """路由模式（调用时读取 Config，与 _skill_dirs 同口径）。非法值安全回退 domain。"""
    from config import Config
    mode = getattr(Config, "AI_SKILL_ROUTING_MODE", "domain")
    return mode if mode in ("full", "domain", "recall", "domain+recall") else "domain"


def _catalog_signature(merged: List[dict]) -> str:
    """catalog 内容指纹：name/title/description/triggers 任一变化即重建索引。"""
    import hashlib
    h = hashlib.sha1()
    for c in sorted(merged, key=lambda x: x.get("name", "")):
        h.update((c.get("name", "") + "\0").encode())
        h.update((c.get("title", "") + "\0").encode())
        h.update((c.get("description", "") + "\0").encode())
        h.update((" ".join(c.get("triggers", [])) + "\0").encode())
    return h.hexdigest()


def _ensure_skill_index(store, merged: List[dict]) -> None:
    """按需把 catalog 索引进 rag（domain=skill_catalog），仅内容变化时重建。"""
    global _SKILL_INDEX_SIGNATURE
    if not getattr(store, "available", False):
        return
    sig = _catalog_signature(merged)
    if _SKILL_INDEX_SIGNATURE == sig:
        return
    texts = [
        f"[{c.get('name', '')}] {c.get('title', '')}\n{c.get('description', '')}\n"
        f"触发词: {' '.join(c.get('triggers', []))}\n[{c.get('name', '')}]"
        for c in merged
    ]
    try:
        store.ingest(texts, domain=_SKILL_DOMAIN, source="skill")
        _SKILL_INDEX_SIGNATURE = sig
    except Exception as e:  # noqa: BLE001
        logger.warning("skill_index_build_failed: %s", e)


def _recall_skills(merged: List[dict], question: str, top_k: int) -> List[dict]:
    """L1 语义召回：hybrid_search 召回 top-k 相关技能，解析 `[name]` 前缀映射回 catalog。

    返回命中 catalog 的子集；rag 不可用/异常时返回 []，由 _build_menu_catalog 回退。
    """
    try:
        from app.services.ai.rag_store import get_rag_store
        store = get_rag_store()
        _ensure_skill_index(store, merged)
        chunks = store.hybrid_search(question, domain=_SKILL_DOMAIN, top_k=top_k)
    except Exception as e:  # noqa: BLE001
        logger.warning("skill_recall_failed: %s，回退粗筛/全量", e)
        return []
    names: List[str] = []
    for c in chunks:
        text = c.get("text", "") if isinstance(c, dict) else str(c)
        m = re.search(r"\[([A-Za-z_][\w.]*)\]", text)
        if m:
            names.append(m.group(1))
    seen: set = set()
    uniq = [n for n in names if not (n in seen or seen.add(n))]
    by_name = {c["name"]: c for c in merged}
    return [by_name[n] for n in uniq if n in by_name]


def _build_menu_catalog(merged: List[dict], question: str,
                        mode: str, top_k: int) -> List[dict]:
    """按路由模式构造注入 prompt 的技能集（与总数解耦的核心开关）。

    - full         → 全量（现网行为）
    - domain       → L0 triggers 粗筛（命中≤top_k 用命中集，否则回退全量）
    - recall       → L1 rag 语义召回；召回空则回退全量
    - domain+recall→ L1 优先，召回失败再用 L0 兜底；均失败回退全量
    - 未知模式     → 安全回退全量
    """
    if mode == "full":
        return merged
    if mode == "domain":
        return _select_menu_catalog(merged, question, _prefilter_enabled(), top_k)
    if mode == "recall":
        return _recall_skills(merged, question, top_k) or merged
    if mode == "domain+recall":
        rec = _recall_skills(merged, question, top_k)
        if rec:
            return rec
        return _select_menu_catalog(merged, question, _prefilter_enabled(), top_k)
    return merged
