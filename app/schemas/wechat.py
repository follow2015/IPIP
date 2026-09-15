# -*- coding: utf-8 -*-
"""微信相关请求验证 Schema（T3.1：`wechat.py` 写路由的 request_body 契约）。

字段来源：逐条取自各 handler 实际读取的 `data[...]` / `data.get(...)` 与 handler 内
的显式校验（如 `if not scene_id or not openid: 400`）——**不按接口名臆测**。

**5 个写路由中 2 个不读请求体**（`invalidate_cache`：仅管理员权限 + 清缓存；
`generate_qrcode`：无输入、由后端生成 scene_id），故有意不声明 `request_body`。

注意：`/qrcode/confirm` 与 `app/schemas/auth.py` 的 `QRCodeConfirmSchema` **语义不同**——
auth 那个是"用户扫码后在 Web 端确认登录"（`scene_id` + `code`），
wechat 这个是"小程序端回报扫码结果"（`scene_id` + `openid` + `action`），
因此未复用，避免把两套流程混成一个类型。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class WeChatMiniprogramLoginRequestSchema(Schema):
    """小程序登录（`POST /wechat/miniprogram-login`）。

    handler：`if not data or "code" not in data: return 400`，故 `code` 必填。
    """
    class Meta:
        unknown = EXCLUDE

    code = fields.Str(required=True)   # 微信小程序登录凭证（jscode2session 的 js_code）


class WeChatQRCodeConfirmRequestSchema(Schema):
    """小程序回报扫码结果（`POST /wechat/qrcode/confirm`）。

    handler：`if not scene_id or not openid: return 400`，故二者必填；
    `action`（如 confirm/cancel）可选。
    """
    class Meta:
        unknown = EXCLUDE

    scene_id = fields.Str(required=True)
    openid = fields.Str(required=True)
    action = fields.Str(allow_none=True)


class WeChatQRCodeAutoConfirmRequestSchema(Schema):
    """测试用自动确认（`POST /wechat/qrcode/auto-confirm`）。

    ⚠️ 仅在 `development` / `testing` 环境可用（handler 内先判环境）；
    `scene_id` 必填，`test_user_id` 可选。
    """
    class Meta:
        unknown = EXCLUDE

    scene_id = fields.Str(required=True)
    test_user_id = fields.Str(allow_none=True)
