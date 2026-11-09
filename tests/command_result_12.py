# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Rebuild result schema 12.0 from the published schemas (AD-336).

JSON Schema cannot widen the enum of a schema that a `$ref` names, and schemas 6.0 to 11.0 are
pinned. So 12.0 copies the chain 6.0 to 11.0 and both architecture-command schemas. Each copy
points its diagnostic at the one diagnostic definition of 12.0, which has the new kinds. A test
compares this rebuild with the published file, so a copy cannot drift.
"""

import copy
import json
import re
from pathlib import Path
from typing import Any

_P = "urn:archkeel:command-result:"
_AC = "urn:archkeel:architecture-command:"
_ACN = f"{_P}12.0.0:architecture-command:"
_NEW_KINDS = ("unresolved_import", "not_examined", "incomplete_scan")
_DIAGNOSTIC = f"{_P}6.0.0#/$defs/diagnostic"
_ARRAY = {"type": "array", "items": {"$ref": "#/$defs/diagnostic"}}
_DROPPED = ("$id", "$schema", "$defs", "title", "$comment")
_COMMENT = (
    "AD-336: version 12 differs from 11.0 only in the diagnostic kind. It adds unresolved_import, "
    "not_examined and incomplete_scan, which name the cause of a coverage gap. Every result of "
    "11.0 and earlier stays valid. AD-138."
)


def _convert(node: Any, version: int) -> Any:
    if isinstance(node, list):
        return [_convert(item, version) for item in node]
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        reference = value.get("$ref") if isinstance(value, dict) else None
        if key == "diagnostics" and str(reference).endswith("/properties/diagnostics"):
            result[key] = _ARRAY
        elif key == "$ref" and isinstance(value, str):
            result[key] = _reference(value, version)
        else:
            result[key] = _convert(value, version)
    return result


def _reference(value: str, version: int) -> str:
    if value == _DIAGNOSTIC or (version == 6 and value == "#/$defs/diagnostic"):
        return "#/$defs/diagnostic"
    if value.startswith("#/"):
        return value if version == 11 else f"{_P}{version}.0.0{value}"
    if value.startswith(_AC):
        return _ACN + value[len(_AC) :]
    whole = re.fullmatch(rf"{_P}(\d+)\.0\.0", value)
    return f"#/$defs/v{whole.group(1)}" if whole else value


def build(schema_dir: Path) -> dict[str, Any]:
    def load(name: str) -> dict[str, Any]:
        return json.loads((schema_dir / name).read_text(encoding="utf-8"))

    chain = {6: load("command-result.schema.json")}
    chain.update({n: load(f"command-result-{n}.0.schema.json") for n in range(7, 12)})
    diagnostic = copy.deepcopy(chain[6]["$defs"]["diagnostic"])
    kinds = diagnostic["properties"]["kind"]["enum"]
    at = kinds.index("parse_error") + 1
    kinds[at:at] = _NEW_KINDS
    defs: dict[str, Any] = {"diagnostic": diagnostic}
    for file, name in (
        ("architecture-command.schema.json", "1.0.0"),
        ("architecture-command-2.0.schema.json", "2.0.0"),
    ):
        command = load(file)
        command["$id"] = _ACN + name
        command.pop("$schema")
        text = json.dumps(command).replace(_DIAGNOSTIC, f"{_P}12.0.0#/$defs/diagnostic")
        defs["architecture_command_" + name.split(".")[0]] = json.loads(text)
    for version, schema in chain.items():
        if version != 11:
            body = {k: v for k, v in schema.items() if k not in _DROPPED}
            defs[f"v{version}"] = _convert(body, version)
    root = _convert({k: v for k, v in chain[11].items() if k not in _DROPPED}, 11)
    defs.update(chain[11]["$defs"])
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_P}12.0.0",
        "title": "Archkeel command JSON results",
        "$comment": _COMMENT,
        **root,
        "$defs": defs,
    }


def render(schema_dir: Path) -> str:
    return json.dumps(build(schema_dir), indent=2) + "\n"
