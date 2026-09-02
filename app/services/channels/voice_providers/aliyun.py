# -*- coding: utf-8 -*-
"""阿里云语音通知 provider（Dyvmsapi/2017-05-25/SingleCallByTts）。

采用 SingleCallByTts（文本转语音模板），与腾讯云 SendTtsVoice 对齐；
模板支持变量，可播报告警标题/级别。
"""
import hashlib
import hmac
import json

from app.utils.logging import get_logger
from .base import VoiceProvider

logger = get_logger(__name__)

VOLUME_RANGE = (0, 100)
SPEED_RANGE = (-500, 500)


class AliyunVoiceProvider(VoiceProvider):
    """阿里云语音通知（SingleCallByTts）。"""

    def make_call(self, callee: str, receipt_id: int, config: dict,
                  template_vars: dict | None = None) -> str:
        from alibabacloud_dyvmsapi20170525.client import Client
        from alibabacloud_dyvmsapi20170525 import models
        from alibabacloud_tea_openapi import models as open_api_models

        openapi_config = open_api_models.Config(
            access_key_id=config["aliyun_access_key_id"],
            access_key_secret=config["aliyun_access_key_secret"],
            endpoint="dyvmsapi.aliyuncs.com",
        )
        client = Client(openapi_config)

        request = models.SingleCallByTtsRequest(
            called_number=callee,
            tts_code=config["aliyun_tts_code"],
            play_times=int(config.get("play_times", 2)),
            volume=self._clamp(int(config.get("volume", 100)), *VOLUME_RANGE),
            speed=self._clamp(int(config.get("speed", 0)), *SPEED_RANGE),
            out_id=self._encode_out_id(receipt_id),  # hex 编码避免 15 字符溢出
        )

        tts_param = self._render_tts_param(config, template_vars)
        if tts_param:
            request.tts_param = tts_param

        if config.get("aliyun_caller_number"):
            request.called_show_number = config["aliyun_caller_number"]

        response = client.single_call_by_tts(request)
        call_id = response.body.call_id
        logger.info("阿里云语音呼叫已发起: receipt_id=%s call_id=%s", receipt_id, call_id)
        return call_id

    @staticmethod
    def _clamp(value: int, low: int, high: int) -> int:
        """夹取到官方合法范围，防止前端/DB 脏值导致 API 拒绝。"""
        return max(low, min(high, value))

    @staticmethod
    def _render_tts_param(config: dict, template_vars: dict | None) -> str | None:
        """渲染 TtsParam：配置里的静态变量映射 + 本次告警的动态变量。"""
        try:
            mapping = json.loads(config.get("aliyun_tts_param") or "{}")
        except (ValueError, TypeError):
            logger.warning("aliyun_tts_param 非合法 JSON，忽略: %s",
                           config.get("aliyun_tts_param"))
            mapping = {}
        if template_vars:
            mapping.update(template_vars)
        return json.dumps(mapping, ensure_ascii=False) if mapping else None

    def supports_ack(self) -> bool:
        return False

    def is_config_ready(self, config: dict) -> bool:
        return bool(config.get("aliyun_access_key_id")
                    and config.get("aliyun_access_key_secret")
                    and config.get("aliyun_tts_code"))

    def callback_response(self) -> tuple[dict, int]:
        """阿里云回执要求返回 {"code": 0, ...}。"""
        return {"code": 0, "msg": "success"}, 200

    def _classify_error(self, exc: Exception) -> Exception:
        """根据阿里云错误码分类异常。"""
        from app.services.channels.voice_providers.errors import (
            TransientVoiceError, PermanentVoiceError,
            ALIYUN_TRANSIENT_CODES, ALIYUN_PERMANENT_CODES,
        )
        code = getattr(exc, "code", "") or str(exc)
        if code in ALIYUN_PERMANENT_CODES:
            return PermanentVoiceError(f"aliyun permanent: {code}")
        if code in ALIYUN_TRANSIENT_CODES:
            return TransientVoiceError(f"aliyun transient: {code}")
        return exc  # 未知，交由 task 默认按瞬态处理

    def parse_callback(self, raw_body: bytes, headers: dict) -> list[dict]:
        """阿里云 HTTP 批量推送的 body 是 JSON 数组，且用 status_code 数字码。

        原按单对象 + state 枚举解析会在 `data.get()` 处 AttributeError，
        导致回调 500、acked/answered 永远写不进数据库。
        """
        from app.services.channels.voice_providers.errors import ALIYUN_STATUS_MAP

        payload = json.loads(raw_body)
        items = payload if isinstance(payload, list) else [payload]  # 兼容单条推送

        events = []
        for item in items:
            receipt_id = None
            out_id = item.get("out_id")
            if out_id:
                try:
                    receipt_id = self._decode_out_id(out_id)
                except (ValueError, TypeError):
                    logger.warning("阿里云回调 out_id 解析失败: out_id=%s", out_id)

            code = str(item.get("status_code", ""))
            event, retryable = ALIYUN_STATUS_MAP.get(code, ("failed:unknown", False))
            events.append({
                "call_id": item.get("call_id", ""),
                "receipt_id": receipt_id,
                "event": event,
                "retryable": retryable,
                "key_press": item.get("dtmf"),
                "raw": item,
            })
        return events

    @staticmethod
    def _encode_out_id(receipt_id: int) -> str:
        """将 receipt_id 编码为 hex 字符串（≤15 字节）。

        超长**禁止截断**：截断后的 hex 仍可被 int(_,16) 解析，但值已错，
        回调会把状态写到**错误的 receipt**（静默串号）。宁可失败不可写错。
        """
        from app.services.channels.voice_providers.errors import PermanentVoiceError

        encoded = f"{receipt_id:X}"  # 大写 hex，无 0x 前缀
        if len(encoded) > 15:
            raise PermanentVoiceError(
                f"receipt_id={receipt_id} hex 编码超 OutId 15 字节限制"
            )
        return encoded

    @staticmethod
    def _decode_out_id(out_id: str) -> int:
        """将 hex OutId 解码回 receipt_id。"""
        return int(out_id, 16)

    def verify_callback_signature(self, raw_body: bytes, headers: dict, config: dict) -> bool:
        """阿里云回调签名校验（HMAC-SHA1）。

        阿里云官方语音回执不携带本项目自定义签名头，本方法仅在厂商支持
        自定义头时才有意义（callback_verify_mode=signature_and_ip）。
        """
        token = config.get("callback_token", "")
        if not token:
            return False
        signature = headers.get("X-Aliyun-Signature", "")
        expected = hmac.new(token.encode(), raw_body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(signature, expected)
