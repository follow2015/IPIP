# -*- coding: utf-8 -*-
"""通用工单 · 内核与插件（架构见 ``docs/design/IPIP-通用工单系统-插件化架构设计.md``）。

**当前状态（2026-10-10 评审标注）：半落地。**
模型（``app/models/ticket.py``，迁移 0027）+ 状态机 + 插件骨架已合入，
但 **API 路由、权限位、前端均未接入**——``app/api/`` 下没有任何工单路由，
``seed_rbac`` 没有 ticket 权限点。在此标注前本包无任何 TODO/flag，消费者
容易误以为可接。接入时必须：新增路由蓝图 + 权限位分级下发 + 前端页面，
缺一不可上线。

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
