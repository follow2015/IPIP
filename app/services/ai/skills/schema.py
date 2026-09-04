# -*- coding: utf-8 -*-
"""技能 YAML 校验模型。任何技能必须满足统一 schema，否则拒绝加载。"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ParamSpec(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    description: Optional[str] = None


class StepSpec(BaseModel):
    id: str
    type: Literal["capability", "llm", "route"] = "capability"
    call: str                        # capability 步骤指向能力名；llm/route 步骤指向 prompt 模板名
    args: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[str] = None     # 本步结果写入 steps.<id>.output，供后续引用
    when: Optional[str] = None       # 可选条件，false 则跳过（最小表达式）
    max_tokens: int = 500            # llm/route 步骤单次调用 token 上限
    branches: Dict[str, str] = Field(default_factory=dict)  # route 专用：分支值 → 目标步骤 id


class SkillSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    title: Optional[str] = None
    description: str
    category: str = "general"
    version: int = 1
    max_llm_steps: int = 3           # 单次技能执行 llm/route 步骤总数硬上限
    params: List[ParamSpec] = Field(default_factory=list)
    triggers: List[str] = Field(default_factory=list)
    steps: List[StepSpec]
    return_: Any = Field(None, alias="return")

    @classmethod
    def parse_obj(cls, obj: dict) -> "SkillSpec":
        """v1 兼容别名，校验失败抛 ValidationError（SkillValidationError 别名）。"""
        return cls.model_validate(obj)


SkillValidationError = ValidationError



_PARAM_TYPE_CHECKS = {
    "string": (str,),
    "str": (str,),
    "int": (int,),
    "integer": (int,),
    "number": (int, float),
    "float": (int, float),
    "bool": (bool,),
    "boolean": (bool,),
    "array": (list,),
    "list": (list,),
    "object": (dict,),
    "dict": (dict,),
}


class SkillArgsError(Exception):
    """技能执行参数校验失败。

    B8 修复：args 未通过 ParamSpec 声明校验时抛出，由路由层转为 400。
    """

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def validate_skill_args(skill: SkillSpec, args: Dict[str, Any]) -> None:
    """按技能 params 声明校验执行参数。

    B8 修复：原实现把 args 直接透传给 WorkflowEngine，缺必填项或类型错误
    只能在引擎运行时才暴露（报错不友好，且此时可能已产生部分副作用）。
    此处提前校验并**一次性汇总全部错误**，便于前端表单一次性提示而非逐次试错。

    Args:
        skill: 技能定义。
        args: 待校验的执行参数。

    Raises:
        SkillArgsError: 任一参数不满足声明。
    """
    errors: List[str] = []
    declared = {p.name: p for p in skill.params}

    for name, spec in declared.items():
        if spec.required and (name not in args or args[name] is None):
            errors.append(f"缺少必填参数：{name}")

    for name, value in args.items():
        spec = declared.get(name)
        if spec is None or value is None:
            continue
        expected = _PARAM_TYPE_CHECKS.get(spec.type.lower())
        if expected is None:
            continue  # 未知类型声明不校验，避免误伤
        if expected == (int,) and isinstance(value, bool):
            errors.append(f"参数 {name} 类型错误：期望 {spec.type}，实际 bool")
            continue
        if not isinstance(value, expected):
            errors.append(
                f"参数 {name} 类型错误：期望 {spec.type}，实际 {type(value).__name__}")

    if errors:
        raise SkillArgsError(errors)
