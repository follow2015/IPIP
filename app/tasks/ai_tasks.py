# -*- coding: utf-8 -*-
"""AI 长任务定义（Celery，方案 §Phase 2）。

仅本模块与 `app/celery_app.py` 依赖 celery，API / 服务层不直接依赖，保持分层。

进度通道：统一写 `task_state`（Redis `ai:task:{task_id}`，TTL 1h），SSE 端点
逻辑不变，前端零改造即可拿到进度（详见方案 §2）。

app context：由 `app/celery_app.ContextTask` 自动注入，task 内可直接使用
db.session / ORM / AuditService。

**与方案 v2 的两处偏差（实施时按代码实际情况修正）**：

1. `session_id` 不由路由层传入——它由 `AgenticSkillRunner._start_session()` 在
   task 内部创建，路由层靠 `runner.last_session_id` 取。异步化后路由层在 202
   响应时任务尚未执行，拿不到 session_id。故本模块把 session_id 写进
   `task_state`，前端从进度流的 done 事件里取（接口契约相应调整，见方案 §5）。

2. runner 的**正常返回路径已经自己收尾 session**（`_finish_session`），task 不
   应重复收尾。task 只负责**异常路径**（含软超时）的收尾，避免孤儿 session
   ——这才是方案 Q2 真正要补的缺口。
"""
import time
from typing import Any, Dict, List, Optional

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery
from app.services.ai import task_state
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TransientAIError(Exception):
    """AI 调用的瞬态错误（限流 / 超时 / 5xx），可安全重试。

    用于 `autoretry_for`：LLM provider 返回 429 / 5xx 或网络超时时重试有意义，
    而参数错误、权限不足等永久性错误重试只会浪费算力。

    注意：provider **不会主动抛**这个类型——它把所有异常统一包装成
    `ExternalServiceError`。由 `_classify_transient()` 在 task 出口做分类映射，
    见下方说明。
    """


def _classify_transient(exc: Exception) -> bool:
    """判断异常是否为可安全重试的瞬态错误。

    为什么需要它：provider 层（openai_provider）把 429/5xx/网络错误统一包装成
    `ExternalServiceError`，不保留可区分的异常类型。若直接 `autoretry_for=(
    ExternalServiceError,)`，则 400 参数错误这类**永久错误也会被重试**，白白
    消耗算力还会放大故障。故在此按状态码分类。

    判定规则（保守优先，未知异常不重试）：
    - `TransientAIError` 本身 → 瞬态（允许 provider 未来显式抛出）；
    - 网络类异常（ConnectionError / TimeoutError / OSError）→ 瞬态；
    - `ExternalServiceError` 且状态码为 429、5xx、或**无状态码**（连接阶段就
      失败，请求根本没到服务端）→ 瞬态；
    - 其余（含 4xx 客户端错误）→ 永久，不重试。

    Args:
        exc: 待判定的异常。

    Returns:
        是否可安全重试。
    """
    if isinstance(exc, TransientAIError):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    from app.exceptions.system import ExternalServiceError

    if isinstance(exc, ExternalServiceError):
        details = getattr(exc, "details", None) or {}
        code = details.get("status_code")
        if code is None:
            return True  # 无状态码 = 连接阶段就失败，请求未到达服务端
        return code == 429 or code >= 500
    return False


def _should_retry(exc: Exception, retries: int, max_retries: Optional[int]) -> bool:
    """是否还有重试额度且错误可重试。

    Args:
        exc: 本次异常。
        retries: 已重试次数（`self.request.retries`）。
        max_retries: 重试上限（None 视为 0）。

    Returns:
        是否应转为 TransientAIError 交 autoretry 处理。
    """
    return retries < (max_retries or 0) and _classify_transient(exc)


def _session_id_of(runner: Any) -> Optional[int]:
    """从 runner 提取本轮创建的会话 ID，未创建则返回 None。

    `last_session_id` 在会话创建失败时可能是 None 或非 int 的占位值，统一在此
    收敛类型判断，避免在多条异常分支里重复。

    Args:
        runner: AgenticSkillRunner 实例。

    Returns:
        会话 ID，或 None。
    """
    session_id = runner.last_session_id
    return session_id if isinstance(session_id, int) else None


