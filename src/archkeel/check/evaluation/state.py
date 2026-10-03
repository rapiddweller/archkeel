# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay collected state traces under the selected architecture's context roots."""

from __future__ import annotations

from collections.abc import Sequence

from archkeel.ir.facts import Evidence
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import EvidenceClass, stable_id
from archkeel.ir.state_facts import (
    ArgumentPass,
    Assignment,
    AttributeAccess,
    FieldState,
    StateFacts,
)


def _context_simple_name(annotation: str | None, context_names: dict[str, str]) -> str | None:
    if not annotation:
        return None
    normalized = annotation.replace('"', "").replace("'", "")
    for simple, qualified in context_names.items():
        if simple in normalized:
            return qualified
    return None


def _field_detail_records(root: str, fields: dict[str, RecordData]) -> list[RawRecord]:
    records: list[RawRecord] = []
    for field_data in sorted(fields.values(), key=lambda value: value["name"]):
        records.append(
            classified(
                item_id=stable_id("CONTEXT-FIELD", root, field_data["name"]),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_field",
                title=f"{root}.{field_data['name']}",
                subjects=[root, field_data["name"]],
                evidence_ids=field_data["evidence_ids"],
                data={"context": root, **field_data},
            )
        )
    return records


def _access_detail_records(
    root: str, accesses: dict[str, list[RecordData]]
) -> list[tuple[str, RawRecord]]:
    access_kinds = {
        "reads": "context_read",
        "writes": "context_write",
        "passes": "context_pass",
        "constructed_by": "context_construction",
    }
    records: list[tuple[str, RawRecord]] = []
    for category, kind in access_kinds.items():
        for entry in accesses[category]:
            call_id = entry.get("call_id")
            item = classified(
                item_id=stable_id(
                    "CONTEXT-ACCESS",
                    root,
                    category,
                    entry.get("source"),
                    entry.get("field"),
                    entry.get("path"),
                    entry.get("target"),
                    *(entry.get("evidence_ids") or []),
                ),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind=kind,
                title=(
                    f"{entry.get('source')} {category.replace('_', ' ')} "
                    f"{entry.get('path') or entry.get('target') or root}"
                ),
                subjects=[root, entry.get("source", ""), entry.get("target", "")],
                evidence_ids=entry.get("evidence_ids", []),
                fact_ids=[call_id] if call_id else [],
                data={"context": root, "category": category, **entry},
            )
            records.append((category, item))
    return records


def _dependency_detail_records(
    root: str, owner: str | None, imports: Sequence[RawRecord]
) -> list[RawRecord]:
    dependencies = sorted(
        {
            item["data"]["target_module"]
            for item in imports
            if owner is not None
            and item["data"]["source_module"] == owner
            and item["data"]["target_module"] != owner
        }
    )
    records: list[RawRecord] = []
    for dependency in dependencies:
        import_facts = [
            item["id"]
            for item in imports
            if owner is not None
            and item["data"]["source_module"] == owner
            and item["data"]["target_module"] == dependency
        ]
        records.append(
            classified(
                item_id=stable_id("CONTEXT-DEP", root, dependency),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_dependency",
                title=f"{root} depends on {dependency}",
                subjects=[root, dependency],
                fact_ids=import_facts,
                data={"context": root, "target_module": dependency},
            )
        )
    return records


def _detail_records(
    root: str,
    owner: str | None,
    fields: dict[str, RecordData],
    accesses: dict[str, list[RecordData]],
    imports: Sequence[RawRecord],
) -> tuple[list[RawRecord], dict[str, list[str]]]:
    detail_records: list[RawRecord] = []
    detail_ids: dict[str, list[str]] = {
        "fields": [],
        "reads": [],
        "writes": [],
        "passes": [],
        "constructed_by": [],
        "dependencies": [],
    }
    field_records = _field_detail_records(root, fields)
    detail_records.extend(field_records)
    detail_ids["fields"] = [item["id"] for item in field_records]
    for category, item in _access_detail_records(root, accesses):
        detail_records.append(item)
        detail_ids[category].append(item["id"])
    dependency_records = _dependency_detail_records(root, owner, imports)
    detail_records.extend(dependency_records)
    detail_ids["dependencies"] = [item["id"] for item in dependency_records]
    return detail_records, detail_ids


