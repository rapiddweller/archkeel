# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check a core frame against the one JSON schema of the frame (AD-596).

The core generates `schema/archkeel-core-frame-1.schema.json` from the Rust types that write the
frame; the shell keeps no list of keys of its own. This reader needs the standard library only: it
supports the keywords that the generated schema uses and refuses a keyword that it does not know,
so a schema change that the shell cannot check fails closed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Final

from .core_json import CoreError

_SCHEMA_NAME: Final = "archkeel-core-frame-1.schema.json"
_REFUSAL_NAME: Final = "archkeel-core-refusal-1.schema.json"
# Keywords that describe and never constrain.
_NOTES: Final = frozenset({"$schema", "title", "description", "format", "$defs"})
_CHECKS: Final = frozenset(
    {
        "$ref",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "enum",
        "const",
        "anyOf",
        "oneOf",
    }
)


def schema_file(name: str) -> Path:
    """The schema file of this install: the wheel copy, or the checkout copy."""
    package = Path(__file__).resolve().parents[1]
    for found in (package / "schema" / name, package.parents[1] / "schema" / name):
        if found.is_file():
            return found
    raise CoreError(f"the schema {name} is missing from this install")


@cache
def _schema(name: str) -> Mapping[str, object]:
    """One generated schema of the core, read once."""
    try:
        value = json.loads(schema_file(name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CoreError(f"the schema {name} cannot be read: {error}") from error
    if not isinstance(value, dict):
        raise CoreError(f"the schema {name} is not an object")
    return value


def check_frame(frame: object) -> None:
    """Refuse a frame that the schema does not accept, with the first path that differs."""
    _check(frame, _SCHEMA_NAME, "frame")


def check_refusal(refusal: object) -> None:
    """Refuse a stderr refusal that the refusal schema does not accept."""
    _check(refusal, _REFUSAL_NAME, "refusal")


def _check(value: object, name: str, what: str) -> None:
    root = _schema(name)
    problem = _problem(value, root, root, what)
    if problem is not None:
        raise CoreError(f"the core {what} breaks its schema: {problem}")


def _kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _is(value: object, name: object) -> bool:
    if name == "number":
        return _kind(value) in {"integer", "number"}
    return _kind(value) == name


def _resolve(root: Mapping[str, object], ref: object) -> object:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise CoreError(f"the frame schema has a reference that the shell cannot follow: {ref!r}")
    found = root.get("$defs")
    name = ref.removeprefix("#/$defs/")
    if not isinstance(found, dict) or name not in found:
        raise CoreError(f"the frame schema has no definition {name}")
    return found[name]


def _problem(value: object, schema: object, root: Mapping[str, object], where: str) -> str | None:
    """The first place where `value` breaks `schema`, or `None`."""
    if schema is True:
        return None
    if not isinstance(schema, dict):
        raise CoreError(f"the frame schema has a part that is no schema, at {where}")
    if unknown := sorted(schema.keys() - _CHECKS - _NOTES):
        raise CoreError(f"the frame schema has a keyword that the shell cannot check: {unknown}")
    if "$ref" in schema:
        found = _problem(value, _resolve(root, schema["$ref"]), root, where)
        if found is not None:
            return found
    for key in ("type", "const", "enum", "minimum", "maximum"):
        if key in schema and (found := _scalar(key, schema[key], value, where)) is not None:
            return found
    for key in ("anyOf", "oneOf"):
        if key in schema and (found := _choice(key, schema[key], value, root, where)) is not None:
            return found
    if isinstance(value, dict):
        return _object(value, schema, root, where)
    if isinstance(value, list):
        return _array(value, schema, root, where)
    return None


def _scalar(key: str, rule: object, value: object, where: str) -> str | None:
    if key == "type":
        names = rule if isinstance(rule, list) else [rule]
        return None if any(_is(value, name) for name in names) else f"{where} is not {rule}"
    if key == "const":
        return None if value == rule and _kind(value) == _kind(rule) else f"{where} is not {rule!r}"
    if key == "enum":
        if isinstance(rule, list) and any(
            value == item and _kind(value) == _kind(item) for item in rule
        ):
            return None
        return f"{where} is not one of {rule}"
    if _kind(value) not in {"integer", "number"}:
        return None
    if not isinstance(rule, int | float):
        raise CoreError(f"the frame schema has a bound that is no number, at {where}")
    below = key == "minimum" and isinstance(value, int | float) and value < rule
    above = key == "maximum" and isinstance(value, int | float) and value > rule
    return f"{where} is out of its bound {rule}" if below or above else None


def _choice(
    key: str, rule: object, value: object, root: Mapping[str, object], where: str
) -> str | None:
    if not isinstance(rule, list) or not rule:
        raise CoreError(f"the frame schema has an empty {key} at {where}")
    problems = [_problem(value, branch, root, where) for branch in rule]
    fits = sum(1 for found in problems if found is None)
    if fits == 0:
        return f"{where} fits none of its forms ({problems[0]})"
    if key == "oneOf" and fits > 1:
        return f"{where} fits more than one of its forms"
    return None


def _object(
    value: dict[object, object], schema: dict[str, object], root: Mapping[str, object], where: str
) -> str | None:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise CoreError(f"the frame schema has properties that are no object, at {where}")
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise CoreError(f"the frame schema has a required list that is no list, at {where}")
    if missing := sorted(str(name) for name in required if name not in value):
        return f"{where} has no field {', '.join(missing)}"
    extra = schema.get("additionalProperties", True)
    for name, item in value.items():
        if name in properties:
            found = _problem(item, properties[name], root, f"{where}.{name}")
        elif extra is False:
            return f"{where} has an unknown field {name}"
        else:
            found = _problem(item, extra, root, f"{where}.{name}")
        if found is not None:
            return found
    return None


def _array(
    value: Sequence[object], schema: dict[str, object], root: Mapping[str, object], where: str
) -> str | None:
    low, high = schema.get("minItems", 0), schema.get("maxItems", len(value))
    if not isinstance(low, int) or not isinstance(high, int):
        raise CoreError(f"the frame schema has a length bound that is no number, at {where}")
    if not low <= len(value) <= high:
        return f"{where} has {len(value)} items, not {low} to {high}"
    if schema.get("uniqueItems") is True and len(
        {json.dumps(item, sort_keys=True) for item in value}
    ) != len(value):
        return f"{where} repeats an item"
    prefix = schema.get("prefixItems", [])
    if not isinstance(prefix, list):
        raise CoreError(f"the frame schema has prefixItems that are no list, at {where}")
    rest = schema.get("items", True)
    for index, item in enumerate(value):
        part = prefix[index] if index < len(prefix) else rest
        found = _problem(item, part, root, f"{where}[{index}]")
        if found is not None:
            return found
    return None


def budget(name: str) -> int:
    """One list limit of the explain part, as the schema states it."""
    node: object = _schema(_SCHEMA_NAME)
    for key in ("$defs", "Explain", "properties", "budgets", "properties", name, "const"):
        if not isinstance(node, dict) or key not in node:
            raise CoreError(f"the frame schema has no explain budget {name}")
        node = node[key]
    if isinstance(node, bool) or not isinstance(node, int):
        raise CoreError(f"the frame schema has an explain budget {name} that is no count")
    return node
