# -*- coding: utf-8 -*-
"""有界 agent loop：工具面收拢到已注册 capability，仅调用顺序交给 LLM 自主决定。

LLMClient 无 chat_with_tools，故采用 JSON 决策协议：
每轮 LLM 输出 JSON，要么 {"final_answer": "..."} 终止，要么 {"tool": "name", "args": {...}} 调工具。
"""
import json
import time
from typing import Optional

from app.services.ai.capabilities.registry import get_capability, get_required_permission
from app.services.ai.prompt_guard import strip_sensitive_fields, strip_sensitive_result
from app.services.ai.skills.permission import SkillPermissionDenied
from app.services.ai.llm_factory import create_llm_client
from app.services.ai.ai_audit_logger import AIAuditLogger
from app.services.ai.circuit_breaker import get_circuit_breaker, AICircuitOpenError
from app.services.ai.agentic.skill_as_capability import call_tier1_skill_as_tool
from app.services.ai.command_safety import enforce_confirmation
from app.services.ai.confidence import compute_confidence, extract_confidence_inputs
from app.services.ai.diagnosis_session_service import DiagnosisSessionService
from app.utils.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_DIAGNOSIS = "诊断未完成，已采集多轮数据但未能定位根因，建议人工介入。"
_CIRCUIT_OPEN = "AI 服务暂不可用（熔断开启），请稍后重试。"

_DECISION_SYSTEM = (
    "你是一个决策器。每轮你必须只输出一个 JSON 对象，不要输出任何其他文字。\n"
    "若已能给出最终答案，输出：<<FINAL>>\n"
    "若需要调用工具，输出：<<TOOL>>\n"
    "可用工具列表：{tools}\n"
    "上一轮工具调用结果（如有）：{last_tool_result}"
)


_MAX_TOOL_RESULT_CHARS = 4000  # 单条工具结果上限（头尾各保留一半）
_MAX_QUESTION_CHARS = 4000     # 用户输入上限（E1 修复）
_MAX_HISTORY_ROUNDS = 4        # prompt 中保留最近 N 轮工具结果


from app.services.ai.prompt_guard import truncate_text as _truncate


def _summarize_tool_result(msg: dict) -> str:
    """把一轮工具结果压缩为单行证据摘要（用于滑窗剔除后保留线索）。

    设计文档第五节末尾决策点2选①：滑窗剔除旧轮次时同步生成一行证据摘要插入
    prompt 头部，避免第 5/6 轮丢失前 2 轮工具结果导致 Agent 重复调用相同工具。
    摘要只保留工具名 + 结果前 120 字符，足以让 LLM 知道"之前查过什么、大致结论"，
    不保留完整结果（完整结果仍在审计日志中可追溯）。

    Args:
        msg: {"role": "tool", "name": <tool>, "content": <result>} 结构。

    Returns:
        形如 "rag.retrieve: CPU 高排查方法→需查会话数/SYN半连接..." 的单行摘要。
    """
    name = msg.get("name", "unknown")
    content = msg.get("content", "")
    if isinstance(content, str):
        preview = content.replace("\n", " ")[:120]
    else:
        preview = str(content)[:120]
    return f"{name}: {preview}"


def _is_pretruncated(result) -> bool:
    """capability 内部是否已完成「关键行优先」的截断。

    设计文档 §3.2 要求 SSH 回显截断前先提取故障特征行。若 runner 层随后再按
    「头尾各半」裁剪一次，恰好会把这些关键行重新切掉，使 capability 的策略失效。
    故已声明 truncated 的结果不再二次裁剪，只保留长度上限的兜底语义。
    """
    if not isinstance(result, dict):
        return False
    if result.get("truncated") is True:
        return True
    out = result.get("output")
    return isinstance(out, dict) and out.get("truncated") is True


def _build_prompt_payload(messages: list) -> str:
    """把对话历史序列化为模型输入，并对工具结果应用滑动窗口。

    仅保留最近 _MAX_HISTORY_ROUNDS 轮工具结果，更早的以证据摘要形式插入 prompt
    头部（决策点2选①），避免第 5/6 轮丢失前 2 轮工具结果导致 Agent 重复调用。
    system 指令与用户原始问题始终保留，避免丢失任务上下文。

    Args:
        messages: [system, user, tool...] 结构的历史列表。

    Returns:
        序列化后的 JSON 字符串。
    """
    head = messages[:2]  # system 指令 + 用户原始问题
    tool_msgs = [m for m in messages[2:] if m.get("role") == "tool"]
    kept = tool_msgs[-_MAX_HISTORY_ROUNDS:]
    omitted_msgs = tool_msgs[:-_MAX_HISTORY_ROUNDS] if len(tool_msgs) > _MAX_HISTORY_ROUNDS else []
    payload = list(head)
    if omitted_msgs:
        summaries = [_summarize_tool_result(m) for m in omitted_msgs]
        payload.append({"role": "tool", "name": "system",
                        "content": "【更早轮次证据摘要（完整结果见审计日志）】\n" + "\n".join(summaries)})
    payload.extend(kept)
    return json.dumps(payload, ensure_ascii=False)


