# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Group collector definitions by the owner identified in the same scan."""

from collections import defaultdict
from collections.abc import Iterator

_Row = dict[str, object]


def _rows(value: object) -> Iterator[_Row]:
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                yield row


def _symbol_rows(records: list[_Row]) -> Iterator[_Row]:
    """Preserve definition IDs so calls, source evidence and class members agree."""
    definitions = {row["id"]: row for row in records}
    owners: dict[str, set[str]] = defaultdict(set)
    attributes: dict[str, _Row] = {}
    for owner in records:
        if owner.get("kind") != "class":
            continue
        for attr in _rows(owner.get("attributes")):
            key = str(attr["definition_id"])
            owners[key].add(str(owner["id"]))
            attributes[key] = attr
        for inventory in _rows(owner.get("member_inventories")):
            ids = inventory.get("definition_ids")
            if isinstance(ids, list):
                for key in ids:
                    owners[str(key)].add(str(owner["id"]))

    for row in records:
        key = str(row["id"])
        parent = row.get("lexical_parent_id")
        known_parent = definitions.get(parent)
        if not known_parent and len(owners[key]) == 1:
            known_parent = definitions.get(next(iter(owners[key])))
        yield _entry(row, known_parent, attributes.get(key))
    for key, attr in attributes.items():
        if key in definitions or len(owners[key]) != 1:
            continue
        owner = definitions[next(iter(owners[key]))]
        row = dict(
            attr,
            id=key,
            module=owner["module"],
            kind="property",
            qualified_name=f"{owner['qualified_name']}.{attr['name']}",
        )
        yield _entry(row, owner, attr)


def _entry(row: _Row, parent: _Row | None, attr: _Row | None) -> _Row:
    kind = row.get("kind")
    body = {
        key: row[key]
        for key in ("method_kind", "accessor_kind", "property_operation")
        if row.get(key) is not None
    }
    name = row.get("qualified_name")
    if kind == "class":
        coverage = {"method": "unknown", "property": "unknown"}
        for inventory in _rows(row.get("member_inventories")):
            category = {"attribute": "property", "method": "method"}.get(str(inventory["kind"]))
            if category:
                coverage[category] = str(inventory["status"])
        body.update(
            member_coverage=coverage,
            members_complete=all(status == "complete" for status in coverage.values()),
            property_names=row.get("property_names"),
        )
    elif parent and parent.get("kind") == "class":
        if attr is not None or row.get("property_operation") or row.get("accessor_kind"):
            kind = "property"
        elif kind == "function":
            kind = "method"
    if attr:
        body.update(
            {key: attr[key] for key in ("annotation", "static") if attr.get(key) is not None}
        )
    if isinstance(name, str):
        body["display_name"] = name.rsplit(".", 1)[-1]
    return dict(row, kind=kind, parent=parent["id"] if parent else row.get("module"), body=body)
