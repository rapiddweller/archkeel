# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Pure shared import-origin facts, independent of parser and contract."""

from collections.abc import Sequence

from .source_records import RawRecord


def _reexport_route_is_proven(
    binding: str,
    alias_targets: dict[str, set[str]],
    uncertain_bindings: set[str],
) -> bool:
    current = binding
    visited: set[str] = set()
    while current in alias_targets:
        if current in visited or current in uncertain_bindings:
            return False
        targets = alias_targets[current]
        if len(targets) != 1:
            return False
        visited.add(current)
        current = next(iter(targets))
    return True


def _terminal_reexport_origins(binding: str, alias_targets: dict[str, set[str]]) -> frozenset[str]:
    pending = [binding]
    visited: set[str] = set()
    terminals: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        targets = alias_targets.get(current)
        if targets:
            pending.extend(targets - visited)
        else:
            terminals.add(current)
    return frozenset(terminals)


def resolve_reexports(
    imports: Sequence[RawRecord],
    exports_by_module: dict[str, set[str]],
    stable_bindings: dict[str, frozenset[str]] | None = None,
) -> dict[str, frozenset[str]]:
    """Follow re-export chains in place so each import records its origin definition."""
    stable_bindings = stable_bindings or {}
    alias_targets: dict[str, set[str]] = {}
    uncertain_bindings: set[str] = set()
    _collect_reexport_targets(imports, stable_bindings, alias_targets, uncertain_bindings)
    reexports = _proven_reexports(imports, alias_targets, uncertain_bindings)
    _record_import_origins(imports, exports_by_module, stable_bindings, reexports)
    uncertain_origins = {
        binding: _terminal_reexport_origins(binding, alias_targets)
        for binding in uncertain_bindings
    }
    for item in imports:
        data = item["data"]
        uncertain_route = [alias for alias in data["reexport_chain"] if alias in uncertain_origins]
        if uncertain_route:
            data["reexport_candidates"] = sorted(
                {origin for alias in uncertain_route for origin in uncertain_origins[alias]}
            )
    return uncertain_origins


def _collect_reexport_targets(
    imports: Sequence[RawRecord],
    stable_bindings: dict[str, frozenset[str]],
    alias_targets: dict[str, set[str]],
    uncertain_bindings: set[str],
) -> None:
    for item in imports:
        data = item["data"]
        if not data["symbol"] or not (data["reexport"] or data.get("reexport_candidate")):
            continue
        binding = f"{data['source_module']}.{data['binding']}"
        target = f"{data['target_module']}.{data['symbol']}"
        targets: set[str] = {target}
        if binding in alias_targets:
            targets |= alias_targets[binding]
        alias_targets[binding] = targets
        source_unique = data["source_module"] not in stable_bindings or (
            data["binding"] in stable_bindings[data["source_module"]]
        )
        target_unique = data["target_module"] not in stable_bindings or (
            data["symbol"] in stable_bindings[data["target_module"]]
        )
        if data.get("reexport_candidate") is True or not source_unique or not target_unique:
            uncertain_bindings.add(binding)
            data["reexport_candidate"] = True
            data["reexport"] = False


def _proven_reexports(
    imports: Sequence[RawRecord],
    alias_targets: dict[str, set[str]],
    uncertain_bindings: set[str],
) -> dict[str, str]:
    reexports: dict[str, str] = {}
    for item in imports:
        data = item["data"]
        if not data["reexport"] or not data["symbol"]:
            continue
        binding = f"{data['source_module']}.{data['binding']}"
        if not _reexport_route_is_proven(binding, alias_targets, uncertain_bindings):
            uncertain_bindings.add(binding)
            data["reexport_candidate"] = True
            data["reexport"] = False
            continue
        reexports[binding] = f"{data['target_module']}.{data['symbol']}"
    return reexports


def _record_import_origins(
    imports: Sequence[RawRecord],
    exports_by_module: dict[str, set[str]],
    stable_bindings: dict[str, frozenset[str]],
    reexports: dict[str, str],
) -> None:
    for item in imports:
        data = item["data"]
        source_binding_unique = data["source_module"] not in stable_bindings or (
            data["binding"] in stable_bindings[data["source_module"]]
        )
        if data["source_module"] in stable_bindings:
            data["source_binding_unique"] = source_binding_unique
        if not data["symbol"]:
            data["reexport_chain"] = []
            data["origin_definition"] = None
            data["symbol_visibility"] = None
            data["declared_in_all"] = False
            continue
        symbol: str = data["symbol"]
        current = f"{data['target_module']}.{symbol}"
        chain = [current]
        seen: set[str] = {current}
        while current in reexports and reexports[current] not in seen:
            current = reexports[current]
            seen.add(current)
            chain.append(current)
        data["reexport_chain"] = chain
        origin_definition: str = chain[-1]
        data["origin_definition"] = origin_definition
        origin_module, _, origin_name = origin_definition.rpartition(".")
        data["origin_binding_unique"] = (
            origin_module not in stable_bindings or origin_name in stable_bindings[origin_module]
        )
        if data["reexport"] and (
            not source_binding_unique
            or (data.get("ordinary_module") and not data["origin_binding_unique"])
        ):
            data["reexport_candidate"] = True
            data["reexport"] = False
        data["symbol_visibility"] = "private" if symbol.startswith("_") else "public_name"
        data["declared_in_all"] = data["binding"] in exports_by_module.get(
            data["source_module"], set()
        )
