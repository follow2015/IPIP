# -*- coding: utf-8 -*-
"""
邮件渠道

使用 Python 标准库 smtplib + email.mime 发送邮件，无需引入额外依赖。
配置从数据库 mail_settings 表读取。
"""
from app.utils.logging import get_logger
import smtplib
import socket
import threading
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.enums import ChannelType
from app.services.channels.base import PersonalChannel, TransientChannelError
from app.models.notification import Notification, NotificationReceipt
from app.models.user import User

logger = get_logger(__name__)

SEVERITY_LABEL = {
    "info": "通知",
    "warning": "警告",
    "critical": "严重",
}

_DEADLINE_MULTIPLIER = 3


def get_mail_config_from_db() -> dict:
    """从数据库获取 SMTP 配置（单一数据源）。

    供邮件渠道和 API 路由共同调用，避免硬编码字段名重复。

    Returns:
        dict: 包含 server, port, use_tls, use_ssl, username, password, sender, timeout
    """
    from app.models.mail_setting import MailSetting

    raw = MailSetting.get_raw_batch([
        "mail_server", "mail_port", "mail_use_tls", "mail_use_ssl",
        "mail_username", "mail_password", "mail_default_sender", "mail_timeout",
    ])
    return {
        "server": raw.get("mail_server") or "",
        "port": int(raw.get("mail_port") or 587),
        "use_tls": (raw.get("mail_use_tls") or "true").lower() == "true",
        "use_ssl": (raw.get("mail_use_ssl") or "false").lower() == "true",
        "username": raw.get("mail_username") or "",
        "password": raw.get("mail_password") or "",
        "sender": raw.get("mail_default_sender") or "",
        "timeout": int(raw.get("mail_timeout") or 10),
    }


class EmailChannel(PersonalChannel):
    """邮件渠道（SMTP）"""

    def get_channel_name(self) -> str:
        return ChannelType.EMAIL

    def is_available(self, user: User) -> bool:
        """检查邮件渠道是否可用：偏好 + SMTP 配置 + 用户邮箱"""
        if not super().is_available(user):
            return False
        if not user.email:
            return False
        cfg = get_mail_config_from_db()
        return bool(cfg["server"] and cfg["sender"])

    def send(self, notification: Notification, receipt: NotificationReceipt, user: User) -> bool:
        """发送邮件通知"""
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
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            logger.exception("邮件发送失败（瞬时，可重试）: user_id=%s notification_id=%s",
                             user.id, notification.id)
            raise TransientChannelError(f"SMTP 投递瞬时失败: {type(exc).__name__}") from exc
        except Exception:
            logger.exception("邮件发送失败（确定性，不重试）: user_id=%s notification_id=%s",
                             user.id, notification.id)
            return False

    def _build_message(self, notification: Notification, user: User, cfg: dict) -> MIMEMultipart:
        """构建邮件消息"""
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
        """构建纯文本邮件正文"""
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
        """构建 HTML 邮件正文

        notification.title / notification.content 使用 html.escape() 转义，
        防止 HTML 注入（设备名、错误消息等可能包含 <> 字符）。
        """
        severity_colors = {"info": "#1890ff", "warning": "#fa8c16", "critical": "#f5222d"}
        color = severity_colors.get(notification.severity, "#1890ff")
        safe_title = html.escape(notification.title or "")
        safe_content = html.escape(notification.content or "")

        return f"""<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #333;">
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
        """通过 SMTP 发送邮件（B-41：整段会话受总 deadline 保护）

        支持三种连接模式：
        - SSL 直连（use_ssl=True）：端口 465，适用于腾讯企业邮等
        - STARTTLS（use_tls=True）：端口 587，适用于 Gmail / SendGrid 等
        - 明文（两者均为 False）：端口 25，仅限内网测试

        使用上下文管理器确保连接在异常时也能正确关闭。
        """
        self._send_smtp_with_deadline(msg, cfg)

    @staticmethod
    def _send_smtp_with_deadline(msg: MIMEMultipart, cfg: dict) -> None:
        """SMTP 会话 + 总 deadline watchdog（B-41）。

        `timeout` 参数只约束**单次 socket 操作**；watchdog 在总墙钟超过
        `3×timeout` 后强制关闭 socket，把"慢而不死"服务器拖出的 7×timeout
        会话压回 deadline。被中断的会话表现为 SMTPServerDisconnected
        （SMTPException 子类）→ 调用方的**瞬时**分支 → B-39 重试。
        """
        timeout = cfg.get("timeout", 10)

        if cfg.get("use_ssl"):
            smtp_ctx = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=timeout)
        else:
            smtp_ctx = smtplib.SMTP(cfg["server"], cfg["port"], timeout=timeout)

        watchdog = threading.Timer(
            timeout * _DEADLINE_MULTIPLIER, _abort_smtp, args=(smtp_ctx,)
        )
        watchdog.daemon = True  # [WARN] Timer 默认非 daemon：不设的话解释器退出会被它拖住最多一个 deadline
        watchdog.start()
        try:
            with smtp_ctx as server:
                if not cfg.get("use_ssl"):
                    server.ehlo()
                    if cfg.get("use_tls"):
                        server.starttls()
                        server.ehlo()

                if cfg.get("username") and cfg.get("password"):
                    server.login(cfg["username"], cfg["password"])

                server.send_message(msg)
        finally:
            watchdog.cancel()  # 正常完成（或已异常退出）就撤销；到点竞态见 _abort_smtp 注释


def _abort_smtp(smtp: smtplib.SMTP) -> None:
    """watchdog 到点回调：强制关闭当前 socket，解开阻塞中的读。

    两个承重细节：
    ① **必须在触发时读 `smtp.sock`**——`starttls()` 会把 `sock` 替换为新的
       SSLSocket（旧对象被 detach 成 fd=-1，关它等于 no-op）；构造 watchdog
       时抓 socket 的话，TLS 路径下完全失效。
    ② **先 shutdown(SHUT_RDWR) 再 close**——Linux 下只 close() 不保证唤醒
       另一线程里阻塞中的 recv()（fd 已从任务侧解除关联但读仍挂在内核对象上），
       shutdown 才会立刻以 EOF/错误返回 ⇒ smtplib 抛 SMTPServerDisconnected。
    正常完成与 watchdog 到点之间的竞态是良性的：会话已成功时多关一个
    即将关闭的 socket，无副作用（与"响应恰在自然超时后到达"的既有竞态同构）。
    """
    sock = getattr(smtp, "sock", None)
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