def _safe_fail_session(session_id: Optional[int], reason: str) -> None:
    """把会话标记为失败（旁路：失败仅记日志，不掩盖原始异常）。

    Args:
        session_id: 会话 ID，None 表示会话未创建成功。
        reason: 失败原因（错误类型名）。
    """
    if session_id is None:
        return
    try:
        from app.services.ai.diagnosis_session_service import DiagnosisSessionService
        DiagnosisSessionService().complete_session(
            session_id=session_id, rounds=[],
            final_answer={"error": reason}, status="error",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task.session_fail_marker_failed session=%s: %s",
                       session_id, e)


def _progress(task_id: str, status: str, progress: int, total: int,
              result: Any = None, user_id: Optional[int] = None,
              **extra) -> None:
    """写入进度状态。

    Args:
        task_id: Celery task id。
        status: pending / running / done / error。
        progress/total: 进度计数（诊断按轮次，非检查项数量）。
        result: 结果负载。
        user_id: 发起用户 ID。进度端点据此做**任务归属校验**（§6.3）——
            仅校验 ai:use 权限不足以防止他人订阅任务流。
            必须由 task 参数传入：Celery worker 无 request context，
            在 task 内调 get_current_user_id() 只会得到 None。
        **extra: 附加字段（如 session_id）。
    """
    task_state.save(task_id, {"status": status, "progress": progress,
                              "total": total, "result": result,
                              "user_id": user_id, **extra})



@celery.task(bind=True, queue="ai",
             time_limit=1800, soft_time_limit=1500,
             autoretry_for=(TransientAIError,), retry_backoff=True,
             retry_backoff_max=60, retry_jitter=True, max_retries=3)
def run_agentic_diagnosis(self, name: str, question: str, user_id: int,
                          user_perms: List[str], instructions: str = "",
                          max_iterations: Optional[int] = None) -> Dict[str, Any]:
    """执行 agentic 诊断技能（有界 agent loop）。

    Args:
        name: 技能名（用于 load_agentic_skill）。
        question: 用户问题（路由层已做长度与类型校验）。
        user_id: 发起用户 ID（审计与会话归属）。
        user_perms: 用户权限码列表。必须是 list 而非 set——JSON 序列化约束
            （方案 Q1），task 内重建为 set 供 runner 使用。
        instructions: 技能指令。缺省则在 task 内加载（worker 侧文件系统可见）。
        max_iterations: 覆盖技能默认轮次上限（可选）。

    Returns:
        {"answer": str, "session_id": int|None}，同时写入 task_state。
    """
    task_id = self.request.id
    from app.services.ai.agentic.loader import load_agentic_skill
    from app.services.ai.agentic.runner import AgenticSkillRunner
    from app.services.ai.metrics import record_skill_run

    started = time.monotonic()
    runner = AgenticSkillRunner()
    perms_set = set(user_perms or ())

    spec, loaded_instructions = load_agentic_skill(name)
    instructions = instructions or loaded_instructions
    if max_iterations:
        spec.max_iterations = max_iterations

    _progress(task_id, "running", 0, spec.max_iterations, None,
              user_id=user_id, session_id=None)
    try:
        answer = runner.run(spec, instructions, question,
                            user_id=user_id, user_permissions=perms_set)
        session_id = _session_id_of(runner)
        record_skill_run(skill_name=f"agentic.{name}", status="ok",
                         duration_seconds=time.monotonic() - started)
        _progress(task_id, "done", spec.max_iterations, spec.max_iterations,
                  {"answer": answer}, user_id=user_id, session_id=session_id)
        return {"answer": answer, "session_id": session_id}

    except SoftTimeLimitExceeded:
        session_id = _session_id_of(runner)
        _safe_fail_session(session_id, "soft_time_limit")
        record_skill_run(skill_name=f"agentic.{name}", status="error",
                         duration_seconds=time.monotonic() - started)
        _progress(task_id, "error", 0, spec.max_iterations,
                  "SoftTimeLimitExceeded", user_id=user_id,
                  session_id=session_id)
        raise

    except Exception as e:  # noqa: BLE001
        session_id = _session_id_of(runner)

        if _should_retry(e, self.request.retries, self.max_retries):
            _progress(task_id, "running", 0, spec.max_iterations, None,
                      user_id=user_id, session_id=session_id)
            logger.warning(
                "ai.task.agentic_retryable name=%s retries=%s/%s: %s",
                name, self.request.retries, self.max_retries, e)
            raise TransientAIError(f"{type(e).__name__}: {e}") from e

        _safe_fail_session(session_id, type(e).__name__)
        record_skill_run(skill_name=f"agentic.{name}", status="error",
                         duration_seconds=time.monotonic() - started)
        _progress(task_id, "error", 0, spec.max_iterations, type(e).__name__,
                  user_id=user_id, session_id=session_id)
        raise



