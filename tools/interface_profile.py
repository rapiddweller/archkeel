# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure the AD-9 interface surface an architecture observation would need to declare.

Dedup units, stated once because the fields mix them:
  - raw crossing-import records: crossing_imports, underscore_crossings,
    type_checking_crossings, module_imports, modules_with_all.
  - distinct (source_component, target_component, token) per edge: names_per_edge,
    protocol_crossing_uses, signature_positions, unknown_positions.
  - distinct (module, token) per target component, independent of edge: surface.

A "token" is the target module for a whole-module or star import, or
"module:symbol" for a named import; a whole-module use stands for one name, same
convention the report uses for the communication table. A named token is declared
at the module actually crossed (AD-9's re-export chain), but its parameter and
return annotations are read from where it is defined, following `origin_definition`.

Known limits: `all_exports` cannot distinguish "no __all__" from "__all__ = []" -
both are empty; a module's public top-level names come from its class/function
symbol records only, since module-level constants are not recorded; and a
re-exporting package's own public name count is limited to names it defines
itself, not names it re-exports, which can undercount the half-rule denominator
for such packages.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from archkeel.check.onboarding import (
    interface_entries,
    module_all_exports,
    public_top_level_names,
)
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.model import ArchitectureContract, Observation, Record, RecordData

WHOLE_MODULE_SYMBOLS = (None, "*")


def _load_observation(path: Path) -> Observation:
    raw = decode_json(path.read_bytes())
    if not isinstance(raw, dict):
        raise ValueError("architecture.json must decode to an object")
    return parse_observation(decode_canonical_model(raw))


def _load_contract(path: Path) -> ArchitectureContract:
    return parse_contract(decode_json(path.read_bytes()))


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a string or None")
    return value


def _token(target_module: str, symbol: str | None) -> str:
    return target_module if symbol in WHOLE_MODULE_SYMBOLS else f"{target_module}:{symbol}"


class Crossing(NamedTuple):
    """One import record whose source and target modules resolve to different components."""

    record: Record
    source_label: str
    target_label: str
    target_module: str
    symbol: str | None
    origin_definition: str | None


def _crossing_imports(imports: Iterable[Record], contract: ArchitectureContract) -> list[Crossing]:
    crossing = []
    for record in imports:
        source_module = _string(record.data.get("source_module"), "source_module")
        target_module = _string(record.data.get("target_module"), "target_module")
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is not None and target is not None and source.label != target.label:
            symbol = _optional_string(record.data.get("symbol"), "symbol")
            origin = _optional_string(record.data.get("origin_definition"), "origin_definition")
            crossing.append(
                Crossing(record, source.label, target.label, target_module, symbol, origin)
            )
    return crossing


def _edge_tokens(crossing: list[Crossing]) -> dict[tuple[str, str], set[str]]:
    edges: dict[tuple[str, str], set[str]] = {}
    for use in crossing:
        token = _token(use.target_module, use.symbol)
        edges.setdefault((use.source_label, use.target_label), set()).add(token)
    return edges


def _origin_by_token(crossing: list[Crossing]) -> dict[str, tuple[str, str]]:
    """Map each named token to the module and name where the symbol is actually defined.

    A crossing import can name a re-exporting package (`origin_definition` then points
    past it), so the definition used for signature and protocol lookups is not always
    the pair encoded in the token itself.
    """
    origins = {}
    for use in crossing:
        if use.symbol in WHOLE_MODULE_SYMBOLS or use.origin_definition is None:
            continue
        definition_module, _, definition_name = use.origin_definition.rpartition(".")
        origins[_token(use.target_module, use.symbol)] = (definition_module, definition_name)
    return origins


def _names_per_edge(edges: dict[tuple[str, str], set[str]]) -> dict[str, float | int]:
    counts = [len(tokens) for tokens in edges.values()]
    if not counts:
        return {"median": 0.0, "max": 0}
    return {"median": statistics.median(counts), "max": max(counts)}


def _raw_counts(crossing: list[Crossing], modules: Iterable[Record]) -> dict[str, int]:
    all_exports = module_all_exports(modules)
    underscore = type_checking = module_imports = 0
    modules_with_all: set[str] = set()
    for use in crossing:
        data = use.record.data
        if data.get("symbol_visibility") == "private":
            underscore += 1
        if data.get("under_type_checking") is True:
            type_checking += 1
        if use.symbol in WHOLE_MODULE_SYMBOLS:
            module_imports += 1
        if all_exports.get(use.target_module):
            modules_with_all.add(use.target_module)
    return {
        "underscore_crossings": underscore,
        "type_checking_crossings": type_checking,
        "module_imports": module_imports,
        "modules_with_all": len(modules_with_all),
    }


def _top_level_symbols(symbols: Iterable[Record]) -> dict[tuple[str, str], Record]:
    result = {}
    for symbol in symbols:
        if symbol.data.get("parent") is not None:
            continue
        module = _string(symbol.data.get("module"), "module")
        name = _string(symbol.data.get("name"), "name")
        result[(module, name)] = symbol
    return result


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string tuple")
    return value


def _is_protocol(symbol: Record) -> bool:
    bases = _string_tuple(symbol.data.get("bases"), "bases")
    return symbol.data.get("class_kind") == "protocol" or "ABC" in bases


def _parameter_annotation(value: object) -> str | None:
    if not isinstance(value, RecordData):
        raise ValueError("parameter must be a record")
    return _optional_string(value.get("annotation"), "annotation")


def _signature_positions(symbol: Record) -> tuple[int, int]:
    """Return (positions, unknown) for a function's parameters plus its return."""
    parameters = symbol.data.get("parameters")
    if parameters is None:
        parameters = ()
    if not isinstance(parameters, tuple):
        raise ValueError("parameters must be a tuple")
    annotations = [_parameter_annotation(parameter) for parameter in parameters]
    annotations.append(_optional_string(symbol.data.get("returns"), "returns"))
    return len(annotations), sum(1 for annotation in annotations if annotation is None)


def _edge_symbol_measures(
    edges: dict[tuple[str, str], set[str]],
    top_level: dict[tuple[str, str], Record],
    origins: dict[str, tuple[str, str]],
) -> dict[str, int]:
    protocol_uses = positions = unknown = 0
    for tokens in edges.values():
        for token in tokens:
            definition = origins.get(token)
            if definition is None:
                continue
            target = top_level.get(definition)
            if target is None:
                continue
            if _is_protocol(target):
                protocol_uses += 1
            if target.data.get("symbol_category") == "function":
                token_positions, token_unknown = _signature_positions(target)
                positions += token_positions
                unknown += token_unknown
    return {
        "protocol_crossing_uses": protocol_uses,
        "signature_positions": positions,
        "unknown_positions": unknown,
    }


def _component_surface(
    target_label: str,
    crossing: list[Crossing],
    all_exports: dict[str, bool],
    public_names_by_module: dict[str, set[str]],
) -> dict[str, int]:
    by_module: dict[str, list[str | None]] = {}
    for use in crossing:
        if use.target_label == target_label:
            by_module.setdefault(use.target_module, []).append(use.symbol)

    module_level_modules = module_first_entries = symbol_entries = 0
    for module, symbols_used in by_module.items():
        whole_module = any(symbol in WHOLE_MODULE_SYMBOLS for symbol in symbols_used)
        named_uses = {
            symbol for symbol in symbols_used if isinstance(symbol, str) and symbol != "*"
        }
        public_names = public_names_by_module.get(module, set())
        all_exports_nonempty = bool(all_exports.get(module))
        symbol_entries += len(named_uses) + (1 if whole_module else 0)
        entries = interface_entries(
            module, named_uses, whole_module, all_exports_nonempty, public_names
        )
        if entries == [module]:
            module_level_modules += 1
            module_first_entries += 1
        else:
            module_first_entries += len(named_uses)
    return {
        "symbol_entries": symbol_entries,
        "module_first_entries": module_first_entries,
        "module_level_modules": module_level_modules,
    }


def _surface(
    crossing: list[Crossing], modules: Iterable[Record], symbols: Iterable[Record]
) -> dict[str, dict[str, int]]:
    all_exports = module_all_exports(modules)
    public_names = public_top_level_names(symbols)
    labels = sorted({use.target_label for use in crossing})
    return {
        label: _component_surface(label, crossing, all_exports, public_names) for label in labels
    }


def _anonymize(profile: dict[str, object], contract: ArchitectureContract) -> dict[str, object]:
    labels = sorted(component.label for component in contract.components)
    aliases = {label: f"C{index + 1}" for index, label in enumerate(labels)}
    surface = profile["surface"]
    if not isinstance(surface, dict):
        raise ValueError("surface must be an object")
    profile["surface"] = {aliases[label]: counts for label, counts in surface.items()}
    return profile


def build_profile(observation: Observation, contract: ArchitectureContract) -> dict[str, object]:
    imports = observation.records("imports") or ()
    modules = observation.records("modules") or ()
    symbols = observation.records("symbols") or ()
    crossing = _crossing_imports(imports, contract)
    edges = _edge_tokens(crossing)
    top_level = _top_level_symbols(symbols)
    origins = _origin_by_token(crossing)
    profile: dict[str, object] = {
        "components": len(contract.components),
        "crossing_imports": len(crossing),
        "edges": len(edges),
        "names_per_edge": _names_per_edge(edges),
        **_raw_counts(crossing, modules),
        **_edge_symbol_measures(edges, top_level, origins),
        "surface": _surface(crossing, modules, symbols),
    }
    surface = profile["surface"]
    if not isinstance(surface, dict):
        raise ValueError("surface must be an object")
    profile["contract_lines"] = {
        "symbol_only": sum(counts["symbol_entries"] for counts in surface.values()),
        "module_first": sum(counts["module_first_entries"] for counts in surface.values()),
    }
    return profile


def main() -> None:
    description = (__doc__ or "").splitlines()[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--architecture", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--anonymize", action="store_true")
    args = parser.parse_args()

    observation = _load_observation(args.architecture)
    contract = _load_contract(args.contract)
    profile = build_profile(observation, contract)
    if args.anonymize:
        profile = _anonymize(profile, contract)
    print(json.dumps(profile, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
