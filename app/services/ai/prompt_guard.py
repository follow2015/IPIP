# -*- coding: utf-8 -*-
"""Prompt 字段白名单过滤，防止凭据类字段进入 LLM prompt。

复用项目既有敏感字段约定（参照 app/models/monitor_credential.py:81 的 encrypted_payload 排除）。
"""
import re
from typing import Any, Optional, Set

SENSITIVE_KEYS: Set[str] = {
    "encrypted_payload", "password", "secret", "api_key", "token", "credential",
    "credentials", "credential_links", "switch_credential",
    "community", "snmp_community", "snmp", "ipmi_password", "ipmi",
}


def strip_sensitive_fields(payload: Any, allowlist: Optional[Set[str]] = None) -> Any:
    """递归过滤 dict/list 中敏感字段。

    Args:
        payload: 任意结构（dict/list/标量）
        allowlist: 若提供，则仅保留 allowlist 中的 key（白名单模式）；
                   若为 None，则仅剔除 SENSITIVE_KEYS（黑名单模式）。

    Returns:
        过滤后的同结构副本（不修改原对象）
    """
    if isinstance(payload, dict):
        return {
            k: strip_sensitive_fields(v, allowlist)
            for k, v in payload.items()
            if (allowlist is not None and k in allowlist)
            or (allowlist is None and k not in SENSITIVE_KEYS)
        }
    if isinstance(payload, list):
        return [strip_sensitive_fields(item, allowlist) for item in payload]
    return payload



_INJECTION_PATTERNS = [
    re.compile(r"<\|"),   # OpenAI 特殊 token 标记
    re.compile(r"\{\{"),  # Jinja2 模板
    re.compile(r"\}\}"),
    re.compile(r"\{%"),   # Jinja2 语句
    re.compile(r"%\}"),
]


def sanitize_user_input(text: str) -> str:
    """过滤用户输入中的 Prompt 注入危险字符序列。

    将危险序列替换为空格，避免用户输入逃逸系统 prompt 边界。
    各 AI 服务在拼入 user_prompt 前必须调用此函数。
    """
    if not isinstance(text, str):
        return text
    safe = text
    for pattern in _INJECTION_PATTERNS:
        safe = pattern.sub(" ", safe)
    return safe


def sanitize_args_deep(payload: Any) -> Any:
    """对 dict/list/标量结构深递归净化所有字符串值。

    用于引擎层在 LLM prompt 渲染前统一净化技能参数，与模板级净化互补，
    不依赖每个模板各自记得调用 sanitize_user_input。

    与 strip_sensitive_fields 区别：本函数净化字符串**值**（防 prompt 注入），
    后者剔除敏感**键**（防凭据泄露）。两者可串联使用。
    """
    if isinstance(payload, dict):
        return {k: sanitize_args_deep(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [sanitize_args_deep(item) for item in payload]
    if isinstance(payload, str):
        return sanitize_user_input(payload)
    return payload



_VALUE_REDACT_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(sorted(SENSITIVE_KEYS, key=len, reverse=True)) + r")\b"
    r"\s*[:=]\s*[\"']?([^\s,;&\"'}\]]+)[\"']?"
)
_REDACTED = "***REDACTED***"


def redact_text(text: Any) -> Any:
    """对字符串中敏感键对应的「值」做正则脱敏。

    弥补 strip_sensitive_fields 只过滤**键**的不足：当敏感信息以纯文本形式
    出现在字符串值内部时（如设备命令回显、异常消息、日志中的
    "连接失败 password=abc123"），键级过滤完全失效。本函数补齐该缺口。

    Args:
        text: 待脱敏内容；非字符串原样返回。

    Returns:
        敏感值已被 ***REDACTED*** 替换后的字符串。
    """
    if not isinstance(text, str):
        return text
    return _VALUE_REDACT_PATTERN.sub(lambda m: f"{m.group(1)}={_REDACTED}", text)


def redact_deep(payload: Any) -> Any:
    """深递归对结构内所有字符串值做 redact_text 脱敏。

    用于审计入库等场景：先 strip_sensitive_fields 剔除敏感键，再 redact_deep
    处理残留于字符串值内部的敏感片段，二者互补构成纵深防御。

    Args:
        payload: 任意结构（dict/list/标量）。

    Returns:
        脱敏后的同结构副本。
    """
    if isinstance(payload, dict):
        return {k: redact_deep(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [redact_deep(item) for item in payload]
    return redact_text(payload)


def strip_sensitive_result(result: Any) -> Any:
    """工具结果回传 LLM prompt 前的统一脱敏入口。

    设计文档第十三节第一条要求：正常成功路径（非仅异常分支）的工具调用也走脱敏。
    原实现 runner.py L185 直接 _truncate(f"{call_name}: {result}", ...)，
    SSH 命令回显等字符串结果中的敏感片段（如 password=xxx）原样进入 prompt。

    分派规则：
    - dict/list → strip_sensitive_fields（剔除敏感键）
    - str → redact_text（脱敏字符串值内部的敏感片段）
    - 其它标量 → 原样返回

    与 AIAuditLogger.log 的 redact_deep(strip_sensitive_fields(...)) 串联脱敏互补：
    审计入库做深递归脱敏（更彻底），prompt 回传做浅脱敏（保留结构供 LLM 理解）。

    Args:
        result: 工具调用返回值（任意结构）。

    Returns:
        脱敏后的同结构副本。
    """
    if isinstance(result, (dict, list)):
        return strip_sensitive_fields(result)
    if isinstance(result, str):
        return redact_text(result)
    return result


def truncate_text(text: Any, limit: int) -> str:
    """将任意文本截断到 limit 字符，超出部分以省略标记替代。

    统一供 runner（用户输入、工具结果）与 capability 参数使用，避免各处重复实现
    导致截断策略不一致。头尾各保留一半：工具结果（如设备命令回显）的统计结论
    常出现在尾部，只保留头部会丢失该信息。

    Args:
        text: 待截断内容，非字符串先转字符串。
        limit: 最大保留字符数。

    Returns:
        截断后的字符串；未超限时原样返回。
    """
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    keep = limit // 2
    return f"{s[:keep]}\n...[已截断 {len(s) - limit} 字符]...\n{s[-keep:]}"
