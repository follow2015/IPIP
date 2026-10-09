# -*- coding: utf-8 -*-
"""通用工单 · 内核与插件（架构见 ``docs/design/IPIP-通用工单系统-插件化架构设计.md``）。

分层约定（**单向依赖，反向即违规**，由契约测试守住）：

```
plugins/  ──依赖──>  plugin_base / plugin_capability  ──依赖──>  app.core.enums
    ↑                        ↑
    │                        │
   内核不得 import plugins    内核可以直接用 base（它不认识任何具体插件）
```

``plugins/`` 下的每个文件是一个外部平台（企微 / 飞书 / 钉钉 / 第三方 ITSM / 告警源）。
新增平台的最小动作见 ``plugins/__init__.py``。
"""
