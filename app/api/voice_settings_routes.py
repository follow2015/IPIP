# -*- coding: utf-8 -*-
"""语音通知配置 API 端点（仅管理员）。

仿 mail_settings_routes.py 结构：配置存数据库 voice_settings 表
（key-value 行存储），不修改 .env，避免注入风险。
"""
from flask import Blueprint, request, g

from app.api.base import APIResponse
from app.openapi.doc import doc
from app.utils.auth import login_required
from app.utils.transactional import transactional
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Blueprint("voice_settings", __name__, url_prefix="/api/settings/voice")

_NUMERIC_RANGES = {
    "play_times": (1, 3),
    "volume": (0, 100),
    "speed": (-500, 500),
    "call_timeout": (10, 30),      # 硬上限 30，保 Celery soft_time_limit(45) 余量
    "voice_budget_hour": (1, 5),
    "voice_budget_day": (1, 20),
}


def _require_admin():
    """检查当前用户是否为管理员。"""
    from app.services.user_service import UserService
    from app.persistence.user_repository import UserRepository
    from app.persistence.user_log_repository import UserLogRepository

    user_service = UserService(UserRepository(), UserLogRepository())
    user = user_service.get_by_id(g.current_user["user_id"])
    return bool(user and user.is_admin())


@router.route("", methods=["GET"])
@doc(summary="获取语音通知配置", tags=["语音配置"], responses={200: "VoiceConfig"})
@login_required
def get_voice_config():
    """获取语音通知配置（管理员），敏感字段脱敏。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    from app.models.voice_setting import VoiceSetting

    return APIResponse.success(data=VoiceSetting.get_all())


@router.route("", methods=["PUT"])
@doc(summary="更新语音通知配置", tags=["语音配置"], responses={200: "VoiceConfig"})
@login_required
@transactional
def update_voice_config():
    """更新语音通知配置（管理员）。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = request.get_json() or {}
    if not data:
        return APIResponse.error("请求数据不能为空")

    for key, (low, high) in _NUMERIC_RANGES.items():
        if key in data and data[key] is not None:
            try:
                value = int(data[key])
            except (TypeError, ValueError):
                return APIResponse.error(f"{key} 必须为整数")
            if not low <= value <= high:
                return APIResponse.error(f"{key} 必须在 {low}-{high} 之间")

    if "provider" in data and data["provider"] not in ("aliyun", "tencent"):
        return APIResponse.error("provider 必须为 aliyun 或 tencent")

    if ("callback_verify_mode" in data
            and data["callback_verify_mode"] not in ("ip_only", "signature_and_ip", "off")):
        return APIResponse.error("callback_verify_mode 取值非法")

    try:
        from app.models.voice_setting import VoiceSetting

        updates = {}
        for key in VoiceSetting.ALLOWED_KEYS:
            if key in data and data[key] is not None:
                if isinstance(data[key], bool):
                    updates[key] = "true" if data[key] else "false"
                else:
                    updates[key] = str(data[key])

        VoiceSetting.bulk_set(updates)

        logger.info("语音通知配置已更新: user_id=%s", g.current_user["user_id"])
        return APIResponse.success(data=VoiceSetting.get_all(), message="配置已保存")
    except ValueError as exc:
        return APIResponse.error(str(exc))
    except Exception as exc:
        logger.exception("语音配置更新失败")
        return APIResponse.error(f"配置保存失败: {exc}")


@router.route("/test", methods=["POST"])
@doc(summary="测试语音呼叫", tags=["语音配置"], responses={200: "ApiResponse"})
@login_required
def test_voice_call():
    """向当前管理员的 contact_phone 发起一次测试呼叫（异步全链路）。

    与真实告警共用同一条链路（VoiceChannel → send_voice_call → 回调），
    因此预算流控、模板播报、回调落库、重试取消均可被真实验证——
    这是同步直调 provider 做不到的（绕过 task 管线，回调无处落库）。

    Returns:
        200 {task_id, receipt_id}：前端可提示"已发起，请留意手机"。
        呼叫结果经回调写入 receipt，可在通知中心查看。
    """
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    from app.models.user import User
    from app.models.voice_setting import VoiceSetting
    from app.models.notification import Notification, NotificationReceipt
    from app.services.channels.voice_providers import get_voice_provider
    from app.tasks.voice_tasks import send_voice_call
    from extensions import db

    admin = User.query.get(g.current_user["user_id"])
    if not admin or not admin.contact_phone:
        return APIResponse.error("当前管理员账号未设置手机号，请先在个人资料中填写")

    config = VoiceSetting.get_raw_batch(VoiceSetting.ALLOWED_KEYS)
    if (config.get("enabled") or "false").lower() != "true":
        return APIResponse.error("语音通知未启用，请先开启总开关")

    try:
        provider_name = config.get("provider", "aliyun")
        provider = get_voice_provider(provider_name)
        if not provider.is_config_ready(config):
            return APIResponse.error(
                f"{provider_name} 语音配置不完整，请检查必填项"
            )
    except ValueError as exc:
        return APIResponse.error(str(exc))

    notification = Notification(
        type="voice_test",
        severity="info",
        title="语音配置测试",
        content="这是一条测试语音通知",
        source_module="voice_config",
        target_type="user",
        target_id=str(admin.id),
    )
    db.session.add(notification)
    db.session.flush()

    receipt = NotificationReceipt(
        notification_id=notification.id,
        user_id=admin.id,
        channel_status={"voice": "queued"},
    )
    db.session.add(receipt)
    db.session.commit()

    task = send_voice_call.delay(receipt.id)

    status = dict(receipt.channel_status or {})
    status["voice_task_id"] = task.id
    receipt.channel_status = status
    db.session.add(receipt)
    db.session.commit()

    logger.info("语音测试呼叫已入队: user_id=%s receipt_id=%s task_id=%s",
                admin.id, receipt.id, task.id)
    return APIResponse.success(
        data={"task_id": task.id, "receipt_id": receipt.id},
        message="测试呼叫已发起，请留意手机",
    )


@router.route("/status", methods=["GET"])
@doc(summary="查询语音渠道就绪状态", tags=["语音配置"], responses={200: "VoiceChannelStatus"})
@login_required
def voice_channel_status():
    """返回语音渠道是否就绪及缺失的配置项，便于前端引导配置。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    from app.models.voice_setting import VoiceSetting
    from app.services.channels.voice_providers import get_voice_provider

    config = VoiceSetting.get_raw_batch(VoiceSetting.ALLOWED_KEYS)
    provider_name = config.get("provider", "aliyun")

    enabled = (config.get("enabled") or "false").lower() == "true"
    try:
        provider = get_voice_provider(provider_name)
        ready = provider.is_config_ready(config)
    except Exception as exc:
        return APIResponse.success(data={
            "enabled": enabled, "provider": provider_name,
            "ready": False, "missing": [], "error": str(exc),
        })

    missing = [k for k in _PROVIDER_REQUIRED_KEYS.get(provider_name, [])
               if not config.get(k)]

    return APIResponse.success(data={
        "enabled": enabled,
        "provider": provider_name,
        "ready": bool(enabled and ready),
        "missing": missing,
        "supports_ack": provider.supports_ack(),
    })


_PROVIDER_REQUIRED_KEYS = {
    "aliyun": ["aliyun_access_key_id", "aliyun_access_key_secret", "aliyun_tts_code"],
    "tencent": ["tencent_secret_id", "tencent_secret_key",
                "tencent_app_id", "tencent_template_id"],
}
