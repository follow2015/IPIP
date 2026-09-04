# -*- coding: utf-8 -*-
"""AI 接口蓝图。

Phase 2 重写：收敛为四类核心端点 + 必要管理端点。
- GET  /skills              列技能目录
- POST /skills/<name>/run   执行技能
- POST /ask                 NL 自然语言入口
- POST /rag/ingest          RAG 文档入库
- 管理端点：/health /config /circuit /metrics /skills/<name> /skills/reload
"""
from flask import Blueprint, request, Response, stream_with_context
from app.api.base import APIResponse, api_exception_handler
from app.openapi.doc import doc
from app.services.ai.llm_factory import create_llm_client
from app.services.ai.rag_store import RAGStore
from app.services.ai.rag_ingest_async import ingest_async, get_progress
from app.services.ai import task_state
from app.services.ai.skill_admin_service import (
    list_skills,
    get_skill,
    set_skill_enabled,
    reload_catalog,
    create_skill,
    update_skill_content,
    delete_skill,
    BuiltinSkillProtected,
)
from app.services.ai.skills.schema import SkillValidationError
from app.services.ai.config_admin_service import get_config, update_config
from app.services.ai.monitor_admin_service import (
    get_circuit_status,
    reset_circuit,
    get_metrics_summary,
)
from app.utils.auth import (
    permission_required,
    sse_permission_required,
    get_current_user_id,
    get_user_permissions,
    _sse_error_response,
)
from app.utils.rate_limiting.decorators import rate_limit
from app.utils.logging import get_logger

logger = get_logger(__name__)

bp = Blueprint("ai", __name__)  # url_prefix 在 register_blueprints 处传入


def _check_device_access(device_id: int,
                         *, fail_closed: bool = False) -> "tuple[bool, str]":
    """C2 修复：设备级（数据域）鉴权。

    校验当前用户是否有权操作指定设备。复用 data_scope_service.get_visible_device_ids：
    - 返回 None 表示无限制（data_scope=all 或超管）
    - 返回 set 表示受限，device_id 必须在集合内

    Args:
        device_id: 目标设备 ID。
        fail_closed: data_scope 服务故障时的降级语义（P0-4）。
            False（默认）= fail-open 放行，适用查询/预览等只读路径；
            True = 拒绝并 403，适用 execute/rollback 等设备写路径——
            鉴权服务不可用不能成为绕过数据域、向真实设备下发变更的通道。

    Returns:
        (True, "") 有权限
        (False, reason) 无权限/服务故障拒绝，reason 用于 403 响应
    """
    user_id = get_current_user_id()
    if not user_id:
        return False, "无法识别当前用户"
    try:
        from app.services.monitoring.data_scope_service import get_visible_device_ids
        visible = get_visible_device_ids(user_id)
        if visible is None:
            return True, ""  # 无限制
        if device_id in visible:
            return True, ""
        return False, f"无权操作设备 {device_id}（数据域隔离）"
    except Exception:  # noqa: BLE001
        logger.warning(
            "ai.device_scope_check_failed user=%s device=%s fail_closed=%s",
            user_id, device_id, fail_closed,
        )
        if fail_closed:
            return False, "设备权限服务暂不可用，已拒绝该操作"
        return True, ""


def _parse_device_id(raw) -> "tuple[int | None, str | None]":
    """I4 修复：安全解析 device_id，非数字返回 (None, error_msg)。"""
    if raw is None or raw == "":
        return None, "device_id 必填"
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, f"device_id 必须为整数，收到: {raw!r}"


def _validate_docs_dir(docs_dir: str) -> str:
    """校验 RAG 入库 docs_dir 必须在 AI_DOCS_ROOT 白名单根目录之下（C2 修复）。

    实现已下沉到 services 层（`docs_dir_validation`），供 Celery task 复用同一套
    校验作为纵深防御（H1 修复），避免 task 反向依赖 api 层。

    Args:
        docs_dir: 用户传入的文档目录路径

    Returns:
        校验通过后的绝对路径

    Raises:
        ValueError: 路径越界或不存在
    """
    from app.services.ai.docs_dir_validation import validate_docs_dir

    return validate_docs_dir(docs_dir)