def _parse_decision(text: str) -> dict:
    """解析 LLM 输出为决策 dict。容错：去 markdown fence。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        return {}


class AgenticSkillRunner:
    """有界 agent loop 执行器。

    Attributes:
        last_session_id: 本次 run() 创建的诊断会话 ID（供路由层回传前端，
            使 remedial 执行能反查并标记会话）。会话持久化失败时为 None。
    """

    def __init__(self, client=None, audit=None, sessions=None):
        self.client = client or create_llm_client()
        self.audit = audit or AIAuditLogger()
        self.sessions = sessions or DiagnosisSessionService()
        self.last_session_id: Optional[int] = None

    def _start_session(self, spec, user_id: int, safe_question: str) -> Optional[int]:
        """创建诊断会话（旁路：失败仅记日志，不中断诊断）。

        诊断会话属审计/回溯旁路，其失败不应让用户拿不到诊断结论，
        故此处捕获异常并记录 error 日志，而不是向上抛出。
        """
        try:
            return self.sessions.create_session(
                device_id=None, user_id=user_id,
                skill_name=spec.name, question=safe_question,
            )
        except Exception as e:  # noqa: BLE001 - 旁路持久化失败不阻断诊断
            logger.error("agentic.%s create diagnosis session failed: %s",
                         spec.name, e, exc_info=True)
            return None

    def _finish_session(self, spec, session_id: Optional[int], rounds: list,
                        answer: str, status: str, duration_ms: int) -> None:
        """结束诊断会话并回填 device_id（旁路：失败仅记日志）。"""
        if session_id is None:
            return
        try:
            device_id = None
            for r in rounds:
                args = r.get("args") or {}
                if isinstance(args, dict) and isinstance(args.get("device_id"), int):
                    device_id = args["device_id"]
                    break
            self.sessions.complete_session(
                session_id=session_id, rounds=rounds, final_answer=answer,
                status=status, duration_ms=duration_ms,
            )
            if device_id is not None:
                self.sessions.set_device_id(session_id, device_id)
        except Exception as e:  # noqa: BLE001 - 旁路持久化失败不阻断诊断
            logger.error("agentic.%s complete diagnosis session failed: %s",
                         spec.name, e, exc_info=True)

    def run(self, spec, instructions: str, question: str,
            user_id: int, user_permissions: set) -> str:
        from app.services.ai.capabilities.registry import is_registered
        tools = []
        for name in spec.allowed_capabilities:
            if not is_registered(name):
                logger.warning("agentic.%s allowed_capability %r not registered, skipped",
                               spec.name, name)
                continue
            perm = get_required_permission(name)
            if perm is None or perm in user_permissions:
                tools.append(name)
        skill_tools = list(spec.allowed_skills)
        all_tool_names = tools + skill_tools

        from app.services.ai.prompt_guard import sanitize_user_input
        safe_question = _truncate(sanitize_user_input(question), _MAX_QUESTION_CHARS)
        messages = [{"role": "system", "content": instructions},
                    {"role": "user", "content": safe_question}]
        last_tool_result = ""

        session_id = self._start_session(spec, user_id, safe_question)
        self.last_session_id = session_id if isinstance(session_id, int) else None
        session_id = self.last_session_id
        rounds: list = []  # 每轮 {tool, args, result} 原始记录，供 confidence 与会话留存
        run_started = time.monotonic()

        for round_i in range(spec.max_iterations):
            started = time.monotonic()
            system_prompt = _DECISION_SYSTEM.format(
                tools=", ".join(all_tool_names) or "(无)",
                last_tool_result=last_tool_result or "(无)",
            ).replace("<<FINAL>>", '{"final_answer": "你的答案"}').replace("<<TOOL>>", '{"tool": "工具名", "args": {参数}}')
            user_prompt = _build_prompt_payload(messages)
            try:
                raw = get_circuit_breaker("agentic").call(
                    lambda: self.client.chat(system_prompt, user_prompt)
                )
            except AICircuitOpenError:
                answer = json.dumps({
                    "diagnosis": _CIRCUIT_OPEN,
                    "confidence": 0.0,
                    "evidence": [],
                    "proposed_commands": [],
                    "incomplete": True,
                }, ensure_ascii=False)
                self._finish_session(
                    spec, session_id, rounds, answer, status="error",
                    duration_ms=int((time.monotonic() - run_started) * 1000),
                )
                return answer
            duration_ms = int((time.monotonic() - started) * 1000)

            decision = _parse_decision(raw) if isinstance(raw, str) else {}

            self.audit.log(
                user_id=user_id, scenario=f"agentic.{spec.name}.round{round_i}",
                request={"tool": decision.get("tool"), "args": decision.get("args")},
                response={"llm_raw": raw, "tool_result": last_tool_result or None},
                duration_ms=duration_ms, status="ok",
                model=None, base_url=None,
            )

            if "final_answer" in decision:
                fa = decision["final_answer"]
                if isinstance(fa, (dict, list)):
                    answer = self._finalize_answer(fa, rounds)
                else:
                    fallback = {
                        "diagnosis": str(fa),
                        "confidence": 0.0,
                        "evidence": [],
                        "proposed_commands": [],
                    }
                    answer = self._finalize_answer(fallback, rounds)
                self._finish_session(
                    spec, session_id, rounds, answer, status="completed",
                    duration_ms=int((time.monotonic() - run_started) * 1000),
                )
                return answer

            call_name = decision.get("tool")
            call_args = decision.get("args", {}) or {}

            if call_name not in all_tool_names:
                last_tool_result = f"{call_name or 'unknown'}: 该操作不在当前技能允许的能力范围内。"
                messages.append({"role": "tool", "name": call_name or "unknown",
                                 "content": last_tool_result})
                continue

            if call_name in skill_tools:
                fn = call_tier1_skill_as_tool(
                    call_name, user_id=user_id, user_permissions=user_permissions)
            else:
                fn = get_capability(call_name)

            safe_args = strip_sensitive_fields(call_args) if isinstance(call_args, dict) else call_args
            from app.services.ai.prompt_guard import sanitize_args_deep
            safe_args = sanitize_args_deep(safe_args)
            try:
                from app.services.ai.capabilities.device_scope import bound_user
                with bound_user(user_id):
                    result = fn(safe_args)
            except SkillPermissionDenied:
                self._finish_session(
                    spec, session_id, rounds, "权限不足，诊断已中断",
                    status="error",
                    duration_ms=int((time.monotonic() - run_started) * 1000),
                )
                raise
            except Exception as e:  # noqa: BLE001
                logger.error("agentic.%s capability=%s failed: %s",
                             spec.name, call_name, e, exc_info=True)
                self.audit.log(
                    user_id=user_id, scenario=f"agentic.{spec.name}.capability_error",
                    request={"tool": call_name, "args": safe_args},
                    response={"error_type": type(e).__name__, "error": str(e)},
                    duration_ms=0, status="error", model=None, base_url=None,
                )
                result = f"能力调用失败：{type(e).__name__}"
            rounds.append({"round": round_i, "tool": call_name,
                           "args": safe_args, "result": result})
            safe_result = strip_sensitive_result(result)
            raw_summary = f"{call_name}: {safe_result}"
            if _is_pretruncated(safe_result) or len(raw_summary) <= _MAX_TOOL_RESULT_CHARS:
                tool_summary = raw_summary
            else:
                tool_summary = _truncate(raw_summary, _MAX_TOOL_RESULT_CHARS)
            last_tool_result = tool_summary
            messages.append({"role": "tool", "name": call_name, "content": tool_summary})

        incomplete = {
            "diagnosis": _FALLBACK_DIAGNOSIS,
            "confidence": 0.0,
            "evidence": [_summarize_tool_result({"name": r.get("tool"),
                                                 "content": r.get("result")})
                         for r in rounds],
            "proposed_commands": [],
            "incomplete": True,
        }
        answer = json.dumps(incomplete, ensure_ascii=False)
        self._finish_session(
            spec, session_id, rounds, answer, status="incomplete",
            duration_ms=int((time.monotonic() - run_started) * 1000),
        )
        return answer

    def _finalize_answer(self, final_answer, rounds: list) -> str:
        """结构化 final_answer 的后处理：强制确认 + 混合置信度 + 验证回路字段。

        Args:
            final_answer: LLM 输出的 final_answer dict。
            rounds: 每轮 {round, tool, args, result} 原始记录。

        Returns:
            JSON 字符串（ensure_ascii=False）。
        """
        commands = final_answer.get("proposed_commands")
        if isinstance(commands, list):
            final_answer["proposed_commands"] = enforce_confirmation(commands)

        inputs = extract_confidence_inputs(rounds, final_answer)
        final_answer["confidence"] = compute_confidence(
            total_checks=inputs["total_checks"],
            successful_checks=inputs["successful_checks"],
            anomalous_metrics=inputs["anomalous_metrics"],
            baseline_hit_3sigma=inputs["baseline_hit_3sigma"],
            rag_top1_score=inputs["rag_top1_score"],
            llm_self_eval=inputs["llm_self_eval"],
        )

        final_answer["anomalous_metrics"] = inputs["anomalous_metric_names"]
        final_answer["pre_snapshot"] = inputs["pre_snapshot"]

        return json.dumps(final_answer, ensure_ascii=False)