@celery.task(bind=True, queue="ai",
             time_limit=600, soft_time_limit=500, max_retries=0)
def rag_ingest_task(self, task_id: str, docs_dir: str,
                    user_id: Optional[int] = None) -> Dict[str, Any]:
    """RAG 文档入库（替换原线程池执行路径）。

    入库实现委托 `rag_ingest_async.run_ingest`（H2 修复）——该函数是 Celery 路径
    与同步回退路径共用的唯一实现，避免两份副本漂移。本 task 只负责异常转进度。

    Args:
        task_id: **外部指定的** task id。路由层 `ingest_async` 先生成 uuid4 再
            入队，使接口返回的 task_id 与进度键一致（保持既有前端契约）。
        docs_dir: 待入库文档目录。`run_ingest` 内部会做白名单校验（H1 修复）。
        user_id: 发起用户 ID（进度归属校验用，见 §6.3）。

    Returns:
        {"ingested": int}。
    """
    from app.services.ai.rag_ingest_async import run_ingest

    try:
        count = run_ingest(task_id, docs_dir, user_id)
        return {"ingested": count}
    except Exception as e:  # noqa: BLE001
        _progress(task_id, "error", 0, 0, type(e).__name__, user_id=user_id)
        logger.warning("rag.task.failed %s", e)
        raise



@celery.task(bind=True, queue="ai",
             acks_late=False,  # at-most-once：崩溃不重投（重复下发比丢失更危险）
             time_limit=300, soft_time_limit=240,
             max_retries=0)  # 不重试：重试 = 重复下发
def execute_remedial_task(self, task_id: str, device_id: int, command_key: str,
                          params: Dict[str, Any], brand: str = "",
                          session_id: Optional[int] = None,
                          user_id: Optional[int] = None,
                          confirmed: bool = False) -> Dict[str, Any]:
    """向真实设备下发 remedial 修复命令。

    安全边界（方案 §Phase 3）：权限校验、二次确认、命令白名单渲染均在路由层
    （同步，返回 202 前）完成。本 task 只负责**执行**已通过校验的
    `command_key + params`，不重新做权限校验，但保留设备写锁与审计。
    P0-3 例外：confirmed 在 task 内二次校验（纵深防御第二道门）。

    幂等性（方案 §6.1）：由路由层的 `idempotency_key` 原子占位保证（入队前），
    **不在 task 内做幂等检查**——task 内查 task_state 只能防 Celery 重投，而
    acks_late=False 已堵死该路径；真正需要防的客户端重试必须用客户端侧确定性
    键在入队前拦截。

    Args:
        task_id: 外部指定的 task id（路由层生成，与幂等占位记录一致）。
        device_id: 目标设备 ID。
        command_key: 已通过白名单校验的命令键。
        params: 命令参数（已校验）。
        brand: 设备 brand（enterprise 号字符串），用于命令族路由。
        session_id: 关联诊断会话（成功时标记 remedial_executed）。
        user_id: 发起用户（审计留痕）。
        confirmed: 用户确认标记（P0-3 纵深防御）。路由层已校验并透传
            True；task 侧再验一道，防止未来新调用方绕过路由直接入队。
            默认 False（fail-closed）——旧签名调用方/未知消息缺该字段时拒绝执行。

    Returns:
        remedial_executor.execute() 的结果字典。
    """
    from app.services.ai.remedial_executor import RemedialExecutor

    def _progress(status: str, result: Any = None):
        task_state.save(task_id, {"status": status, "progress": 0,
                                  "total": 1, "result": result,
                                  "user_id": user_id})

    _progress("running", None)
    if confirmed is not True:
        _progress("error", "unconfirmed")
        return None
    try:
        result = RemedialExecutor().execute(
            device_id=device_id, command_key=command_key, params=params,
            brand=brand, session_id=session_id, confirmed=confirmed,
        )
        _progress("done", result)
        return result
    except Exception as e:  # noqa: BLE001
        _progress("error", type(e).__name__)
        raise