@bp.get("/skills")
@doc(summary="列出 AI 技能目录", tags=["AI"],
     responses={200: "AISkillsListResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@rate_limit("30 per minute")
@api_exception_handler
def skills_list():
    """列技能目录（仅元数据）。"""
    return APIResponse.success(data={"skills": list_skills()})


@bp.post("/skills/<name>/run")
@doc(summary="执行 AI 技能", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AISkillRunRequest"}}}},
     responses={200: "AISkillRunResponse", 401: "ApiError", 403: "ApiError", 404: "ApiError"})
@permission_required("ai:use")
@rate_limit("10 per minute")
@api_exception_handler
def skills_run(name):
    """执行指定技能。

    技能执行前聚合校验权限：若技能引用了需 ai:execute 等权限的 capability，
    而当前用户无此权限，返回 403。
    """
    from app.services.ai.skills.loader import load_skill, default_skill_dirs
    from app.services.ai.skills.engine import WorkflowEngine
    from app.services.ai.skills.permission import check_skill_permission, SkillPermissionDenied
    from app.services.ai.capabilities.registry import get_capability

    SKILL_DIRS = default_skill_dirs()
    user_id = get_current_user_id() or 0
    user_perms = get_user_permissions(user_id)

    try:
        skill = load_skill(name, SKILL_DIRS)
    except KeyError:
        return APIResponse.error(f"技能不存在：{name}", status_code=404)

    try:
        check_skill_permission(skill, user_perms)
    except SkillPermissionDenied as e:
        return APIResponse.error(
            f"权限不足，需要：{'/'.join(e.missing)}",
            error_code="AUTHORIZATION_ERROR", status_code=403,
        )

    args = request.get_json(silent=True) or {}
    from app.services.ai.skills.schema import validate_skill_args, SkillArgsError
    try:
        validate_skill_args(skill, args)
    except SkillArgsError as e:
        return APIResponse.error(str(e), status_code=400)
    engine = WorkflowEngine(get_capability=get_capability)
    import time as _time
    from app.services.ai.metrics import record_skill_run
    from app.services.ai._runtime import observe_call
    _t0 = _time.monotonic()
    result = None
    status = "ok"
    try:
        result = engine.run(skill, args, user_id=user_id)
        return APIResponse.success(data={"result": result})
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = int((_time.monotonic() - _t0) * 1000)
        record_skill_run(skill_name=name, status=status,
                         duration_seconds=_time.monotonic() - _t0)
        observe_call(scenario=f"skill.{name}", user_id=user_id,
                     request=args, response=result if status == "ok" else None,
                     status=status, duration_ms=duration_ms)


@bp.post("/ask")
@doc(summary="AI 自然语言问答", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AIAskRequest"}}}},
     responses={200: "AIAskResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@rate_limit("10 per minute")
@api_exception_handler
def ask():
    """NL 自然语言入口：LLM 选技能 + 填参数 → WorkflowEngine 执行。"""
    from app.services.ai.nlquery_router import NLQueryRouter

    question = (request.get_json(silent=True) or {}).get("question", "")
    if not isinstance(question, str):
        return APIResponse.error("question 必须为字符串", status_code=400)
    if len(question) > 2000:
        return APIResponse.error("问题过长，请控制在 2000 字以内")
    user_id = get_current_user_id() or 0
    user_perms = get_user_permissions(user_id)

    from app.services.ai._runtime import observe_call, CallTimer
    status = "ok"
    answer = ""
    with CallTimer() as t:
        try:
            router = NLQueryRouter()
            answer = router.ask(question, user_id=user_id, user_permissions=user_perms)
        except Exception:
            status = "error"
            raise
        finally:
            observe_call(scenario="nlq", user_id=user_id,
                         request={"question": question},
                         response={"answer": answer} if status == "ok" else None,
                         status=status, duration_ms=t.duration_ms)
    session_id = router.last_session_id
    return APIResponse.success(data={
        "answer": answer,
        "session_id": session_id if isinstance(session_id, int) else None,
    })


from app.services.ai.skills.loader import default_agentic_dirs



@bp.get("/agentic/skills")
@doc(summary="列出 agentic 技能目录", tags=["AI"],
     responses={200: "AIAgenticSkillsListResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:agentic")
@api_exception_handler
def list_agentic_skills():
    """列出所有 agentic 技能元数据。"""
    from app.services.ai.agentic.loader import load_agentic_catalog

    catalog = load_agentic_catalog(default_agentic_dirs())
    return APIResponse.success(data={"skills": catalog})


@bp.post("/agentic/skills/<name>/run")
@doc(summary="执行 agentic 技能（多轮自主诊断）", tags=["AI"],
     responses={200: "AIAgenticRunResponse", 202: "AIAsyncTaskResponse",
                401: "ApiError", 403: "ApiError"})
@permission_required("ai:agentic")
@rate_limit("5 per minute")
@api_exception_handler
def run_agentic_skill(name):
    """执行 agentic 技能：有界 agent loop。

    v3（方案 §Phase 3）：改为 Celery 异步执行。返回 202 + {task_id}，前端通过
    /task/progress/<task_id> SSE 订阅进度，session_id 随 done 事件下发（task 内部
    创建 session，路由层在 202 时拿不到）。

    `AI_ASYNC_ENABLED=0` 时回退同步执行（短期兜底，验证稳定后移除）。
    """
    from app.services.ai.agentic.loader import load_agentic_skill
    from app.services.ai.agentic.runner import AgenticSkillRunner
    from app.services.ai.skills.permission import SkillPermissionDenied

    body = request.get_json(silent=True) or {}
    question = body.get("question", "")
    if not isinstance(question, str):
        return APIResponse.error("question 必须为字符串", status_code=400)
    if len(question) > 2000:
        return APIResponse.error("问题过长，请控制在 2000 字以内")
    try:
        spec, instructions = load_agentic_skill(name, default_agentic_dirs())
    except KeyError:
        return APIResponse.error(f"技能不存在：{name}", status_code=404)
    user_id = get_current_user_id() or 0
    user_perms = get_user_permissions(user_id)
    try:
        from app.services.ai.skills.permission import check_skill_permission
        check_skill_permission(spec, user_perms)
    except SkillPermissionDenied as e:
        return APIResponse.error(
            f"无权执行该技能，缺少权限：{', '.join(sorted(e.missing))}",
            status_code=403,
        )

    import uuid
    from config import Config

    if Config.AI_ASYNC_ENABLED:
        from app.tasks.ai_tasks import run_agentic_diagnosis
        idempotency_key = body.get("idempotency_key")
        task_id = str(uuid.uuid4())
        if idempotency_key:
            from app.services.ai.task_idempotency import try_claim
            first, existing_task_id = try_claim(
                str(idempotency_key), task_id, user_id)
            if not first:
                state = task_state.load(existing_task_id)
                data = {"task_id": existing_task_id, "duplicate": True}
                if state is None:
                    data["finished"] = True
                return APIResponse.success(data=data)
        task = run_agentic_diagnosis.apply_async(
            kwargs={
                "name": name,
                "question": question,
                "user_id": user_id,
                "user_perms": list(user_perms),
            },
            task_id=task_id,
        )
        task_state.save(task.id, {"status": "pending", "progress": 0, "total": 0,
                                  "result": None, "user_id": user_id}, nx=True)
        return APIResponse.success(data={"task_id": task.id}, status_code=202)

    runner = AgenticSkillRunner()
    import time as _time
    from app.services.ai.metrics import record_skill_run
    _t0 = _time.monotonic()
    try:
        answer = runner.run(spec, instructions, question,
                            user_id=user_id, user_permissions=user_perms)
        record_skill_run(skill_name=f"agentic.{name}", status="ok",
                         duration_seconds=_time.monotonic() - _t0)
        session_id = runner.last_session_id
        return APIResponse.success(data={
            "answer": answer,
            "session_id": session_id if isinstance(session_id, int) else None,
        })
    except SkillPermissionDenied as e:
        record_skill_run(skill_name=f"agentic.{name}", status="error",
                         duration_seconds=_time.monotonic() - _t0)
        return APIResponse.error(
            f"无权执行该技能，缺少权限：{', '.join(sorted(e.missing))}",
            status_code=403,
        )
    except Exception:
        record_skill_run(skill_name=f"agentic.{name}", status="error",
                         duration_seconds=_time.monotonic() - _t0)
        raise


@bp.post("/diagnosis/remedial/preview")
@doc(summary="预览 remedial 命令（渲染后不下发）", tags=["AI"],
     responses={200: "AIRemedialPreviewResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@api_exception_handler
def preview_remedial_command():
    """渲染 remedial 命令供执行前确认，不下发到设备。

    同一 command_key 在不同厂商下渲染出的命令与生效条件不同（如思科 TCP
    intercept 依赖 ACL 已存在，H3C 策略需额外 apply）。这类「命令成功但
    不生效」的约束必须在执行前告知运维，执行后再说已无意义。
    """
    from app.services.ai.command_safety import (
        CommandSafetyError, render_remedial_command,
    )
    from app.services.ai.service_factory import get_device_service

    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    command_key = body.get("command_key")
    params = body.get("params", {})

    if not command_key:
        return APIResponse.error("command_key 必填", status_code=400)
    dev_id, err = _parse_device_id(device_id)
    if err:
        return APIResponse.error(err, status_code=400)

    ok, reason = _check_device_access(dev_id)
    if not ok:
        return APIResponse.error(reason, status_code=403)

    device = get_device_service().get_device_by_id(dev_id)
    if not device:
        return APIResponse.error(f"设备 {dev_id} 不存在", status_code=404)

    try:
        rendered = render_remedial_command(
            command_key=command_key,
            brand=device.get("brand") or "",
            params=params,
        )
    except CommandSafetyError as e:
        return APIResponse.error(str(e), status_code=400)

    return APIResponse.success(data={"command_key": command_key, **rendered})


@bp.post("/diagnosis/remedial/execute")
@doc(summary="执行 remedial 修复命令（需人工确认）", tags=["AI"],
     responses={200: "AIRemedialExecuteResponse", 202: "AIAsyncTaskResponse",
                400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:execute")
@rate_limit("5 per minute")
@api_exception_handler
def execute_remedial_command():
    """执行 remedial 命令（前端"确认"按钮触发）。

    设计文档第七节：四层校验 + 执行前置（备份 + 回滚登记）。
    必须传 confirmed=true，后端强制不采信 LLM 输出。
    """
    from app.services.ai.remedial_executor import RemedialExecutor, RemedialExecutionError
    from app.services.ai.service_factory import get_device_service

    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    command_key = body.get("command_key")
    params = body.get("params", {})
    session_id = body.get("session_id")
    confirmed = body.get("confirmed", False)

    if not command_key:
        return APIResponse.error("command_key 必填", status_code=400)
    idempotency_key = body.get("idempotency_key")
    if not idempotency_key:
        return APIResponse.error("idempotency_key 必填", status_code=400)
    if confirmed is not True:
        return APIResponse.error(
            "remedial 命令必须经用户确认后执行（confirmed=true）",
            status_code=400,
        )
    dev_id, err = _parse_device_id(device_id)
    if err:
        return APIResponse.error(err, status_code=400)

    ok, reason = _check_device_access(dev_id, fail_closed=True)
    if not ok:
        return APIResponse.error(reason, status_code=403)

    from app.services.ai.service_factory import get_device_service
    device = get_device_service().get_device_by_id(dev_id)
    if not device:
        return APIResponse.error(f"设备 {dev_id} 不存在", status_code=404)
    brand = device.get("brand") or ""

    from app.services.ai.task_idempotency import (
        try_claim, IdempotencyUnavailableError,
    )
    import os
    import uuid

    task_id = str(uuid.uuid4())
    user_id = get_current_user_id()
    try:
        first, existing_task_id = try_claim(
            str(idempotency_key), task_id, user_id, fail_closed=True)
    except IdempotencyUnavailableError as e:
        logger.warning("remedial 幂等占位拒绝: key=%s %s", idempotency_key, e)
        return APIResponse.error(
            "依赖的 Redis 暂不可用，为防止命令重复下发已拒绝执行，请稍后重试",
            status_code=503,
        )
    if not first:
        state = task_state.load(existing_task_id)
        data = {"task_id": existing_task_id, "duplicate": True}
        if state is None:
            data["finished"] = True
        return APIResponse.success(data=data)

    from config import Config

    if Config.AI_ASYNC_ENABLED:
        from app.tasks.ai_tasks import execute_remedial_task
        execute_remedial_task.apply_async(
            kwargs={
                "task_id": task_id,
                "device_id": dev_id,
                "command_key": command_key,
                "params": params,
                "brand": brand,
                "session_id": session_id,
                "user_id": get_current_user_id(),
                "confirmed": True,
            },
            task_id=task_id,
        )
        task_state.save(task_id, {"status": "pending", "progress": 0, "total": 0,
                                  "result": None, "user_id": get_current_user_id()},
                        nx=True)
        from app.services.audit_service import AuditService
        AuditService().log(
            user_id=get_current_user_id(),
            action="ai.remedial.execute",
            resource="device",
            resource_id=dev_id,
            detail={"command_key": command_key, "params": params, "session_id": session_id, "task_id": task_id, "async": True},
            ip_address=request.remote_addr,
        )
        return APIResponse.success(data={"task_id": task_id}, status_code=202)

    try:
        from app.services.ai.remedial_executor import RemedialExecutor, RemedialExecutionError
        executor = RemedialExecutor()
        result = executor.execute(
            device_id=dev_id,
            command_key=command_key,
            params=params,
            brand=brand,
            session_id=session_id,
            confirmed=confirmed,
        )
        from app.services.audit_service import AuditService
        AuditService().log(
            user_id=get_current_user_id(),
            action="ai.remedial.execute",
            resource="device",
            resource_id=dev_id,
            detail={"command_key": command_key, "params": params, "session_id": session_id, "result": result},
            ip_address=request.remote_addr,
        )
        return APIResponse.success(data=result)
    except RemedialExecutionError as e:
        return APIResponse.error(str(e), status_code=400)


@bp.post("/diagnosis/remedial/rollback")
@doc(summary="手动触发 remedial 命令回滚", tags=["AI"],
     responses={200: "AIRemedialRollbackResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:execute")
@rate_limit("5 per minute")
@api_exception_handler
def rollback_remedial_command():
    """运维手动触发回滚。"""
    from app.services.ai.remedial_executor import RemedialExecutor, RemedialExecutionError
    from app.services.ai.service_factory import get_device_service

    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    rollback_command_key = body.get("rollback_command_key")
    params = body.get("params", {})
    session_id = body.get("session_id")

    if not rollback_command_key:
        return APIResponse.error("rollback_command_key 必填", status_code=400)
    dev_id, err = _parse_device_id(device_id)
    if err:
        return APIResponse.error(err, status_code=400)

    ok, reason = _check_device_access(dev_id, fail_closed=True)
    if not ok:
        return APIResponse.error(reason, status_code=403)

    from app.services.ai.service_factory import get_device_service
    device = get_device_service().get_device_by_id(dev_id)
    if not device:
        return APIResponse.error(f"设备 {dev_id} 不存在", status_code=404)
    brand = device.get("brand") or ""

    try:
        from app.services.ai.remedial_executor import RemedialExecutor, RemedialExecutionError
        executor = RemedialExecutor()
        result = executor.execute_rollback(
            device_id=dev_id,
            rollback_key=rollback_command_key,
            params=params,
            brand=brand,
            session_id=session_id,
        )
        from app.services.audit_service import AuditService
        AuditService().log(
            user_id=get_current_user_id(),
            action="ai.remedial.rollback",
            resource="device",
            resource_id=dev_id,
            detail={"rollback_command_key": rollback_command_key, "params": params, "session_id": session_id, "result": result},
            ip_address=request.remote_addr,
        )
        return APIResponse.success(data=result)
    except RemedialExecutionError as e:
        return APIResponse.error(str(e), status_code=400)


@bp.get("/diagnosis/sessions")
@doc(summary="诊断会话历史", tags=["AI"],
     responses={200: "AIDiagnosisSessionsResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@rate_limit("30 per minute")
@api_exception_handler
def list_diagnosis_sessions():
    """列出诊断会话历史（支持按 device_id 过滤）。"""
    from app.services.ai.diagnosis_session_service import DiagnosisSessionService

    device_id = request.args.get("device_id", type=int)
    limit = min(request.args.get("limit", default=20, type=int), 100)

    sessions = DiagnosisSessionService().list_sessions(
        user_id=get_current_user_id(), device_id=device_id, limit=limit,
    )
    if sessions is None:
        return APIResponse.error(f"无权查看设备 {device_id} 的会话", status_code=403)
    return APIResponse.success(data={"sessions": sessions})


@bp.post("/diagnosis/verify")
@doc(summary="处置后验证（回读指标对比处置前快照）", tags=["AI"],
     responses={200: "AIVerificationResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:execute")
@rate_limit("5 per minute")
@api_exception_handler
def verify_remediation():
    """处置后验证回路：回读指标 + 对比快照 + 输出恢复状态。"""
    from app.services.ai.post_remediation_verifier import PostRemediationVerifier

    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    pre_snapshot = body.get("pre_snapshot", {})
    anomalous_metrics = body.get("anomalous_metrics", [])

    dev_id, err = _parse_device_id(device_id)
    if err:
        return APIResponse.error(err, status_code=400)

    ok, reason = _check_device_access(dev_id)
    if not ok:
        return APIResponse.error(reason, status_code=403)

    from app.services.ai.post_remediation_verifier import PostRemediationVerifier
    verifier = PostRemediationVerifier()
    result = verifier.verify(
        device_id=dev_id,
        pre_snapshot=pre_snapshot,
        anomalous_metrics=anomalous_metrics,
    )
    return APIResponse.success(data=result)


@bp.post("/diagnosis/case-to-rag")
@doc(summary="处置案例回流 RAG 知识库", tags=["AI"],
     responses={200: "AISuccessResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("5 per minute")
@api_exception_handler
def case_to_rag():
    """案例回流 RAG（运维确认处置有效后调用）。"""
    from app.services.ai.post_remediation_verifier import PostRemediationVerifier

    body = request.get_json(silent=True) or {}
    verifier = PostRemediationVerifier()
    success = verifier.case_to_rag(
        symptom=body.get("symptom", ""),
        evidence=body.get("evidence", []),
        root_cause=body.get("root_cause", ""),
        remedial_commands=body.get("remedial_commands", []),
        verified_status=body.get("verified_status", ""),
    )
    return APIResponse.success(data={"success": success})


@bp.get("/diagnosis/rollback-failures")
@doc(summary="回滚失败会话（持续告警）", tags=["AI"],
     responses={200: "AIRollbackFailuresResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@rate_limit("30 per minute")
@api_exception_handler
def list_rollback_failures():
    """Phase 4.4：查询回滚失败会话（供前端持续展示告警，非一次性 toast）。

    设计文档第七节：设备滞留"已变更未回滚"的中间态是最危险的状态，
    不能让运维误以为已恢复。回滚失败必须持续性告警。
    """
    from app.services.ai.diagnosis_session_service import DiagnosisSessionService

    rows = DiagnosisSessionService().list_rollback_failures(limit=50)
    return APIResponse.success(data={
        "rollback_failures": rows,
        "count": len(rows),
    })


@bp.post("/rag/ingest")
@doc(summary="RAG 文档入库（异步）", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AIRagIngestRequest"}}}},
     responses={200: "AIRagIngestResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("5 per minute")
@api_exception_handler
def rag_ingest():
    """RAG 文档入库（I9 修复：改为异步入库，避免阻塞 gunicorn worker）。

    返回 task_id，客户端可通过 /rag/ingest/progress/<task_id> 订阅进度。
    """
    body = request.get_json(silent=True) or {}
    docs_dir = body.get("docs_dir", "docs")
    try:
        safe_dir = _validate_docs_dir(docs_dir)
    except ValueError as e:
        return APIResponse.error(str(e), status_code=400)
    task_id = ingest_async(safe_dir, user_id=get_current_user_id())
    return APIResponse.success(data={"task_id": task_id})



@bp.get("/rag/ingest/progress/<task_id>")
@doc(summary="RAG 入库进度（SSE 流）", tags=["AI"],
     parameters=[{"name": "task_id", "in": "path", "required": True,
                  "schema": {"type": "string"}, "description": "入库任务 ID"}],
     responses={
         200: {"description": "SSE 进度流（text/event-stream）",
               "content": {"text/event-stream": {"schema": {"type": "string"}}}},
         401: "ApiError", 403: "ApiError",
     })
@sse_permission_required("ai:admin")
def rag_ingest_progress(task_id):
    """旧版 RAG 入库进度端点，保留以兼容既有前端调用方。

    M6 修复：实现与通用端点 `/task/progress/<task_id>` 共用同一份实现，避免改
    一处漏一处。差异仅在权限码（ai:admin vs ai:use），由各自的装饰器体现。
    """
    return _progress_stream_response(task_id)



def _check_task_ownership(task_id: str):
    """校验当前用户是否有权订阅该任务的进度流（方案 §6.3）。

    仅校验 `ai:use` 权限码**不够**：任何持该权限的用户凭一个 task_id 就能订阅
    他人任务流，看到设备 SSH 输出等信息。既有 `strip_sensitive_result` 脱敏防的
    是「进 LLM 上下文」，防不住「另一个已登录用户直接订阅」这条路径。

    判定顺序（不可颠倒）：
    1. 本人任务 → 放行；
    2. `ai:admin` → 放行但**审计留痕**（运维排障需要，§10.5 决策）；
    3. 其余（含 user_id 缺失）→ 403。

    `user_id` 缺失一律拒绝（fail-closed）：旧任务 / 降级路径写入的状态没有
    user_id，放行等于绕过校验。**admin 也不豁免**——否则 admin 可枚举任意
    task_id 订阅未知归属的任务。

    Returns:
        None 表示放行；否则返回可直接 return 的 SSE 错误响应。
    """
    from app.services.ai.ai_audit_logger import AIAuditLogger
    from app.services.user_service import user_service
    from app.utils.auth import permission_manager

    state = task_state.load(task_id) or {}
    owner_id = state.get("user_id")
    current_user_id = get_current_user_id()

    if owner_id is not None and owner_id == current_user_id:
        return None  # 本人任务

    if owner_id is not None:
        user = user_service.get_by_id(current_user_id) if current_user_id else None
        if user and permission_manager.check_user_permissions(user, ["ai:admin"]):
            AIAuditLogger().log(
                user_id=current_user_id,
                scenario="task_progress_cross_user_read",
                request={"task_id": task_id},
                response={"owner_id": owner_id},
                duration_ms=0,
                status="ok",
            )
            return None

    return _sse_error_response("无权访问该任务", 403)


def _progress_stream_response(task_id: str):
    """构造进度 SSE 响应（归属校验 + 生成器），供两个进度端点共用。

    M6 修复：两个端点此前各有一份相同的生成器与响应头，改一处会漏另一处。
    抽成内部函数而非让一个端点直接调用另一个——后者会叠加两层
    `sse_permission_required` 装饰器，使旧端点从「需 ai:admin」变成
    「需同时持有 ai:admin 与 ai:use」，属于权限收紧的行为变更。

    Args:
        task_id: 任务 ID。

    Returns:
        Flask Response（SSE 流）或 SSE 格式的错误响应。
    """
    err = _check_task_ownership(task_id)
    if err:
        return err

    def generate():
        for event in get_progress(task_id):   # 复用既有生成器
            yield event
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/task/progress/<task_id>")
@doc(summary="通用 AI 任务进度（SSE 流）", tags=["AI"],
     parameters=[{"name": "task_id", "in": "path", "required": True,
                  "schema": {"type": "string"}, "description": "任务 ID"}],
     responses={
         200: {"description": "SSE 进度流（text/event-stream）",
               "content": {"text/event-stream": {"schema": {"type": "string"}}}},
         401: "ApiError", 403: "ApiError",
     })
@sse_permission_required("ai:use")
def task_progress(task_id):
    """通用 AI 任务进度 SSE 端点（诊断 / RAG 入库 / remedial 执行）。

    鉴权分两层：`sse_permission_required` 校验权限码，
    `_check_task_ownership` 校验**任务归属**（见 §6.3）。
    """
    return _progress_stream_response(task_id)



@bp.get("/rag/status")
@doc(summary="RAG 知识库状态", tags=["AI"],
     responses={200: "AIRagStatusResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@api_exception_handler
def rag_status():
    """知识库状态：文档总数 + 是否可用。"""
    from app.services.ai.rag_store import get_rag_store
    store = get_rag_store()
    return APIResponse.success(data={
        "available": store.available,
        "doc_count": store.count(),
    })


@bp.get("/rag/docs")
@doc(summary="RAG 文档列表", tags=["AI"],
     responses={200: "AIRagDocsListResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@api_exception_handler
def rag_docs_list():
    """列出知识库文档（分页）。"""
    from app.services.ai.rag_store import get_rag_store

    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0

    store = get_rag_store()
    return APIResponse.success(data={"docs": store.list_docs(limit=limit, offset=offset)})


@bp.delete("/rag/docs/<doc_id>")
@doc(summary="删除 RAG 文档", tags=["AI"],
     responses={200: "AIOkResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("20 per minute")
@api_exception_handler
def rag_docs_delete(doc_id):
    """删除指定文档（向量库 + FTS5 索引）。"""
    from app.services.ai.rag_store import get_rag_store
    get_rag_store().delete_doc(doc_id)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.rag.doc_delete",
        resource="ai_rag",
        resource_id=None,
        detail={"doc_id": doc_id},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.post("/rag/reset")
@doc(summary="清空 RAG 知识库", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AIRagResetRequest"}}}},
     responses={200: "AIOkResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("2 per minute")
@api_exception_handler
def rag_reset():
    """清空知识库（删除 collection + FTS5 索引，下次 ingest 自动重建）。

    需请求体 {"confirm": true} 显式确认，避免误删。
    """
    from app.services.ai.rag_store import get_rag_store
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return APIResponse.error("需 confirm=true 显式确认", status_code=400)
    store = get_rag_store()
    store.reset()
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.rag.reset",
        resource="ai_rag",
        resource_id=None,
        detail={"confirm": True},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.post("/rag/qa")
@doc(summary="RAG 知识库问答", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AIRagQaRequest"}}}},
     responses={200: "AIRagQaResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@rate_limit("10 per minute")
@api_exception_handler
def rag_qa():
    """RAG 问答：检索知识库 + 调 LLM 生成答案。

    接通 rag_service.py 预留的 RAGService.ask（此前未接线，M2-M3 死代码）。
    """
    from app.services.ai.rag_service import RAGService
    body = request.get_json(silent=True) or {}
    question = body.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return APIResponse.error("question 必填且为非空字符串", status_code=400)
    if len(question) > 2000:
        return APIResponse.error("问题过长，请控制在 2000 字以内")
    user_id = get_current_user_id() or 0
    service = RAGService()
    answer = service.ask(question, user_id=user_id)
    return APIResponse.success(data={"answer": answer})


@bp.get("/health")
@doc(summary="AI 健康检查", tags=["AI"],
     responses={200: "AIHealthResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:use")
@api_exception_handler
def health():
    return APIResponse.success(data={"configured": create_llm_client().is_configured()})


@bp.get("/skills/<name>")
@doc(summary="获取技能详情", tags=["AI"],
     responses={200: "AISkillDetailResponse", 401: "ApiError", 403: "ApiError", 404: "ApiError"})
@permission_required("ai:use")
@api_exception_handler
def skills_detail(name):
    return APIResponse.success(data={"skill": get_skill(name)})


@bp.put("/skills/<name>")
@doc(summary="启用/禁用技能", tags=["AI"],
     responses={200: "AIOkResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def skills_toggle(name):
    enabled = (request.get_json(silent=True) or {}).get("enabled")
    if not isinstance(enabled, bool):
        return APIResponse.error("enabled 必须为布尔值")
    set_skill_enabled(name, enabled)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.skill.toggle",
        resource="ai_skill",
        resource_id=None,
        detail={"name": name, "enabled": enabled},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.post("/skills/reload")
@doc(summary="热加载技能目录", tags=["AI"],
     responses={200: "AISkillsReloadResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("5 per minute")
@api_exception_handler
def skills_reload():
    count = reload_catalog()
    return APIResponse.success(data={"count": count})


@bp.post("/skills")
@doc(summary="创建技能", tags=["AI"],
     responses={201: "AISkillCreateResponse", 400: "ApiError", 401: "ApiError",
                403: "ApiError", 409: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def skills_create():
    body = request.get_json(silent=True) or {}
    try:
        name = create_skill(body)
    except FileExistsError as e:
        return APIResponse.error(str(e), status_code=409)
    except ValueError as e:
        return APIResponse.error(str(e), status_code=400)
    except SkillValidationError as e:
        return APIResponse.error(f"技能定义非法：{e}", status_code=400)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.skill.create",
        resource="ai_skill",
        resource_id=None,
        detail={"name": name},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True, "name": name}, status_code=201)


@bp.put("/skills/<name>/content")
@doc(summary="编辑技能内容", tags=["AI"],
     responses={200: "AIOkResponse", 400: "ApiError", 401: "ApiError",
                403: "ApiError", 404: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def skills_update_content(name):
    body = request.get_json(silent=True) or {}
    try:
        update_skill_content(name, body)
    except KeyError:
        return APIResponse.error(f"技能不存在：{name}", status_code=404)
    except BuiltinSkillProtected as e:
        return APIResponse.error(str(e), status_code=403)
    except ValueError as e:
        return APIResponse.error(str(e), status_code=400)
    except SkillValidationError as e:
        return APIResponse.error(f"技能定义非法：{e}", status_code=400)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.skill.update",
        resource="ai_skill",
        resource_id=None,
        detail={"name": name},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.delete("/skills/<name>")
@doc(summary="删除技能", tags=["AI"],
     responses={200: "AIOkResponse", 401: "ApiError", 403: "ApiError", 404: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def skills_delete(name):
    try:
        delete_skill(name)
    except KeyError:
        return APIResponse.error(f"技能不存在：{name}", status_code=404)
    except BuiltinSkillProtected as e:
        return APIResponse.error(str(e), status_code=403)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.skill.delete",
        resource="ai_skill",
        resource_id=None,
        detail={"name": name},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.get("/config")
@doc(summary="获取 AI 配置", tags=["AI"],
     responses={200: "AIConfigResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@api_exception_handler
def ai_config_get():
    return APIResponse.success(data=get_config())


@bp.put("/config")
@doc(summary="更新 AI 配置", tags=["AI"],
     request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AIConfigUpdateRequest"}}}},
     responses={200: "AIConfigResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def ai_config_update():
    updates = request.get_json(silent=True) or {}
    try:
        result = update_config(updates)
    except ValueError as e:
        return APIResponse.error(str(e), status_code=400)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.config.update",
        resource="ai_config",
        resource_id=None,
        detail={"fields": list(updates.keys())},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data=result)


@bp.get("/circuit")
@doc(summary="AI 熔断器状态", tags=["AI"],
     responses={200: "AICircuitStatusResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@api_exception_handler
def ai_circuit_status():
    return APIResponse.success(data={"providers": get_circuit_status()})


@bp.post("/circuit/reset")
@doc(summary="重置熔断器", tags=["AI"],
     responses={200: "AIOkResponse", 400: "ApiError", 401: "ApiError", 403: "ApiError", 404: "ApiError"})
@permission_required("ai:admin")
@rate_limit("10 per minute")
@api_exception_handler
def ai_circuit_reset():
    provider = (request.get_json(silent=True) or {}).get("provider")
    if not provider:
        return APIResponse.error("provider 必填")
    try:
        reset_circuit(provider)
    except KeyError as e:
        return APIResponse.error(str(e), status_code=404)
    from app.services.audit_service import AuditService
    AuditService().log(
        user_id=get_current_user_id(),
        action="ai.circuit.reset",
        resource="ai_circuit",
        resource_id=None,
        detail={"provider": provider},
        ip_address=request.remote_addr,
    )
    return APIResponse.success(data={"ok": True})


@bp.get("/metrics")
@doc(summary="AI 运行指标", tags=["AI"],
     responses={200: "AIMetricsResponse", 401: "ApiError", 403: "ApiError"})
@permission_required("ai:admin")
@api_exception_handler
def ai_metrics_get():
    return APIResponse.success(data=get_metrics_summary())
