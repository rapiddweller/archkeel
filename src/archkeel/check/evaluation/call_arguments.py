# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind admitted call actuals to one observed Python signature."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Final

from archkeel.ir.facts import CallArgument, CallArgumentKind, RecordData

_PARAMETER_KINDS: Final = {
    "positional_only": inspect.Parameter.POSITIONAL_ONLY,
    "positional": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "varargs": inspect.Parameter.VAR_POSITIONAL,
    "keyword_only": inspect.Parameter.KEYWORD_ONLY,
    "kwargs": inspect.Parameter.VAR_KEYWORD,
}
_DEFAULT: Final = object()


@dataclass(frozen=True, slots=True)
class BoundCallArguments:
    """Call-order indexes grouped under the formal parameter that receives each actual."""

    by_parameter: tuple[tuple[str, tuple[int, ...]], ...]


def bind_call_arguments(
    signature: RecordData,
    arguments: tuple[CallArgument, ...],
    *,
    bound_receiver: bool,
) -> BoundCallArguments | None:
    """Bind only explicit, non-spread actuals; unknown or invalid shapes have no proof."""
    raw_parameters = signature.get("parameters")
    if not isinstance(raw_parameters, tuple):
        return None
    parameters: list[inspect.Parameter] = []
    for raw in raw_parameters:
        if not isinstance(raw, RecordData):
            return None
        name, kind, default_known = (
            raw.get("name"),
            raw.get("kind"),
            raw.get("default_known"),
        )
        if not isinstance(name, str) or not isinstance(kind, str) or default_known is not True:
            return None
        parameter_kind = _PARAMETER_KINDS.get(kind)
        if parameter_kind is None:
            return None
        if kind == "varargs" and name.startswith("*"):
            name = name[1:]
        elif kind == "kwargs" and name.startswith("**"):
            name = name[2:]
        default = _DEFAULT if raw.get("default") is not None else inspect.Parameter.empty
        try:
            parameters.append(inspect.Parameter(name, parameter_kind, default=default))
        except (TypeError, ValueError):
            return None

    if bound_receiver:
        receiver = signature.get("receiver_parameter")
        if (
            not isinstance(receiver, str)
            or not parameters
            or parameters[0].name != receiver
            or parameters[0].kind
            not in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ):
            return None
        parameters.pop(0)

    if any(
        argument.kind in {CallArgumentKind.STARRED_POSITIONAL, CallArgumentKind.STARRED_KEYWORD}
        for argument in arguments
    ):
        return None

    keyword_names = {
        argument.keyword
        for argument in arguments
        if argument.kind is CallArgumentKind.KEYWORD and argument.keyword is not None
    }
    if len(keyword_names) != sum(
        argument.kind is CallArgumentKind.KEYWORD for argument in arguments
    ):
        return None
    has_kwargs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    renamed: dict[str, str] = {}
    if has_kwargs:
        used_names = {parameter.name for parameter in parameters} | keyword_names
        for index, parameter in enumerate(parameters):
            if (
                parameter.kind is inspect.Parameter.POSITIONAL_ONLY
                and parameter.name in keyword_names
            ):
                name = f"__archkeel_posonly_{index}"
                while name in used_names:
                    name += "_"
                used_names.add(name)
                renamed[name] = parameter.name
                parameters[index] = parameter.replace(name=name)

    try:
        signature_value = inspect.Signature(parameters)
        actual_values = tuple(range(len(arguments)))
        positional = [
            actual_values[index]
            for index, argument in enumerate(arguments)
            if argument.kind is CallArgumentKind.POSITIONAL
        ]
        keywords = {
            argument.keyword: actual_values[index]
            for index, argument in enumerate(arguments)
            if argument.kind is CallArgumentKind.KEYWORD and argument.keyword is not None
        }
        bound = signature_value.bind(*positional, **keywords)
    except (TypeError, ValueError):
        return None

    grouped: list[tuple[str, tuple[int, ...]]] = []
    for parameter in parameters:
        formal_name = renamed.get(parameter.name, parameter.name)
        actual = bound.arguments.get(parameter.name)
        indexes: tuple[int, ...]
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            indexes = tuple(item for item in actual or () if isinstance(item, int))
        elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
            indexes = tuple(item for item in (actual or {}).values() if isinstance(item, int))
        elif isinstance(actual, int):
            indexes = (actual,)
        else:
            indexes = ()
        if indexes:
            grouped.append((formal_name, indexes))
    return BoundCallArguments(tuple(grouped))
