# -*- coding: utf-8 -*-
"""
邮件渠道

使用 Python 标准库 smtplib + email.mime 发送邮件，无需引入额外依赖。
配置从数据库 mail_settings 表读取。
"""
from app.utils.logging import get_logger
import smtplib
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.enums import ChannelType
from app.services.channels.base import PersonalChannel
from app.models.notification import Notification, NotificationReceipt
from app.models.user import User

logger = get_logger(__name__)

SEVERITY_LABEL = {
    "info": "通知",
    "warning": "警告",
    "critical": "严重",
}


def get_mail_config_from_db() -> dict:
    from app.models.mail_setting import MailSetting

    return {
        "server": MailSetting.get_raw("mail_server") or "",
        "port": int(MailSetting.get_raw("mail_port") or 587),
        "use_tls": (MailSetting.get_raw("mail_use_tls") or "true").lower() == "true",
        "use_ssl": (MailSetting.get_raw("mail_use_ssl") or "false").lower() == "true",
        "username": MailSetting.get_raw("mail_username") or "",
        "password": MailSetting.get_raw("mail_password") or "",
        "sender": MailSetting.get_raw("mail_default_sender") or "",
        "timeout": int(MailSetting.get_raw("mail_timeout") or 10),
    }


class EmailChannel(PersonalChannel):

    def get_channel_name(self) -> str:
        return ChannelType.EMAIL

    def is_available(self, user: User) -> bool:
        if not super().is_available(user):
            return False
        if not user.email:
            return False
        cfg = get_mail_config_from_db()
        return bool(cfg["server"] and cfg["sender"])

    def send(self, notification: Notification, receipt: NotificationReceipt, user: User) -> bool:
        cfg = get_mail_config_from_db()
        if not cfg["server"] or not cfg["sender"]:
            logger.warning("邮件渠道未配置 SMTP，跳过发送")
            return False
        if not user.email:
            logger.debug("用户 %s 无邮箱地址，跳过邮件发送", user.id)
            return False

        try:
            msg = self._build_message(notification, user, cfg)
            self._send_smtp(msg, cfg)
            logger.info("邮件通知已发送: user_id=%s notification_id=%s", user.id, notification.id)
            return True
        except Exception:
            logger.exception("邮件发送失败: user_id=%s notification_id=%s", user.id, notification.id)
            return False

    def _build_message(self, notification: Notification, user: User, cfg: dict) -> MIMEMultipart:
        severity_label = SEVERITY_LABEL.get(notification.severity, notification.severity)
        subject = f"[{severity_label}] {notification.title}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["sender"]
        msg["To"] = user.email

        text_body = self._build_text_body(notification, severity_label)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))

        html_body = self._build_html_body(notification, severity_label)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        return msg

    def _build_text_body(self, notification: Notification, severity_label: str) -> str:
        lines = [
            f"{notification.title}",
            f"",
            f"{notification.content or ''}",
            f"",
            f"---",
            f"类型: {notification.type}",
            f"严重程度: {severity_label}",
            f"来源: {notification.source_module or '系统'}",
            f"时间: {notification.created_at.isoformat() if notification.created_at else ''}",
        ]
        return "\n".join(lines)

    def _build_html_body(self, notification: Notification, severity_label: str) -> str:
        severity_colors = {"info": "#1890ff", "warning": "#fa8c16", "critical": "#f5222d"}
        color = severity_colors.get(notification.severity, "#1890ff")
        safe_title = html.escape(notification.title or "")
        safe_content = html.escape(notification.content or "")

        return f"""<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:
<div style="max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="border-left: 4px solid {color}; padding: 12px 16px; background: #fafafa; border-radius: 4px;">
    <h3 style="margin: 0 0 8px 0; color: {color};">{severity_label}: {safe_title}</h3>
    <p style="margin: 0; line-height: 1.6;">{safe_content}</p>
  </div>
  <div style="margin-top: 16px; padding: 8px 16px; color: #999; font-size: 12px;">
    类型: {html.escape(notification.type or '')} &nbsp;|&nbsp; 来源: {html.escape(notification.source_module or '系统')} &nbsp;|&nbsp;
    时间: {notification.created_at.isoformat() if notification.created_at else ''}
  </div>
</div>
</body></html>"""

    def _send_smtp(self, msg: MIMEMultipart, cfg: dict) -> None:
        timeout = cfg.get("timeout", 10)

        if cfg.get("use_ssl"):
            smtp_ctx = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=timeout)
        else:
            smtp_ctx = smtplib.SMTP(cfg["server"], cfg["port"], timeout=timeout)

        with smtp_ctx as server:
            if not cfg.get("use_ssl"):
                server.ehlo()
                if cfg.get("use_tls"):
                    server.starttls()
                    server.ehlo()

            if cfg.get("username") and cfg.get("password"):
                server.login(cfg["username"], cfg["password"])

            server.send_message(msg)
