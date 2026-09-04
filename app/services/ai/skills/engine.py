# -*- coding: utf-8 -*-
"""工作流引擎：解释 SkillSpec，执行 capability/llm/route 三种步骤。

唯一执行入口。route 步骤可跳转，llm 步骤强制过 prompt_guard，max_llm_steps 硬上限。
"""
import re
import time
from typing import Any, Callable, Dict, Optional

from app.services.ai.skills.schema import SkillSpec


class WorkflowEngine:
    def __init__(self, get_capability: Callable[[str], Callable],
                 llm_client=None, audit_logger=None):
        self._get = get_capability
        self._llm_client = llm_client
        self._audit = audit_logger

    def run(self, skill: SkillSpec, args: Dict[str, Any],
            user_id: Optional[int] = None,
            user_permissions: Optional[set] = None) -> Any:
        from app.services.ai.capabilities.device_scope import bound_user
        with bound_user(user_id):
            return self._run(skill, args, user_id, user_permissions)

    def _run(self, skill: SkillSpec, args: Dict[str, Any],
             user_id: Optional[int], user_permissions: Optional[set]) -> Any:
        from app.services.ai.skills.permission import check_skill_permission
        check_skill_permission(skill, user_permissions or set())
        ctx: Dict[str, Any] = {"params": args or {}, "steps": {}}
        llm_step_count = 0
        step_index = {s.id: idx for idx, s in enumerate(skill.steps)}
        i = 0
        while i < len(skill.steps):
            step = skill.steps[i]
            if step.when and not self._eval(step.when, ctx):
                i += 1
                continue

            if step.type == "llm":
                llm_step_count += 1
                if llm_step_count > skill.max_llm_steps:
                    raise RuntimeError(
                        f"skill '{skill.name}' exceeds max_llm_steps={skill.max_llm_steps}")
                out = self._run_llm_step(step, ctx, user_id, skill.name)
                jump_to = None
            elif step.type == "route":
                llm_step_count += 1
                if llm_step_count > skill.max_llm_steps:
                    raise RuntimeError(
                        f"skill '{skill.name}' exceeds max_llm_steps={skill.max_llm_steps}")
                out, branch_key = self._run_route_step(step, ctx, user_id, skill.name)
                norm_key = branch_key.strip().strip('"\'`').strip().rstrip('.').lower()
                jump_to = step.branches.get(norm_key) or step.branches.get(branch_key)
            else:
                cap = self._get(step.call)
                if cap is None:
                    raise RuntimeError(f"capability not registered: {step.call}")
                resolved = self._resolve(step.args, ctx)
                out = cap(resolved)
                jump_to = None

            if step.output:
                ctx["steps"][step.id] = {"output": out}
                if step.output != step.id:
                    ctx["steps"][step.output] = out

            if jump_to is not None:
                if jump_to in step_index:
                    i = step_index[jump_to]
                elif step.type == "route":
                    raise RuntimeError(
                        f"route step '{step.id}' jump target '{jump_to}' not in steps")
                else:
                    i += 1
            elif step.type == "route":
                raise RuntimeError(
                    f"route step '{step.id}' no branch matched for {branch_key!r}")
            else:
                i += 1

        return self._resolve(skill.return_, ctx)

    def _run_llm_step(self, step, ctx, user_id, skill_name) -> str:
        from app.services.ai.prompts.registry import get_prompt
        from app.services.ai.prompt_guard import strip_sensitive_fields, sanitize_args_deep
        from app.services.ai.llm_factory import create_llm_client
        from app.services.ai.ai_audit_logger import AIAuditLogger

        tpl = get_prompt(step.call)
        if tpl is None:
            raise RuntimeError(f"prompt template not registered: {step.call}")

        raw_args = self._resolve(step.args, ctx)
        safe_args = strip_sensitive_fields(raw_args) if isinstance(raw_args, dict) else raw_args
        safe_args = sanitize_args_deep(safe_args)

        client = self._llm_client or create_llm_client()
        started = time.monotonic()
        text = client.chat(tpl.system, tpl.render_user(safe_args))
        duration_ms = int((time.monotonic() - started) * 1000)

        audit = self._audit or AIAuditLogger()
        audit.log(user_id=user_id or 0, scenario=f"skill.{skill_name}.{step.id}",
                  request=safe_args, response=text, duration_ms=duration_ms,
                  status="ok", tokens=0, model=None, base_url=None)
        return text

    def _run_route_step(self, step, ctx, user_id, skill_name):
        text = self._run_llm_step(step, ctx, user_id, skill_name)
        from app.services.ai.prompts.registry import get_prompt
        tpl = get_prompt(step.call)
        choice = text.strip()
        norm_choice = choice.strip().strip('"\'`').strip().rstrip('.').lower()
        if tpl and tpl.allowed_outputs and norm_choice not in tpl.allowed_outputs and choice not in tpl.allowed_outputs:
            raise RuntimeError(f"route step '{step.id}' returned unexpected value: {choice!r}")
        return norm_choice if norm_choice in (tpl.allowed_outputs or []) else choice, norm_choice

    def _resolve(self, node, ctx):
        if isinstance(node, str):
            return _render(node, ctx)
        if isinstance(node, dict):
            return {k: self._resolve(v, ctx) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve(v, ctx) for v in node]
        return node

    def _eval(self, expr: str, ctx) -> bool:
        return _safe_eval(expr, ctx)



_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_PATH_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)$")


def _lookup(path: str, ctx: Dict[str, Any]):
    cur = ctx
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _render(template: str, ctx: Dict[str, Any]) -> Any:
    if not isinstance(template, str):
        return template
    matches = list(_PLACEHOLDER_RE.finditer(template))
    if not matches:
        return template
    if len(matches) == 1 and template.strip() == matches[0].group(0):
        return _eval_expr(matches[0].group(1), ctx)
    parts: list = []
    last = 0
    for m in matches:
        parts.append(template[last:m.start()])
        parts.append(str(_eval_expr(m.group(1), ctx)))
        last = m.end()
    parts.append(template[last:])
    return "".join(parts)


def _eval_expr(expr: str, ctx: Dict[str, Any]) -> Any:
    expr = expr.strip()
    if "|" in expr:
        path, _, default_part = expr.partition("|")
        path = path.strip()
        default_part = default_part.strip()
        dm = re.match(r"^default\((.*)\)$", default_part)
        if not dm:
            return None
        default_val = _parse_literal(dm.group(1))
        if not _PATH_RE.match(path):
            return default_val
        val = _lookup(path, ctx)
        return default_val if val is None else val
    if _PATH_RE.match(expr):
        return _lookup(expr, ctx)
    return _parse_literal(expr)


def _parse_literal(s: str) -> Any:
    s = s.strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "None", ""):
        return None
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


_OP_RE = re.compile(r"^(.*?)\s*(==|!=|>=|<=|>|<)\s*(.*)$")


def _safe_eval(expr: str, ctx: Dict[str, Any]) -> bool:
    expr = expr.strip()
    if expr.startswith("not "):
        return not _safe_eval(expr[4:], ctx)
    m = _OP_RE.match(expr)
    if m:
        left = _eval_expr(m.group(1), ctx)
        op = m.group(2)
        right = _parse_literal(m.group(3))
        try:
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
        except TypeError:
            return False
    val = _eval_expr(expr, ctx)
    return bool(val)
