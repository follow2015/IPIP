# -*- coding: utf-8 -*-
"""
邮件服务器配置 API 端点

提供 SMTP 配置的读取、更新和连通性测试功能，仅管理员可访问。
配置存储在数据库 mail_settings 表中（key-value 行存储），
不修改 .env 文件，避免注入风险和并发问题。
"""
from app.utils.logging import get_logger
import smtplib
from email.mime.text import MIMEText

from flask import Blueprint, request, g

from app.api.base import APIResponse
from app.openapi.doc import doc
from app.utils.auth import login_required
from app.utils.transactional import transactional

logger = get_logger(__name__)

router = Blueprint("mail_settings", __name__, url_prefix="/api/settings/mail")


def _require_admin():
    """检查当前用户是否为管理员"""
    from app.services.user_service import UserService
    from app.persistence.user_repository import UserRepository
    from app.persistence.user_log_repository import UserLogRepository
    user_service = UserService(UserRepository(), UserLogRepository())
    user = user_service.get_by_id(g.current_user["user_id"])
    if not user or not user.is_admin():
        return False
    return True


def _get_db_config() -> dict:
    """从数据库读取邮件配置（密码脱敏），供 API 返回"""
    from app.models.mail_setting import MailSetting
    return MailSetting.get_all()


def _get_smtp_params(data: dict | None = None) -> dict:
    """组装 SMTP 连接参数，优先使用请求体中的临时值，否则从数据库读取。

    用于测试端点：允许用未保存的配置测试连通性。
    """
    from app.services.channels.email import get_mail_config_from_db

    db_values = get_mail_config_from_db()

    if not data:
        return db_values

    if data.get("mail_server"):
        db_values["server"] = data["mail_server"]
    if data.get("mail_port"):
        db_values["port"] = int(data["mail_port"])
    if "mail_use_tls" in data:
        db_values["use_tls"] = bool(data["mail_use_tls"])
    if "mail_use_ssl" in data:
        db_values["use_ssl"] = bool(data["mail_use_ssl"])
    if data.get("mail_username"):
        db_values["username"] = data["mail_username"]
    if data.get("mail_password") and data["mail_password"] != "****":
        db_values["password"] = data["mail_password"]
    if data.get("mail_default_sender"):
        db_values["sender"] = data["mail_default_sender"]
    if data.get("mail_timeout"):
        db_values["timeout"] = int(data["mail_timeout"])

    return db_values


