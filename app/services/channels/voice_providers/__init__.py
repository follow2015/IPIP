# -*- coding: utf-8 -*-
"""语音服务商注册表。"""
from .aliyun import AliyunVoiceProvider
from .tencent import TencentVoiceProvider

VOICE_PROVIDERS = {
    "aliyun": AliyunVoiceProvider,
    "tencent": TencentVoiceProvider,
}


def get_voice_provider(name: str):
    """按名称实例化语音服务商，未知名称抛 ValueError。"""
    cls = VOICE_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"未知的语音服务商: {name}")
    return cls()
