"""Small standard-library model layer used by Harness stage definitions."""

from __future__ import annotations

import json
import types
from dataclasses import MISSING, asdict, field, fields, is_dataclass
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


def schema_field(*, description: str, title: str = "", default: Any = MISSING, default_factory: Any = MISSING):
    metadata = {"description": description, "title": title}
    kwargs: dict[str, Any] = {"metadata": metadata}
    if default is not MISSING:
        kwargs["default"] = default
    if default_factory is not MISSING:
        kwargs["default_factory"] = default_factory
    return field(**kwargs)


class SchemaModel:
    """Dataclass mixin with the small Pydantic-like interface stages need."""

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        return model_json_schema(cls)

    @classmethod
    def model_validate_json(cls, value: str) -> "SchemaModel":
        return model_validate_json(cls, value)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SchemaModel":
        return model_from_dict(cls, value)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def model_json_schema(model_type: type[Any]) -> dict[str, Any]:
    """Build JSON Schema from a standard dataclass model."""
    return _model_schema(model_type)


def model_validate_json(model_type: type[Any], value: str) -> Any:
    return model_from_dict(model_type, json.loads(value))


def model_from_dict(model_type: type[Any], value: dict[str, Any]) -> Any:
    if not is_dataclass(model_type):
        raise TypeError(f"{model_type.__name__} 必须是 dataclass")
    if not isinstance(value, dict):
        raise ValueError(f"{model_type.__name__} 必须由 JSON object 构造")
    hints = get_type_hints(model_type)
    expected = {item.name for item in fields(model_type)}
    extra = set(value) - expected
    if extra:
        raise ValueError(f"{model_type.__name__} 包含未知字段：{', '.join(sorted(extra))}")
    converted = {
        item.name: _convert_value(value[item.name], hints[item.name], item.name)
        for item in fields(model_type)
        if item.name in value
    }
    return model_type(**converted)


def _model_schema(model_type: type[Any]) -> dict[str, Any]:
    if not is_dataclass(model_type):
        raise TypeError(f"{model_type.__name__} 必须是 dataclass")
    hints = get_type_hints(model_type)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for item in fields(model_type):
        schema = _type_schema(hints[item.name])
        if item.metadata.get("description"):
            schema["description"] = item.metadata["description"]
        if item.metadata.get("title"):
            schema["title"] = item.metadata["title"]
        properties[item.name] = schema
        if item.default is MISSING and item.default_factory is MISSING:
            required.append(item.name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _type_schema(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return {"type": "string", "enum": list(args)}
    if origin is list:
        return {"type": "array", "items": _type_schema(args[0])}
    if origin in (Union, types.UnionType):
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1 and len(non_none) != len(args):
            return {"anyOf": [_type_schema(non_none[0]), {"type": "null"}]}
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _model_schema(annotation)
    primitive = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if annotation in primitive:
        return {"type": primitive[annotation]}
    raise TypeError(f"不支持的 Schema 类型：{annotation!r}")


def _convert_value(value: Any, annotation: Any, path: str) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        if not isinstance(value, list):
            raise ValueError(f"{path} 必须是数组")
        return [_convert_value(item, args[0], f"{path}[]") for item in value]
    if origin is Literal:
        if value not in args:
            raise ValueError(f"{path} 必须是 {args} 之一")
        return value
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            return _convert_value(value, non_none[0], path)
    if isinstance(annotation, type) and is_dataclass(annotation):
        return model_from_dict(annotation, value)
    if annotation in (str, int, float, bool) and not isinstance(value, annotation):
        raise ValueError(f"{path} 类型不正确")
    return value
