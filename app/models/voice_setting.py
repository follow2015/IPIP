# -*- coding: utf-8 -*-
"""语音通知配置模型（key-value 行存储，与 MailSetting 同模式）。

全局仅一套服务商凭据（阿里云 / 腾讯云二选一）。
安全约定与监控凭据、MailSetting 一致：**`get_all()` 永不含密文**，
内部读取明文一律走 `get_raw()`。
"""
from app.models.base import BaseModel
from extensions import db


class VoiceSetting(BaseModel):
    """语音通知配置（单例，全局一套服务商凭据）。"""

    __tablename__ = "voice_settings"
    __table_args__ = (
        db.UniqueConstraint("key", name="uq_voice_setting_key"),
        {"comment": "语音通知配置表"},
    )

    key = db.Column(db.String(50), nullable=False, comment="配置键")
    value = db.Column(db.String(500), nullable=True, comment="配置值")

    DEFAULTS = {
        "provider": "aliyun",              # aliyun | tencent
        "aliyun_access_key_id": "",
        "aliyun_access_key_secret": "",
        "aliyun_caller_number": "",        # 主叫号码：公共模式（默认）必须留空；填真实报备号=专属模式
        "aliyun_tts_code": "",             # 语音模板 ID（TTS 路线）
        "aliyun_tts_param": "{}",          # 模板变量 JSON（阿里云为 JSON 字符串）
        "tencent_secret_id": "",
        "tencent_secret_key": "",
        "tencent_app_id": "",              # VoiceSdkAppid，必填
        "tencent_template_id": "",         # 语音模板 ID（VMS 不支持文件外呼）
        "play_times": "2",
        "volume": "100",                   # 阿里云 0~100；腾讯云不支持
        "speed": "0",                      # 阿里云 -500~500；腾讯云不支持
        "call_timeout": "30",              # 呼叫超时（秒），硬上限 30（保 task 软超时余量）
        "voice_budget_hour": "",           # 覆盖阿里云 1 小时预算（默认 4）
        "voice_budget_day": "",            # 覆盖阿里云 24 小时预算（默认 18）
        "callback_token": "",              # 回调签名 token
        "callback_verify_mode": "ip_only",  # ip_only | signature_and_ip | off
        "enabled": "false",                # 总开关，默认关闭
    }

    ALLOWED_KEYS = set(DEFAULTS.keys())
    SENSITIVE_KEYS = {
        "aliyun_access_key_secret",
        "tencent_secret_key",
        "callback_token",
    }

    @classmethod
    def get(cls, key: str) -> str | None:
        """获取配置值（不脱敏，与 get_raw 同义，保留别名以兼容直觉命名）。"""
        return cls.get_raw(key)

    @classmethod
    def get_raw(cls, key: str) -> str | None:
        """获取原始配置值（不脱敏），供 provider / channel 内部使用。"""
        row = cls.query.filter_by(key=key).first()
        if row:
            return row.value
        return cls.DEFAULTS.get(key)

    @classmethod
    def get_all(cls) -> dict:
        """获取全部配置，敏感字段脱敏为 `****` 并附加 `<key>_set` 标志。

        数值字段转成 int、enabled 转成 bool，便于前端表单直接绑定。
        """
        result = dict(cls.DEFAULTS)
        for row in cls.query.all():
            result[row.key] = row.value

        result["play_times"] = int(result.get("play_times") or 2)
        result["volume"] = int(result.get("volume") or 100)
        result["speed"] = int(result.get("speed") or 0)
        result["call_timeout"] = int(result.get("call_timeout") or 30)
        result["voice_budget_hour"] = int(result.get("voice_budget_hour") or 0)
        result["voice_budget_day"] = int(result.get("voice_budget_day") or 0)
        result["enabled"] = (result.get("enabled") or "false").lower() == "true"

        for k in cls.SENSITIVE_KEYS:
            result[f"{k}_set"] = bool(result.get(k))
            if result.get(k):
                result[k] = "****"
        return result

    @classmethod
    def set(cls, key: str, value: str) -> None:
        """写入单个配置值（仅白名单内的 key）。"""
        if key not in cls.ALLOWED_KEYS:
            raise ValueError(f"不允许的配置键: {key}")
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))

    @classmethod
    def bulk_set(cls, updates: dict) -> None:
        """批量写入配置值；`****` 占位符视为"未修改"并跳过。"""
        for key, value in updates.items():
            if key in cls.ALLOWED_KEYS and value is not None:
                if value == "****":
                    continue
                cls.set(key, str(value))
