# -*- coding: utf-8 -*-
"""多通道设备信息采集 · 通道层。

模型一句话：把「采集什么」（``Capability``）与「怎么采」（``Channel``）解耦，
使单点采集失败可以**按能力**降级（例如 SNMP 采端口 + CLI 采 MAC）。

依赖边界（``docs/adr/adr-004-多通道采集通道层独立成层.md``，CI 由
``tests/test_collector_boundary_guard.py`` 强制）：

    app/services/collector/  ── 单向，仅 L1 原语 ──▶  app/services/monitoring/**
                             ◀── 禁止 ───

即「复用轮子，不共用方向盘」：SNMP 会话与 v3 凭据构造等底层原语可复用，
监控侧的注册表 / worker / scheduler / credential_service 一律不得引用。

本包 ``__init__`` 刻意**不导出任何符号**，理由有二：

1. 包导入不应产生超出 ``app.services.__init__`` 的额外副作用；契约层的导入期
   校验（T0.4 的 ``__init_subclass__``）要求导入面尽量窄、尽量可预测。
2. 子模块的导出面由各模块自己声明（如 ``from app.services.collector.facts
   import CollectedFacts``），避免在包这一层再造一份"总清单"式的第二真相源。
"""
