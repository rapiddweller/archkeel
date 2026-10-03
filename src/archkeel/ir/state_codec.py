# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict immutable state-fact wire conversion; event order is preserved."""

from __future__ import annotations

from typing import Literal, TypeVar, assert_never

from .facts import JsonValue, RecordData
from .state_facts import (
    ArgumentPass,
    Assignment,
    AttributeAccess,
    ClassStateFacts,
    FieldState,
    FunctionStateTrace,
    StateEvent,
    StateFacts,
    StateParameter,
)

_Choice = TypeVar("_Choice", bound=str)
_BINDINGS: tuple[Literal["UNKNOWN", "non_reassignable"], ...] = ("UNKNOWN", "non_reassignable")
_REFERENTS: tuple[Literal["UNKNOWN", "mutable_container"], ...] = ("UNKNOWN", "mutable_container")
_MUTABILITY: tuple[Literal["UNKNOWN", "object_immutable", "mutable"], ...] = (
    "UNKNOWN",
    "object_immutable",
    "mutable",
)
_PROPERTIES: tuple[Literal["available", "unavailable"], ...] = ("available", "unavailable")
_ACCESSES: tuple[Literal["read", "write", "mutation"], ...] = ("read", "write", "mutation")


def _data(**values: JsonValue) -> RecordData:
    return RecordData(tuple(values.items()))


def _event_data(event: StateEvent) -> RecordData:
    if isinstance(event, Assignment):
        return _data(
            kind="assignment",
            targets=event.targets,
            constructor=event.constructor,
            annotation=event.annotation,
            alias=event.alias,
        )
    if isinstance(event, AttributeAccess):
        return _data(
            kind="attribute",
            binding=event.binding,
            path=event.path,
            access=event.access,
            evidence_id=event.evidence_id,
        )
    if isinstance(event, ArgumentPass):
        return _data(
            kind="pass", binding=event.binding, target=event.target, evidence_id=event.evidence_id
        )
    assert_never(event)


def state_data(facts: StateFacts) -> RecordData:
    return _data(
        classes=tuple(
            _data(
                qualified_name=item.qualified_name,
                module=item.module,
                frozen=item.frozen,
                protocol=item.protocol,
                methods=item.methods,
                evidence_ids=item.evidence_ids,
                fields=tuple(
                    _data(
                        name=field.name,
                        annotation=field.annotation,
                        binding=field.binding,
                        referent_mutability=field.referent_mutability,
                        mutability=field.mutability,
                        evidence_ids=field.evidence_ids,
                        property_assignment=field.property_assignment,
                    )
                    for field in item.fields
                ),
            )
            for item in facts.classes
        ),
        functions=tuple(
            _data(
                scope=item.scope,
                module=item.module,
                class_owner=item.class_owner,
                receiver=item.receiver,
                parameters=tuple(
                    _data(name=parameter.name, annotation=parameter.annotation)
                    for parameter in item.parameters
                ),
                events=tuple(_event_data(event) for event in item.events),
            )
            for item in facts.functions
        ),
    )


def _fields(value: JsonValue, names: set[str], label: str) -> dict[str, JsonValue]:
    if not isinstance(value, RecordData) or {key for key, _ in value.entries} != names:
        raise ValueError(f"{label} fields mismatch")
    return dict(value.entries)