def evaluate_contexts(
    facts: StateFacts,
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    declared_roots: Sequence[str],
    candidate_evidence: Sequence[Evidence],
) -> tuple[list[RawRecord], list[RawRecord], tuple[Evidence, ...]]:
    class_symbols = [item for item in symbols if item["kind"] == "class"]
    roots = set(declared_roots)
    for item in class_symbols:
        qualified = item["data"]["qualified_name"]
        if item["data"]["name"].endswith(("Context", "State")):
            roots.add(qualified)
    context_names = {name.rsplit(".", 1)[-1]: name for name in sorted(roots)}
    used_evidence: set[str] = set()
    observations = _access_observations(facts, calls, roots, context_names, used_evidence)
    classes_by_name = {item.qualified_name: item for item in facts.classes}

    result: list[RawRecord] = []
    all_detail_records: list[RawRecord] = []
    symbol_by_qname = {item["data"]["qualified_name"]: item for item in symbols}
    context_class_labels = {
        "declared_root": "DECLARED ROOT",
        "runtime_subscope": "RUNTIME SUB-SCOPE",
        "type_protocol_contract": "TYPE / PROTOCOL CONTRACT",
        "local_domain_state_candidate": "LOCAL / DOMAIN STATE CANDIDATE",
        "unknown_context_like_type": "UNKNOWN CONTEXT-LIKE TYPE",
    }
    for root in sorted(roots):
        symbol = symbol_by_qname.get(root)
        class_state = classes_by_name.get(root)
        owner = symbol["data"]["module"] if symbol is not None else None
        if root in declared_roots:
            context_class = "declared_root"
        elif symbol and symbol["data"].get("class_kind") == "protocol":
            context_class = "type_protocol_contract"
        else:
            context_class = "local_domain_state_candidate"
        fields: dict[str, RecordData] = {}
        methods: list[str] = []
        if class_state is not None:
            fields = {field.name: _field_data(field) for field in class_state.fields}
            methods = list(class_state.methods)
            used_evidence.update(class_state.evidence_ids)

        detail_records, detail_ids = _detail_records(
            root, owner, fields, observations[root], imports
        )

        detail_records = sorted(
            {item["id"]: item for item in detail_records}.values(), key=lambda item: item["id"]
        )
        detail_ids = {key: sorted(set(value)) for key, value in detail_ids.items()}
        evidence_ids = symbol["evidence_ids"] if symbol else []
        all_detail_records.extend(detail_records)
        result.append(
            classified(
                item_id=stable_id("CONTEXT", root),
                evidence_class=EvidenceClass.FACT if symbol else EvidenceClass.UNKNOWN,
                area="contexts_state",
                kind="context_topology" if symbol else "declared_context_not_observed",
                title=root,
                subjects=[root],
                evidence_ids=evidence_ids,
                fact_ids=([symbol["id"]] if symbol else [])
                + [item["id"] for item in detail_records],
                data={
                    "qualified_name": root,
                    "declared_root": root in declared_roots,
                    "context_class": context_class,
                    "context_class_label": context_class_labels[context_class],
                    "methods": sorted(methods),
                    **{key: sorted(value) for key, value in detail_ids.items()},
                },
            )
        )
    evidence_by_id = {item.id: item for item in candidate_evidence}
    return (
        sorted(result, key=lambda item: item["id"]),
        sorted(all_detail_records, key=lambda item: item["id"]),
        tuple(evidence_by_id[key] for key in sorted(used_evidence)),
    )


def _field_data(field: FieldState) -> RecordData:
    data: RecordData = {
        "name": field.name,
        "annotation": field.annotation,
        "binding": field.binding,
        "referent_mutability": field.referent_mutability,
        "mutability": field.mutability,
        "evidence_ids": list(field.evidence_ids),
    }
    if field.property_assignment is not None:
        data["property_assignment"] = field.property_assignment
    return data


def _access_observations(
    facts: StateFacts,
    calls: Sequence[RawRecord],
    roots: set[str],
    context_names: dict[str, str],
    used_evidence: set[str],
) -> dict[str, dict[str, list[RecordData]]]:
    observations: dict[str, dict[str, list[RecordData]]] = {
        root: {"reads": [], "writes": [], "passes": [], "constructed_by": []} for root in roots
    }
    for call in calls:
        for target in call["data"]["targets"]:
            if target in roots:
                observations[target]["constructed_by"].append(
                    {
                        "source": call["data"]["source_scope"],
                        "call_id": call["id"],
                        "evidence_ids": call["evidence_ids"],
                    }
                )
    for trace in facts.functions:
        bindings: dict[str, str] = {}
        if trace.class_owner in roots and trace.receiver is not None:
            bindings[trace.receiver] = trace.class_owner
        for argument in trace.parameters:
            context = _context_simple_name(argument.annotation, context_names)
            if context:
                bindings[argument.name] = context
        for event in trace.events:
            if isinstance(event, Assignment):
                assigned_context = (
                    _context_simple_name(event.constructor, context_names)
                    or _context_simple_name(event.annotation, context_names)
                    or (bindings.get(event.alias) if event.alias is not None else None)
                )
                if assigned_context:
                    for target in event.targets:
                        bindings[target] = assigned_context
            elif isinstance(event, AttributeAccess):
                bound = bindings.get(event.binding)
                if bound is None:
                    continue
                field_path = event.path[:-1] if event.access == "mutation" else event.path
                kind = "writes" if event.access in {"write", "mutation"} else "reads"
                observations[bound][kind].append(
                    {
                        "source": trace.scope,
                        "field": field_path[0],
                        "path": ".".join(field_path),
                        "access": event.access,
                        "evidence_ids": [event.evidence_id],
                    }
                )
                used_evidence.add(event.evidence_id)
            elif isinstance(event, ArgumentPass):
                bound = bindings.get(event.binding)
                if bound is None:
                    continue
                observations[bound]["passes"].append(
                    {
                        "source": trace.scope,
                        "target": event.target,
                        "evidence_ids": [event.evidence_id],
                    }
                )
                used_evidence.add(event.evidence_id)
    return observations
