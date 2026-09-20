# -*- coding: utf-8 -*-
"""语音通知渠道。

同步路径只做「落库 + 入队」，实际呼叫由 `app.tasks.voice_tasks` 异步完成，
结果由 `app/api/voice_callback_routes` 回调写入 receipt.channel_status。
"""
from app.core.enums import ChannelType
from app.models.user import User
from app.models.notification import Notification, NotificationReceipt
from app.services.channels.base import PersonalChannel
from app.utils.logging import get_logger

logger = get_logger(__name__)


def get_voice_config_from_db() -> dict:
    """从数据库获取语音配置（不脱敏），供 channel/task 内部使用。"""
    from app.models.voice_setting import VoiceSetting
    return VoiceSetting.get_raw_batch(VoiceSetting.ALLOWED_KEYS)


class VoiceChannel(PersonalChannel):
    """语音通知渠道。"""

    def get_channel_name(self) -> str:
        return ChannelType.VOICE

    def supports_ack(self) -> bool:
        """按键确认能力取决于当前服务商，代理到 provider 查询。

        阿里云 SingleCallByTts 无 ASR 入参拿不到按键（False）；
        腾讯云 voicekey_callback 提供 keypress（True）。
        供通知详情页等上层判断"是否展示等待按键确认"。
        """
        try:
            config = get_voice_config_from_db()
            from app.services.channels.voice_providers import get_voice_provider
            return get_voice_provider(config.get("provider", "aliyun")).supports_ack()
        except Exception:
            logger.exception("语音按键能力查询失败")
            return False

    def is_available(self, user: User) -> bool:
        """语音默认关闭（与其他渠道默认开启相反），必须显式开启。

        条件：偏好显式开启 + 用户有 contact_phone + 总开关开 + provider 配置就绪。
        """
        user_id = getattr(user, "id", None)

        prefs = user.notification_prefs or {}
        if not prefs.get("channels", {}).get(ChannelType.VOICE, False):
            logger.debug("语音渠道不可用: user_id=%s reason=pref_disabled", user_id)
            return False
        if not user.contact_phone:
            logger.debug("语音渠道不可用: user_id=%s reason=no_contact_phone", user_id)
            return False

        try:
            config = get_voice_config_from_db()
            if (config.get("enabled") or "false").lower() != "true":
                logger.debug(
                    "语音渠道不可用: user_id=%s reason=global_switch_off", user_id,
                )
                return False

            from app.services.channels.voice_providers import get_voice_provider

            provider = get_voice_provider(config.get("provider", "aliyun"))
            ready = provider.is_config_ready(config)
            if not ready:
                logger.warning(
                    "语音渠道不可用: user_id=%s reason=provider_unconfigured "
                    "provider=%s（检查语音配置页凭据是否完整）",
                    user_id, config.get("provider", "aliyun"),
                )
            return ready
        except Exception:
            logger.exception("语音渠道可用性校验失败")
            return False

    def send(self, notification: Notification,
             receipt: NotificationReceipt, user: User) -> bool:
        """投递语音呼叫到 Celery task（非阻塞）。

        Returns:
            True 表示已成功入队（**非呼叫成功**）；实际结果由回调写入。

        事务安全（A-P1-3 起更新：worker 由"整条通知一次提交"改为**逐用户提交**）：

        * 本方法**仍必须先 commit 再 delay**。入 broker 与落库是两种介质：若反过来先 delay、
          指望 worker 那次提交来落库，一旦该提交失败/回滚，task 已在 broker 里而 DB 无记录
          ⇒ task 读到空状态、**重复呼叫**。先 commit 才能保证
          "broker 里有 task ⇔ DB 里有 receipt 的 queued 状态"这一前提成立。
        * worker 侧的 `status.update(dict(receipt.channel_status or {}))` 仍必须是**合并而非覆盖**
          —— 因为本方法会先写入 `voice` 状态与 `voice_task_id`（回调路由靠 task_id 取消待重试任务）。
        * 那个"合并会读到最新值"依赖 session 默认的 `expire_on_commit=True`：worker**自己**的逐用户
          提交用 `_commit_without_expire` 显式绕开过期（否则每用户重读，会破坏 A-P1-2 的取数判据），
          而**本方法内部的 commit 仍走默认过期**，故 worker 合并时仍能读到本次写入。
          ⇒ **不要**为省一次重读而全局关闭 `expire_on_commit`：那会让 worker 用内存旧值覆盖
          回调刚落库的语音终态（answered 等），退回"重复外呼并烧预算"的老问题。
        """
        from app.tasks.voice_tasks import send_voice_call
        from extensions import db
        from sqlalchemy.orm.attributes import flag_modified

        try:
            status = dict(receipt.channel_status or {})
            status["voice"] = "queued"
            receipt.channel_status = status
            flag_modified(receipt, "channel_status")
            db.session.commit()

            task = send_voice_call.delay(receipt.id)

            status["voice_task_id"] = task.id
            receipt.channel_status = status
            flag_modified(receipt, "channel_status")
            db.session.commit()
            return True
        except Exception as exc:
            logger.exception("语音呼叫入队失败 receipt_id=%s", receipt.id)
            try:
                status = dict(receipt.channel_status or {})
                status["voice"] = f"failed:{type(exc).__name__}"
                receipt.channel_status = status
                flag_modified(receipt, "channel_status")
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.error(
                    "语音失败状态回写也失败 receipt_id=%s（状态丢失，"
                    "回调可能无法定位此 receipt）", receipt.id,
                )
            return False
