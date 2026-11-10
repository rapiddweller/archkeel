# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Projection of source import facts into the existing observation vocabulary."""

from collections.abc import Container, Sequence

from archkeel.ir.facts_codec import RawRecord

MACRO_BODY_KIND = "macro_body"


def split_imports(
    imports: Sequence[RawRecord], unresolved: Container[str]
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Split the imports into the resolved ones, the unresolved ones and the macro templates.

    AD-349: the template of a `macro_rules!` is no edge of a cycle or a layer rule. This is the one
    place that reads the kind. The templates stay in the observation and count as coupling.
    """
    resolved: list[RawRecord] = []
    unknown: list[RawRecord] = []
    templates: list[RawRecord] = []
    for item in imports:
        if item["id"] in unresolved:
            unknown.append(item)
        elif item["kind"] == MACRO_BODY_KIND:
            templates.append(item)
        else:
            resolved.append(item)
    return resolved, unknown, templates


def count_macro_bodies(
    module_facts: Sequence[RawRecord],
    templates: Sequence[RawRecord],
    edge_pairs: Sequence[tuple[str, str]],
) -> None:
    """Add the pairs that only a macro template names to the fan-in and fan-out of the modules.

    The rank and the cycles come from the edges alone, so they never see these pairs.
    """
    known = set(edge_pairs)
    pairs = {
        (item["data"]["source_module"], item["data"]["target_module"]) for item in templates
    } - known
    by_name = {record["data"]["qualified_name"]: record["data"] for record in module_facts}
    for source, target in pairs:
        if source in by_name and target in by_name and source != target:
            by_name[source]["fan_out"] += 1
            by_name[target]["fan_in"] += 1


def strip_internal_reexport_facts(imports: Sequence[RawRecord]) -> None:
    """Keep reexport-route bookkeeping private, while retaining publisher uniqueness."""
    for item in imports:
        data = item["data"]
        if "ordinary_module" in data:
            del data["ordinary_module"]
        if "origin_binding_unique" in data:
            del data["origin_binding_unique"]
        if "origin_member_binding_static" in data:
            del data["origin_member_binding_static"]
        if "reexport_candidate" in data:
            del data["reexport_candidate"]
        if "module_level_import" in data:
            del data["module_level_import"]
