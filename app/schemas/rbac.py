# -*- coding: utf-8 -*-
"""RBAC 请求验证 Schema（T3.1：`rbac.py` 5 个写路由的 request_body 契约）。

字段来源：角色字段取自 handler docstring 明列的 `Request Body` 且与
`rbac_service.create_role/update_role` 的入参一致；列表字段的"必填"来自
handler 内的 `if not isinstance(x, list): 400` 校验——**不按接口名臆测**。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class RBACRoleCreateRequestSchema(Schema):
    """创建角色（`POST /rbac/roles/`）。

    handler docstring：`name`（唯一）、`display_name`、`description`（可选）、
    `status`（可选，默认 0）。重名由服务返回 409。
    """
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    display_name = fields.Str(allow_none=True, validate=validate.Length(max=100))
    description = fields.Str(allow_none=True, validate=validate.Length(max=255))
    status = fields.Int(allow_none=True, load_default=0)
    data_scope = fields.Str(
        load_default="all",
        validate=validate.OneOf(["all", "responsible_person", "room", "custom"]),
    )
    data_scope_config = fields.Dict(allow_none=True, load_default=None)


class RBACRoleUpdateRequestSchema(Schema):
    """更新角色（`PUT /rbac/roles/<int:role_id>/`）——全部字段可选。"""
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=50))
    display_name = fields.Str(allow_none=True, validate=validate.Length(max=100))
    description = fields.Str(allow_none=True, validate=validate.Length(max=255))
    status = fields.Int(allow_none=True)
    data_scope = fields.Str(
        validate=validate.OneOf(["all", "responsible_person", "room", "custom"])
    )
    data_scope_config = fields.Dict(allow_none=True)


class RBACRoleBatchDeleteRequestSchema(Schema):
    """批量删除角色（`POST /rbac/roles/batch-delete`）。

    handler 校验 `isinstance(ids, list)`，故 `ids` 实际必填。
    """
    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True)


class RBACRolePermissionsUpdateRequestSchema(Schema):
    """设置角色权限（`PUT|POST /rbac/roles/<int:role_id>/permissions/`）。

    handler 内变量名为 `permission_codes`，请求体字段名是 `permissions`；
    校验 `isinstance(permission_codes, list)`，故必填。
    """
    class Meta:
        unknown = EXCLUDE

    permissions = fields.List(fields.Str(), required=True)


class RBACUserRolesUpdateRequestSchema(Schema):
    """设置用户角色（`PUT /rbac/users/<int:user_id>/roles/`）。

    handler 校验 `isinstance(role_ids, list)`，故必填。
    """
    class Meta:
        unknown = EXCLUDE

    role_ids = fields.List(fields.Int(), required=True)
