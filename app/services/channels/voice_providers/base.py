# -*- coding: utf-8 -*-
"""语音服务商抽象基类。

抽象基线取"两家交集"：项目同时保留阿里云与腾讯云互为容灾，
故签名不含任一家的独有参数（如阿里云的语音文件外呼、主叫号码、音量/语速），
厂商差异通过 `supports_ack()` 等能力查询在 VoiceChannel 层降级处理。
"""
from abc import ABC, abstractmethod


class VoiceProvider(ABC):
    """语音服务商统一抽象。"""

    @abstractmethod
    def make_call(self, callee: str, receipt_id: int, config: dict,
                  template_vars: dict | None = None) -> str:
        """发起呼叫，返回 call_id。失败抛异常。"""
        ...

    @abstractmethod
    def parse_callback(self, raw_body: bytes, headers: dict) -> list[dict]:
        """解析回调，返回事件列表。

        阿里云 HTTP 批量推送 body 是数组，一次请求可能携带多条回执；
        腾讯云同一次通话会分推 status / key / failure 三类回调。

        Returns:
            [{
                "call_id": str,
                "receipt_id": int | None,   # 阿里云从 out_id；腾讯云为 None（靠 callid 反查）
                "event": "delivered|acked|answered|no_answer|failed:xxx",
                "retryable": bool,          # 由 provider 按错误码判定
                "key_press": str | None,
                "raw": dict,
            }, ...]
        """
        ...

    @abstractmethod
    def callback_response(self) -> tuple[dict, int]:
        """厂商要求的回调响应体 + HTTP 状态码。"""
        ...

    @abstractmethod
    def verify_callback_signature(self, raw_body: bytes, headers: dict, config: dict) -> bool:
        """校验回调签名。

        两家官方回调均不携带本项目自定义签名头，本方法仅在厂商支持自定义头
        时才有意义（callback_verify_mode=signature_and_ip）。
        """
        ...

    def supports_ack(self) -> bool:
        """是否支持按键确认。默认 False，腾讯云覆写为 True。"""
        return False

    def is_config_ready(self, config: dict) -> bool:
        """provider 必需配置是否齐备。"""
        raise NotImplementedError