def _text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def _optional_text(value: JsonValue, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _items(value: JsonValue, label: str) -> tuple[JsonValue, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an array")
    return value


def _names(value: JsonValue, label: str) -> tuple[str, ...]:
    return tuple(_text(item, label) for item in _items(value, label))


def _bool(value: JsonValue, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _choice(value: JsonValue, choices: tuple[_Choice, ...], label: str) -> _Choice:
    for choice in choices:
        if value == choice:
            return choice
    raise ValueError(f"invalid {label}")


def _parse_field(value: JsonValue) -> FieldState:
    raw = _fields(
        value,
        {
            "name",
            "annotation",
            "binding",
            "referent_mutability",
            "mutability",
            "evidence_ids",
            "property_assignment",
        },
        "state field",
    )
    return FieldState(
        _text(raw["name"], "field.name"),
        _optional_text(raw["annotation"], "field.annotation"),
        _choice(raw["binding"], _BINDINGS, "field.binding"),
        _choice(raw["referent_mutability"], _REFERENTS, "field.referent_mutability"),
        _choice(raw["mutability"], _MUTABILITY, "field.mutability"),
        _names(raw["evidence_ids"], "field.evidence_ids"),
        None
        if raw["property_assignment"] is None
        else _choice(raw["property_assignment"], _PROPERTIES, "field.property_assignment"),
    )


def _parse_class(value: JsonValue) -> ClassStateFacts:
    raw = _fields(
        value,
        {"qualified_name", "module", "frozen", "protocol", "fields", "methods", "evidence_ids"},
        "state class",
    )
    fields = tuple(_parse_field(field) for field in _items(raw["fields"], "class.fields"))
    if len({field.name for field in fields}) != len(fields):
        raise ValueError("duplicate state field")
    return ClassStateFacts(
        _text(raw["qualified_name"], "class.qualified_name"),
        _text(raw["module"], "class.module"),
        _bool(raw["frozen"], "class.frozen"),
        _bool(raw["protocol"], "class.protocol"),
        fields,
        _names(raw["methods"], "class.methods"),
        _names(raw["evidence_ids"], "class.evidence_ids"),
    )


def _parse_parameter(value: JsonValue) -> StateParameter:
    raw = _fields(value, {"name", "annotation"}, "state parameter")
    return StateParameter(
        _text(raw["name"], "parameter.name"),
        _optional_text(raw["annotation"], "parameter.annotation"),
    )


def _parse_event(value: JsonValue) -> StateEvent:
    if not isinstance(value, RecordData):
        raise ValueError("state event must be an object")
    kind = value.get("kind")
    if kind == "assignment":
        raw = _fields(
            value, {"kind", "targets", "constructor", "annotation", "alias"}, "assignment event"
        )
        return Assignment(
            _names(raw["targets"], "assignment.targets"),
            _optional_text(raw["constructor"], "assignment.constructor"),
            _optional_text(raw["annotation"], "assignment.annotation"),
            _optional_text(raw["alias"], "assignment.alias"),
        )
    if kind == "attribute":
        raw = _fields(
            value, {"kind", "binding", "path", "access", "evidence_id"}, "attribute event"
        )
        path = _names(raw["path"], "attribute.path")
        access = _choice(raw["access"], _ACCESSES, "attribute.access")
        if not path or (access == "mutation" and len(path) < 2):
            raise ValueError("attribute event path is empty or has no mutation receiver")
        return AttributeAccess(
            _text(raw["binding"], "attribute.binding"),
            path,
            access,
            _text(raw["evidence_id"], "attribute.evidence_id"),
        )
    if kind == "pass":
        raw = _fields(value, {"kind", "binding", "target", "evidence_id"}, "pass event")
        return ArgumentPass(
            _text(raw["binding"], "pass.binding"),
            _text(raw["target"], "pass.target"),
            _text(raw["evidence_id"], "pass.evidence_id"),
        )
    raise ValueError("unknown state event kind")


def _parse_function(value: JsonValue) -> FunctionStateTrace:
    raw = _fields(
        value,
        {"scope", "module", "class_owner", "receiver", "parameters", "events"},
        "state function",
    )
    return FunctionStateTrace(
        _text(raw["scope"], "function.scope"),
        _text(raw["module"], "function.module"),
        _optional_text(raw["class_owner"], "function.class_owner"),
        _optional_text(raw["receiver"], "function.receiver"),
        tuple(
            _parse_parameter(parameter)
            for parameter in _items(raw["parameters"], "function.parameters")
        ),
        tuple(_parse_event(event) for event in _items(raw["events"], "function.events")),
    )


def parse_state_data(data: RecordData) -> StateFacts:
    raw = _fields(data, {"classes", "functions"}, "state")
    classes = tuple(_parse_class(item) for item in _items(raw["classes"], "state.classes"))
    if len({item.qualified_name for item in classes}) != len(classes):
        raise ValueError("duplicate state class")
    return StateFacts(
        classes,
        tuple(_parse_function(item) for item in _items(raw["functions"], "state.functions")),
    )
