# -*- coding: utf-8 -*-
"""能力包：import 本包即注册所有内置能力。

关键修复：原 builtin.py 从未被任何模块 import，导致 register_capability
装饰器不执行、_CAPS 始终为空，所有技能 YAML 运行时报
"capability not registered"。此处显式 import builtin，确保能力注册表被填充。
"""
from . import builtin  # noqa: F401  (side-effect: 注册内置能力)
from . import diagnostic  # noqa: F401  (side-effect: 注册诊断类能力 device.live_inspection/ssh.diagnostic_show)
from .registry import get_capability, register_capability

__all__ = ["builtin", "diagnostic", "get_capability", "register_capability"]
