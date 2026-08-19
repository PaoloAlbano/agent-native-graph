"""Decorator-based ANA tool metadata.

The executable tool code can live in `agent_native_graph.tools`, while this
module provides the common metadata model used by API discovery and native LLM
tool-call specs.
"""

import inspect
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin, get_type_hints

from agent_native_graph.core.enums import ToolProfile, ToolStatus


@dataclass(frozen=True)
class ToolParam:
    description: str
    required: bool | None = None
    alias: str | None = None
    schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    status: ToolStatus
    profile: ToolProfile
    purpose: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    argument_aliases: dict[str, str] = field(default_factory=dict)
    function: Callable[..., Any] | None = None

    @property
    def when_to_use(self) -> str:
        """Backward-compatible alias used by the public contract."""
        return self.purpose

    def to_contract_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "profile": self.profile.value,
            "purpose": self.purpose,
            "when_to_use": self.when_to_use,
        }

    def to_native_tool_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                    "additionalProperties": False,
                },
            },
        }


_TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def tool(
    *,
    name: str,
    status: ToolStatus,
    profile: ToolProfile,
    purpose: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach ANA metadata to a function and register it as a tool.

    `parameters` is an escape hatch for current dict-shaped tools. For new tools
    with explicit function signatures, omit it and use `Annotated[T,
    ToolParam("...")]` on parameters instead.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        inferred_parameters, inferred_required = _parameters_from_signature(func)
        definition = ToolDefinition(
            name=name,
            status=status,
            profile=profile,
            purpose=purpose,
            description=description,
            parameters=parameters if parameters is not None else inferred_parameters,
            required=required if required is not None else inferred_required,
            argument_aliases=getattr(func, "__tool_argument_aliases__", {}),
            function=func,
        )
        func.__tool__ = definition
        _TOOL_REGISTRY[name] = definition
        return func

    return decorator


def registered_tools() -> dict[str, ToolDefinition]:
    return dict(_TOOL_REGISTRY)


def registered_tool_specs() -> list[dict[str, Any]]:
    return [definition.to_native_tool_spec() for definition in _TOOL_REGISTRY.values()]


def call_registered_tool(backend: Any, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    definition = _TOOL_REGISTRY.get(name)
    if definition is None or definition.function is None:
        return None
    if any(required_name not in args for required_name in definition.required):
        return None
    signature = inspect.signature(definition.function)
    accepted_parameters = {
        parameter_name
        for parameter_name in signature.parameters
        if parameter_name not in {"self", "cls", "backend"}
    }
    accepts_extra_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    kwargs = {
        definition.argument_aliases.get(arg_name, arg_name): value
        for arg_name, value in args.items()
    }
    if not accepts_extra_kwargs:
        kwargs = {
            arg_name: value for arg_name, value in kwargs.items() if arg_name in accepted_parameters
        }
    return definition.function(backend, **kwargs)


def registered_tool_contracts(status: ToolStatus | None = None) -> list[dict[str, str]]:
    definitions = _TOOL_REGISTRY.values()
    if status is not None:
        definitions = [definition for definition in definitions if definition.status == status]
    return [definition.to_contract_dict() for definition in definitions]


def _parameters_from_signature(func: Callable[..., Any]) -> tuple[dict[str, Any], list[str]]:
    signature = inspect.signature(func)
    hints = get_type_hints(func, include_extras=True)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        if name in {"self", "cls", "backend"}:
            continue
        annotation = hints.get(name, parameter.annotation)
        schema, metadata = _schema_from_annotation(annotation)
        parameter_name = metadata.alias if metadata and metadata.alias else name
        if metadata is not None:
            schema["description"] = metadata.description
            is_required = metadata.required
            if metadata.schema:
                schema = {**metadata.schema, "description": metadata.description}
        else:
            is_required = None
        properties[parameter_name] = schema
        if parameter_name != name:
            aliases = getattr(func, "__tool_argument_aliases__", {})
            aliases[parameter_name] = name
            func.__tool_argument_aliases__ = aliases
        if is_required is True or (
            is_required is None and parameter.default is inspect.Parameter.empty
        ):
            required.append(parameter_name)
    return properties, required


def _schema_from_annotation(annotation: Any) -> tuple[dict[str, Any], ToolParam | None]:
    metadata: ToolParam | None = None
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        annotation = args[0]
        metadata = next((item for item in args[1:] if isinstance(item, ToolParam)), None)
    return _json_schema_for_type(annotation), metadata


def _json_schema_for_type(annotation: Any) -> dict[str, Any]:
    if annotation in {inspect.Parameter.empty, Any}:
        return {}
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return {"enum": list(args)}
    if origin in {list, tuple, set}:
        item_schema = _json_schema_for_type(args[0]) if args else {}
        return {"type": "array", "items": item_schema}
    if origin is dict:
        return {"type": "object"}
    if origin is None:
        return _primitive_schema(annotation)
    if origin in {Union, UnionType}:
        return {"anyOf": [_json_schema_for_type(arg) for arg in args if arg is not type(None)]}
    return {}


def _primitive_schema(annotation: Any) -> dict[str, Any]:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }
    json_type = mapping.get(annotation)
    return {"type": json_type} if json_type else {}


def tool_definition_to_dict(definition: ToolDefinition) -> dict[str, Any]:
    data = asdict(definition)
    data["status"] = definition.status.value
    data["profile"] = definition.profile.value
    data.pop("function", None)
    return data
