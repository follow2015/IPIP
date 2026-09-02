# -*- coding: utf-8 -*-
"""腾讯云语音消息 provider（vms/v20200902 SendTtsVoice）。

腾讯云 VMS 不支持语音文件外呼，仅支持模板 TTS，故统一走 SendTtsVoice。
"""
import hashlib
import hmac
import json

from app.utils.logging import get_logger
from .base import VoiceProvider

logger = get_logger(__name__)

_TERMINAL_FAILURE_REASONS = ("空号", "停机", "关机", "号码不存在", "用户拒接")


class TencentVoiceProvider(VoiceProvider):
    """腾讯云语音消息（VMS v20200902 SendTtsVoice）。"""

    def make_call(self, callee: str, receipt_id: int, config: dict,
                  template_vars: dict | None = None) -> str:
        if not config.get("tencent_app_id"):
            from app.services.channels.voice_providers.errors import PermanentVoiceError

            raise PermanentVoiceError("tencent_app_id (VoiceSdkAppid) 未配置，腾讯云 VMS 必填")

        from tencentcloud.common import credential
        from tencentcloud.vms.v20200902.vms_client import VmsClient
        from tencentcloud.vms.v20200902 import models

        cred = credential.Credential(
            config["tencent_secret_id"],
            config["tencent_secret_key"],
        )
        client = VmsClient(cred, "ap-guangzhou")

        request = models.SendTtsVoiceRequest()
        request.VoiceSdkAppid = config["tencent_app_id"]
        request.TemplateId = config["tencent_template_id"]
        request.CalledNumber = self._to_e164(callee)     # 必须为 e.164
        request.TemplateParamSet = self._render_params(template_vars)
        request.PlayTimes = int(config.get("play_times", 2))
        request.SessionContext = str(receipt_id)

        response = client.SendTtsVoice(request)
        call_id = response.SendStatus.CallId
        logger.info("腾讯云语音呼叫已发起: receipt_id=%s call_id=%s", receipt_id, call_id)
        return call_id

    @staticmethod
    def _to_e164(phone: str) -> str:
        """转 e.164（+8613711112222）。contact_phone 通常存本地格式。

        注意：非 + 开头一律按中国大陆号码补 +86；海外号码场景需先在
        contact_phone 中显式带国家码（+ 前缀原样透传）。
        """
        p = (phone or "").strip().replace(" ", "").replace("-", "")
        return p if p.startswith("+") else f"+86{p}"

    @staticmethod
    def _render_params(template_vars: dict | None) -> list[str]:
        """腾讯云模板参数为字符串数组（无参时传空数组）。"""
        if not template_vars:
            return []
        return [str(v) for v in template_vars.values()]

    def supports_ack(self) -> bool:
        return True

    def is_config_ready(self, config: dict) -> bool:
        return bool(config.get("tencent_secret_id")
                    and config.get("tencent_secret_key")
                    and config.get("tencent_app_id")
                    and config.get("tencent_template_id"))

    def callback_response(self) -> tuple[dict, int]:
        """腾讯云要求返回 {"result": 0, "errmsg": "OK"}。"""
        return {"result": 0, "errmsg": "OK"}, 200

    def _classify_error(self, exc: Exception) -> Exception:
        """根据腾讯云错误码分类异常。"""
        from app.services.channels.voice_providers.errors import (
            TransientVoiceError, PermanentVoiceError,
            TENCENT_TRANSIENT_CODES, TENCENT_PERMANENT_CODES,
        )
        code = getattr(exc, "code", "") or str(exc)
        if code in TENCENT_PERMANENT_CODES:
            return PermanentVoiceError(f"tencent permanent: {code}")
        if code in TENCENT_TRANSIENT_CODES:
            return TransientVoiceError(f"tencent transient: {code}")
        return exc  # 未知，交由 task 默认按瞬态处理

    def parse_callback(self, raw_body: bytes, headers: dict) -> list[dict]:
        """腾讯云回调有三类独立推送，共用同一 callid，均不带 sessionContext。

        - 状态  ：voiceprompt_callback（result: "0"=接听 / "1"=未接听 / "2"=呼叫异常）
        - 按键  ：voicekey_callback（keypress）
        - 失败原因：voice_failure_callback（failure_code / failure_reason）

        receipt_id 一律留空，由回调路由用 Redis 反向索引 voice:call:{call_id} 反查。
        """
        data = json.loads(raw_body)

        if "voiceprompt_callback" in data:
            c = data["voiceprompt_callback"]
            result = str(c.get("result", ""))
            event, retryable = {
                "0": ("answered", False),           # 用户正常接听
                "1": ("no_answer", False),          # 未接听（重打只是骚扰）
                "2": ("failed:call_error", True),   # 呼叫异常（平台侧，可重试）
            }.get(result, ("failed:unknown", False))
            return [{
                "call_id": c.get("callid", ""),
                "receipt_id": None,
                "event": event,
                "retryable": retryable,
                "key_press": None,
                "raw": data,
            }]

        if "voicekey_callback" in data:
            c = data["voicekey_callback"]
            return [{
                "call_id": c.get("callid", ""),
                "receipt_id": None,
                "event": "acked",
                "retryable": False,
                "key_press": c.get("keypress"),
                "raw": data,
            }]

        if "voice_failure_callback" in data:
            c = data["voice_failure_callback"]
            reason = (c.get("failure_reason") or "").strip()
            if any(t in reason for t in _TERMINAL_FAILURE_REASONS):
                retryable = False
            else:
                retryable = True
            return [{
                "call_id": c.get("callid", ""),
                "receipt_id": None,
                "event": "failed:" + (reason or "unknown"),
                "retryable": retryable,
                "key_press": None,
                "raw": data,
            }]

        logger.warning("腾讯云回调无法识别的结构: %s", list(data.keys()))
        return []

    def verify_callback_signature(self, raw_body: bytes, headers: dict, config: dict) -> bool:
        """腾讯云回调签名校验（HMAC-SHA256）。

        VMS 语音通知回调不携带签名头，本方法仅在自定义头场景下有意义。
        """
        token = config.get("callback_token", "")
        if not token:
            return False
        signature = headers.get("X-TC-Signature", "")
        expected = hmac.new(token.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
