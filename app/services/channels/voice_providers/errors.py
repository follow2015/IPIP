# -*- coding: utf-8 -*-
"""语音呼叫异常类与错误码分类。

独立模块，供 voice_tasks.py 和 voice_providers/*.py 共同导入，
避免 voice_tasks ↔ voice_providers 循环导入。
"""
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TransientVoiceError(Exception):
    """语音呼叫瞬态错误（可安全重试）。

    触发场景：网络超时、ServiceUnavailable、Throttling 限流。
    """


class PermanentVoiceError(Exception):
    """语音呼叫永久错误（不重试，直接标记失败）。

    触发场景：语音码不存在、号码未报备、被叫号码格式错误、联系人无电话号码。
    若统一用 TransientVoiceError，永久性错误会重试 3 次纯属浪费，
    还会导致告警延迟与额度浪费。
    """


ALIYUN_TRANSIENT_CODES = {
    "isv.BUSINESS_LIMIT_CONTROL",    # 限流
    "isv.RAM_PERMISSION_DENY",       # RAM 权限临时拒绝
    "System.Busy",                   # 系统繁忙
    "UnknownError",                  # 网关未知错误
}

ALIYUN_PERMANENT_CODES = {
    "isv.VOICE_CODE_NOT_EXIST",      # 语音码不存在
    "isv.MOBILE_NUMBER_ILLEGAL",     # 被叫号码非法
    "isv.CALLED_NUMBER_ERROR",       # 被叫号码错误
    "isv.VOICE_FILE_NOT_EXIST",      # 语音文件不存在
    "isv.AMOUNT_NOT_ENOUGH",         # 余额不足（重试也无用）
    "InvalidVoiceCode",
    "InvalidCaller",
}

TENCENT_PERMANENT_CODES = {
    "FailedOperation.ContainSensitiveWord",
    "FailedOperation.TemplateIncorrectOrUnapproved",
    "InvalidParameterValue.ContentLengthLimit",
    "FailedOperation.InvalidJsonParameters",
    "FailedOperation.JsonParseFail",
    "FailedOperation.FailResolvePacket",
    "FailedOperation.InvalidParameters",
    "InvalidParameterValue.CalledNumberVerifyFail",
    "InvalidParameterValue.SdkAppidNotExist",
    "UnauthorizedOperation.SdkAppidIsDisabled",
    "UnauthorizedOperation.VoiceSdkAppidVerifyFail",
    "UnauthorizedOperation.ServiceSuspendDueToArrears",
    "FailedOperation.PhonenumberUnappliedOrExpired",
    "FailedOperation.InsufficientBalanceInVoicePackage",
    "UnsupportedOperation",
}

TENCENT_TRANSIENT_CODES = {
    "LimitExceeded.DeliveryFrequencyLimit",
    "RequestLimitExceeded",
    "FailedOperation.AccessUpstreamTimeout",
    "InternalError.AccessUpstreamTimeout",
    "InternalError.RequestTimeException",
    "InternalError.RestApiInterfaceNotExist",
    "InternalError.SigVerificationFail",
    "InternalError.SsoSendRecvFail",
    "InternalError.UpstreamError",
    "FailedOperation.ParametersOtherError",
}


ALIYUN_STATUS_MAP = {
    "200000": ("delivered", False),    # 用户听完语音
    "200001": ("answered", False),     # 提前挂机（未听完，但已触达）
    "200002": ("no_answer", True),     # 占线
    "200003": ("no_answer", False),    # 收到呼叫未接听（人主动不接）
    "200004": ("failed:permanent:invalid_number", False),
    "200005": ("no_answer", True),     # 无法接通（含公共号被标记骚扰拦截）
    "200006": ("failed:permanent:bad_tts", False),
    "200007": ("no_answer", False),    # 不在服务区
    "200008": ("answered", False),     # 获取按键超时
    "200010": ("no_answer", False),    # 关机
    "200011": ("failed:permanent:out_of_service", False),
    "200118": ("failed:quiet_hours", False),   # 供应商时间段限呼（重试无意义）
    "200119": ("failed:throttled", True),      # 供应商超频限呼
    "200121": ("failed:throttled", True),      # 呼叫超并发
    "200130": ("failed:unknown", False),
    "400": ("failed:transient", True),         # 网元繁忙
    "500": ("failed:transient", True),         # 运营商错误
    "476": ("failed:permanent", False),        # 号码强制回收
    "999999": ("failed:transient", True),      # 系统错误
}
