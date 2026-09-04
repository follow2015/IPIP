# -*- coding: utf-8 -*-
"""NL 入口：LLM 从技能目录选一个技能 + 填参数，交给 WorkflowEngine 或 AgenticSkillRunner 执行。

本身不含业务逻辑，只做"选择 + 分发"，因此不做成技能（避免技能选技能的自指结构）。

Phase 2.5：扩展支持 agentic skill 路由。LLM 同时看到 Tier1 catalog 和 agentic catalog，
选中 agentic skill（category=agentic）时路由到 AgenticSkillRunner，否则路由到 WorkflowEngine。
"""
import json
from typing import Callable, List, Optional

from app.services.ai.skills.engine import WorkflowEngine
from app.services.ai.skills.permission import check_skill_permission, SkillPermissionDenied
from app.services.ai.skills.loader import default_skill_dirs, default_agentic_dirs
from app.services.ai.capabilities.registry import get_capability
from app.services.ai.llm_factory import create_llm_client

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
    '找不到匹配技能时返回 {"skill": null}。'
    '深度诊断/根因分析/故障排查类问题优先选 category=agentic 的技能。'
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
            return "（AI 未配置）"

        tier1_catalog = self._load_catalog(_skill_dirs())
        agentic_catalog = self._load_agentic_catalog(_agentic_dirs())
        merged = list(tier1_catalog) + list(agentic_catalog)
        menu = json.dumps(
            [{k: c.get(k) for k in ("name", "title", "description", "category", "triggers")}
             for c in merged],
            ensure_ascii=False,
        )
        from app.services.ai.prompt_guard import sanitize_user_input
        safe_question = sanitize_user_input(question)
        raw = self.client.chat(_SYSTEM, f"技能目录：{menu}\n用户问题：{safe_question}")
        try:
            decision = json.loads(_strip_fence(raw))
        except (json.JSONDecodeError, ValueError):
            return "抱歉，我无法理解该问题。"

        skill_name = decision.get("skill")
        if not skill_name:
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
            return f"参数校验未通过：{e}"

        result = self.engine.run(
            skill, args,
            user_id=user_id, user_permissions=user_permissions,
        )
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    def _run_agentic(self, skill_name: str, question: str,
                     user_id: int, user_permissions: set) -> str:
        """路由到 AgenticSkillRunner 执行 agentic 技能。"""
        from app.services.ai.agentic.loader import load_agentic_skill
        from app.services.ai.agentic.runner import AgenticSkillRunner

        try:
            spec, instructions = load_agentic_skill(skill_name, _agentic_dirs())
        except KeyError:
            return f"未找到 agentic 技能：{skill_name}"

        runner = AgenticSkillRunner()
        answer = runner.run(spec, instructions, question,
                            user_id=user_id, user_permissions=user_permissions)
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