@router.route("", methods=["GET"])
@doc(summary="获取邮件服务器配置", tags=["邮件配置"], responses={200: "ApiResponse"})
@login_required
def get_mail_config():
    """获取当前邮件服务器配置（管理员），密码脱敏。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    return APIResponse.success(data=_get_db_config())


@router.route("", methods=["PUT"])
@doc(summary="更新邮件服务器配置", tags=["邮件配置"], responses={200: "ApiResponse"})
@login_required
@transactional
def update_mail_config():
    """更新邮件服务器配置（管理员），写入数据库。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空")

    if "mail_port" in data:
        port = data["mail_port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            return APIResponse.error("端口号必须在 1-65535 之间")

    if "mail_timeout" in data:
        timeout = data["mail_timeout"]
        if not isinstance(timeout, int) or timeout < 1 or timeout > 120:
            return APIResponse.error("超时时间必须在 1-120 秒之间")

    use_tls = data.get("mail_use_tls")
    use_ssl = data.get("mail_use_ssl")
    if use_tls and use_ssl:
        return APIResponse.error("STARTTLS 和 SSL 不能同时启用，请选择其中一种")

    try:
        from app.models.mail_setting import MailSetting

        updates = {}
        for key in MailSetting.ALLOWED_KEYS:
            if key in data and data[key] is not None:
                if key == "mail_password" and data[key] == "****":
                    continue
                if key in ("mail_use_tls", "mail_use_ssl"):
                    updates[key] = "true" if data[key] else "false"
                else:
                    updates[key] = str(data[key])

        MailSetting.bulk_set(updates)

        logger.info("邮件服务器配置已更新: user_id=%s", g.current_user["user_id"])
        return APIResponse.success(data=_get_db_config(), message="配置已保存")
    except ValueError as e:
        return APIResponse.error(str(e))
    except Exception as e:
        logger.exception("邮件配置更新失败")
        return APIResponse.error(f"配置保存失败: {e}")


@router.route("", methods=["DELETE"])
@doc(summary="删除邮件服务器配置", tags=["邮件配置"], responses={200: "ApiResponse"})
@login_required
@transactional
def delete_mail_config():
    """删除邮件服务器配置（管理员），清空数据库中的所有配置项。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    try:
        from app.models.mail_setting import MailSetting
        MailSetting.delete_all()

        logger.info("邮件服务器配置已删除: user_id=%s", g.current_user["user_id"])
        return APIResponse.success(message="配置已删除")
    except Exception as e:
        logger.exception("邮件配置删除失败")
        return APIResponse.error(f"删除失败: {e}")


@router.route("/test", methods=["POST"])
@doc(summary="测试邮件服务器连通性", tags=["邮件配置"], responses={200: "ApiResponse"})
@login_required
def test_mail_config():
    """测试邮件服务器连通性（管理员），发送一封测试邮件。

    请求体参数：
    - recipient: 收件人邮箱地址（必填）
    - 其余字段用于测试未保存的配置（可选）
    """
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = request.get_json(silent=True) or {}
    recipient = data.get("recipient", "").strip()
    if not recipient:
        return APIResponse.error("请输入收件人邮箱地址")

    params = _get_smtp_params(data)

    if not params["server"] or not params["sender"]:
        return APIResponse.error("邮件服务器未配置，请先填写 SMTP 服务器地址和发件人")

    try:
        msg = MIMEText("这是一封来自 IPIP 管理系统的邮件服务器连通性测试邮件，无需回复。", "plain", "utf-8")
        msg["Subject"] = "[IPIP] 邮件服务器测试"
        msg["From"] = params["sender"]
        msg["To"] = recipient

        logger.info(
            "邮件测试连接: server=%s port=%s ssl=%s tls=%s",
            params["server"], params["port"], params["use_ssl"], params["use_tls"],
        )

        if params["use_ssl"]:
            server = smtplib.SMTP_SSL(params["server"], params["port"], timeout=params["timeout"])
        else:
            server = smtplib.SMTP(params["server"], params["port"], timeout=params["timeout"])
            server.ehlo()
            if params["use_tls"]:
                server.starttls()
                server.ehlo()

        if params["username"] and params["password"]:
            server.login(params["username"], params["password"])

        server.send_message(msg)
        server.quit()

        logger.info("邮件测试成功: user_id=%s target=%s", g.current_user["user_id"], recipient)
        return APIResponse.success(message=f"测试邮件已发送至 {recipient}")
    except smtplib.SMTPAuthenticationError:
        return APIResponse.error("SMTP 认证失败，请检查用户名和密码")
    except smtplib.SMTPConnectError as e:
        return APIResponse.error(f"SMTP 连接失败（{params['server']}:{params['port']}）: {e}")
    except smtplib.SMTPException as e:
        return APIResponse.error(f"SMTP 错误（{params['server']}:{params['port']} SSL={params['use_ssl']} TLS={params['use_tls']}）: {e}")
    except TimeoutError:
        return APIResponse.error(f"连接超时（{params['server']}:{params['port']}），请检查服务器地址和端口")
    except ConnectionResetError:
        return APIResponse.error(
            f"连接被重置（{params['server']}:{params['port']}），"
            f"可能是加密方式与端口不匹配：SSL 用端口 465，STARTTLS 用端口 587"
        )
    except Exception as e:
        logger.exception("邮件测试失败")
        return APIResponse.error(f"测试失败（{params['server']}:{params['port']}）: {e}")
