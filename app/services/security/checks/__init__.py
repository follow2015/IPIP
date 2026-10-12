# -*- coding: utf-8 -*-
"""内置检测器集合（导入即注册；每个模块底部调用 `register_check`）。

Task 6 只建**注册通道**：`scanner` 在模块尾部导入本包，使 `iter_checks()` 拿到全部
内置规则 —— 缺这一步 = 生产路径上零检测器注册（静默失效，且没有任何报错）。

具体检测器按 Task 7–10 各自落地到本目录（`password_checks.py`、`snmp_checks.py`、
`system_checks.py` 等），每新增一个只要 import 进这里即可，无需改动 `scanner`。

**为什么现在这个文件是空的**：先钉住通道，让后续任务只做"新增文件 + 在这里 import"
两件事，避免每个任务都去动巡检引擎。

—— 2026-10-11 Task 7 起不再是空的：下面每 import 一个模块，就多一批内置检测器。
"""


from app.services.security.checks import password_checks  # noqa: F401
from app.services.security.checks import snmp_checks  # noqa: F401
from app.services.security.checks import login_checks  # noqa: F401
from app.services.security.checks import audit_checks  # noqa: F401
