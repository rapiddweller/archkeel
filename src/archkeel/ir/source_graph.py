# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Normalize recorded source facts into the shared graph; never infer Target intent."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    CoverageStatus,
    DefinitionBranchKind,
    DefinitionContext,
    DefinitionContextKind,
    Entity,
    EntityKind,
    ModifierKind,
    OriginKind,
    Parameter,
    ParameterKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ResolutionKind,
    Signature,
    Visibility,
    VisibilityBasis,
    VisibilityKind,
)
from archkeel.ir.facts import (
    SOURCE_RESOLUTION_GAP_KIND,
    SOURCE_SCRIPT_GLOBAL_KIND,
    InventoryStatus,
    MemberKind,
    MethodKind,
    ResolutionInput,
    ResolutionRole,
    SourceResolution,
    SourceSectionName,
    SymbolClassKind,
    member_inventories,
    parse_method_kind,
    parse_source_resolution,
    parse_symbol_class_kind,
)
from archkeel.ir.facts import RuntimeRequirementState as _RuntimeRequirementState
from archkeel.ir.model import (
    TARGET_GRAPH_RECORD_KINDS,
    EvidenceClass,
    JsonValue,
    Observation,
    RawJson,
    Record,
    RecordData,
    Verdict,
    stable_id,
)
from archkeel.ir.profiles import PROFILES, UnmeasurableScalar, profile_for

_CLASSIFIER_RELATIONSHIPS = (
    RelationshipKind.INHERITS,
    RelationshipKind.REALIZES,
    RelationshipKind.MIXES_IN,
)
MEMBER_INVENTORY_PROOF = "member_inventory_proof"
_INVENTORY_SOURCE_SECTIONS = (
    "modules",
    "packages",
    "symbols",
    "imports",
    "references",
    "calls",
    "bindings",
    "typing_signals",
    "constructs",
)


def _inventory_digest(value: RawJson) -> str:
    payload: str = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _inventory_binding(model: Observation) -> str:
    return _inventory_digest(
        {
            "analyzer": asdict(model.analyzer),
            "producer": asdict(model.producer) if model.producer else None,
            "source": asdict(model.source),
            "contract": asdict(model.contract),
            "runtime": asdict(model.runtime) if model.runtime else None,
            "coverage": asdict(model.coverage),
            "evidence": [asdict(e) for e in model.evidence],
            "declarations": [
                asdict(r)
                for r in model.records("declarations") or ()
                if r.kind not in TARGET_GRAPH_RECORD_KINDS
            ],
            "sections": {
                name: [asdict(r) for r in model.records(name) or ()]
                for name in _INVENTORY_SOURCE_SECTIONS
            },
        }
    )


def _inventory_selected_inputs(model: Observation, inputs: tuple[RecordData, ...]) -> set[str]:
    if model.analyzer.name not in {"archkeel-dart-analyzer", "archkeel-typescript-imports"}:
        return set()
    runtime = model.runtime
    version: str = runtime.version if runtime is not None else ""
    if (
        runtime is None
        or runtime.name != "python"
        or runtime.required != ">=3.11"
        or runtime.requirement_state != _RuntimeRequirementState.DECLARED
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        or tuple(int(v) for v in version.split(".")) < (3, 11, 0)
    ):
        return set()
    if model.producer is None or model.producer.name != model.analyzer.name:
        return set()
    if any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (
            model.analyzer.code_digest,
            model.producer.code_digest,
            model.contract.digest,
            model.source.source_digest,
        )
    ):
        return set()
    rows: list[dict[str, str]] = []
    for item in inputs:
        path, digest, role = item.get("path"), item.get("digest"), item.get("role")
        relative: PurePosixPath = PurePosixPath(str(path))
        if (
            set(dict(item.entries)) != {"path", "digest", "role"}
            or not isinstance(path, str)
            or not path
            or path[:1] == "/"
            or ".." in relative.parts
            or "\\" in path
            or ":" in path
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(role, str)
            or role not in {"selected", "resolution"}
        ):
            return set()
        rows.append({"path": path, "digest": digest, "role": role})
    if len({row["path"] for row in rows}) != len(rows):
        return set()
    listing: str = (
        "".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows)
        if model.analyzer.name == "archkeel-dart-analyzer"
        else json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    )
    selected = {row["path"] for row in rows if row["role"] == "selected"}
    coverage = model.coverage
    if (
        hashlib.sha256(listing.encode()).hexdigest() != model.source.source_digest
        or not selected
        or coverage.status != Verdict.FAIL
        or coverage.rules != Verdict.PASS
        or not coverage.failures
        or coverage.files_discovered != len(selected)
        or coverage.files_read != len(selected)
        or coverage.files_parsed != len(selected)
    ):
        return set()
    return selected


def _inventory_libraries(model: Observation, selected: set[str]) -> dict[str, set[str]]:
    libraries: dict[str, set[str]] = {}
    for module_record in model.records("modules") or ():
        name, path = module_record.data.get("qualified_name"), module_record.data.get("file")
        if not isinstance(name, str) or not isinstance(path, str) or path not in selected:
            return {}
        if name in libraries:
            return {}
        libraries[name] = {path}
    evidence = {e.id: e for e in model.evidence}
    for record in model.records("symbols") or ():
        module = record.data.get("module")
        if not isinstance(module, str) or module not in libraries or not record.evidence_ids:
            return {}
        paths = {evidence[key].file for key in record.evidence_ids if key in evidence}
        if len(paths) != 1 or not paths <= selected:
            return {}
        libraries[module] |= paths
    return libraries


def _inventory_gap_files(
    model: Observation, selected: set[str], libraries: dict[str, set[str]]
) -> set[str] | None:
    evidence = {e.id: e for e in model.evidence}
    paths: set[str] = set()
    for gap in model.coverage.failures:
        keys = set(dict(gap.data.entries))
        if (
            gap.kind != SOURCE_RESOLUTION_GAP_KIND
            or gap.evidence_class != EvidenceClass.UNKNOWN
            or gap.area not in {"source", "analysis_coverage"}
            or not gap.evidence_ids
            or gap.rule_ids
            or keys
            - {
                "file",
                "line",
                "message",
                "module",
                "source_module",
                "reason",
                "resolution_dimension",
            }
        ):
            return None
        sites = [evidence.get(key) for key in gap.evidence_ids]
        if any(e is None or e.file not in selected or e.line <= 0 or not e.excerpt for e in sites):
            return None
        files = {e.file for e in sites if e is not None}
        modules = {name for name, owned in libraries.items() if files <= owned}
        if len(modules) != 1:
            return None
        file = gap.data.get("file")
        module, source_module = gap.data.get("module"), gap.data.get("source_module")
        reasons = [gap.data.get(key) for key in ("reason", "message") if key in keys]
        if not reasons:
            return None
        for value in reasons:
            if not isinstance(value, str):
                return None
            reason: str = value
            if not reason.strip():
                return None
        if file is None and module is None and source_module is None:
            return None
        if file is not None and (
            file not in files
            or type(gap.data.get("line")) is not int
            or gap.data.get("line") not in {e.line for e in sites if e}
        ):
            return None
        if any(value is not None and value not in modules for value in (module, source_module)):
            return None
        allowed_subjects = modules | {
            f"{e.file}:{e.line}" for e in sites if e is not None and e.file == file
        }
        if not gap.subjects or not set(gap.subjects) <= allowed_subjects:
            return None
        if gap.data.get("resolution_dimension") not in {None, "imports", "signature"}:
            return None
        paths.update(files)
    return paths


def _inventory_owners(model: Observation, selected: set[str]) -> tuple[str, ...]:
    libraries = _inventory_libraries(model, selected)
    gaps = _inventory_gap_files(model, selected, libraries)
    if not libraries or gaps is None:
        return ()
    symbols = model.records("symbols") or ()
    names = Counter(item.data.get("qualified_name") for item in symbols)
    return tuple(
        sorted(
            item.id
            for item in symbols
            if item.kind == "class"
            and not item.data.get("definition_contexts")
            and names[item.data.get("qualified_name")] == 1
            and isinstance((module := item.data.get("module")), str)
            and module in libraries
            and not libraries[module] & gaps
            and any(
                inv.status == InventoryStatus.COMPLETE
                for inv in member_inventories(item.data.get("member_inventories"))
            )
        )
    )


def member_inventory_proof(
    model: Observation, inputs: tuple[ResolutionInput, ...]
) -> Record | None:
    """Bind complete native direct inventories to one eligible collected snapshot."""
    rows = tuple(
        RecordData((("digest", item.digest), ("path", item.path), ("role", item.role)))
        for item in inputs
    )
    selected = _inventory_selected_inputs(model, rows)
    owners = _inventory_owners(model, selected) if selected else ()
    if not owners:
        return None
    binding = _inventory_binding(model)
    evidence = tuple(
        sorted(
            {
                e
                for item in model.records("symbols") or ()
                if item.id in owners
                for e in item.evidence_ids
            }
        )
    )
    return Record(
        stable_id("MEMBER-INVENTORY", binding),
        EvidenceClass.FACT,
        "source",
        MEMBER_INVENTORY_PROOF,
        "Direct native member inventories have complete local source",
        (),
        evidence,
        (),
        owners,
        (),
        RecordData((("binding", binding), ("inputs", rows), ("schema_version", "1.0.0"))),
    )


def validated_member_inventory_proof(model: Observation) -> Record | None:
    """Replay the bound local source proof; absent or changed evidence stays unknown."""
    proofs = [
        r for r in model.records("scope_observations") or () if r.kind == MEMBER_INVENTORY_PROOF
    ]
    if len(proofs) != 1:
        return None
    proof = proofs[0]
    try:
        rows = _records(proof.data.get("inputs"))
        selected = _inventory_selected_inputs(model, rows)
        expected = (
            member_inventory_proof(
                model,
                tuple(
                    ResolutionInput(
                        str(row.get("path")),
                        str(row.get("digest")),
                        ResolutionRole(_vocabulary_text(row.get("role"))),
                    )
                    for row in rows
                ),
            )
            if selected
            else None
        )
        return proof if proof == expected else None
    except (TypeError, ValueError):
        return None


def _text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("source graph expected text")


def _vocabulary_text(value: JsonValue, *, default: str = "") -> str:
    text = _text(value)
    return default if text is None else text


def _texts(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise ValueError("source graph expected text array")
    return tuple(item for item in value if isinstance(item, str))


def _records(value: JsonValue) -> tuple[RecordData, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, RecordData) for item in value):
        raise ValueError("source graph expected record array")
    return tuple(item for item in value if isinstance(item, RecordData))


def _visibility(value: JsonValue, spelling: str | None = None) -> Visibility:
    if value is None:
        return Visibility(spelling=spelling)
    if not isinstance(value, RecordData):
        raise ValueError("source graph expected visibility record")
    return Visibility(
        VisibilityKind(_vocabulary_text(value.get("kind"), default=VisibilityKind.UNKNOWN)),
        VisibilityBasis(_vocabulary_text(value.get("basis"), default=VisibilityBasis.UNKNOWN)),
        _text(value.get("spelling")),
    )


def _signature(data: RecordData) -> Signature:
    parameters: list[Parameter] = []
    for item in _records(data.get("parameters")):
        name: str = _text(item.get("name")) or ""
        if not name:
            raise ValueError("source parameter needs a name")
        kind = ParameterKind(_vocabulary_text(item.get("kind"), default=ParameterKind.UNKNOWN))
        known = item.get("default_known")
        if known is not None and not isinstance(known, bool):
            raise ValueError("source default_known must be boolean")
        parameters.append(
            Parameter(
                name.lstrip("*") if kind in {ParameterKind.VARARGS, ParameterKind.KWARGS} else name,
                _text(item.get("annotation")),
                kind,
                _text(item.get("default")),
                known is True,
            )
        )
    return Signature(tuple(parameters), _text(data.get("returns")))


def _definition_contexts(value: JsonValue) -> tuple[DefinitionContext, ...]:
    result: list[DefinitionContext] = []
    for context in _records(value):
        kind = context.get("kind")
        branch = context.get("branch")
        if (
            {key for key, _ in context.entries} != {"kind", "branch", "evidence_ids"}
            or kind is None
            or branch is None
        ):
            raise ValueError("source definition context fields mismatch")
        result.append(
            DefinitionContext(
                DefinitionContextKind(_vocabulary_text(kind, default=DefinitionContextKind.IF)),
                DefinitionBranchKind(_vocabulary_text(branch, default=DefinitionBranchKind.BODY)),
                _texts(context.get("evidence_ids")),
            )
        )
    return tuple(result)


def _classifier_kind(value: JsonValue) -> EntityKind | None:
    """Read known source classifiers without promoting unrelated or future graph tags."""
    classifier = parse_symbol_class_kind(value)
    if classifier is not None:
        return {
            SymbolClassKind.PROTOCOL: EntityKind.INTERFACE,
            SymbolClassKind.ENUM: EntityKind.ENUM,
        }.get(classifier)
    if not isinstance(value, str):
        return None
    try:
        kind = EntityKind(value)
    except ValueError:
        return None
    return kind if kind is EntityKind.MIXIN else None


def _symbol(record: Record, language: str) -> Entity:
    data = record.data
    category = _text(data.get("symbol_category", record.kind))
    aliases = {"static_constant": EntityKind.CONSTANT, "dynamic_binding": EntityKind.BINDING}
    kind = aliases.get(category or "")
    if kind is None:
        kind = EntityKind(_vocabulary_text(category, default=EntityKind.SYMBOL))
    if kind is EntityKind.CLASS:
        kind = _classifier_kind(_text(data.get("class_kind"))) or kind
    modifiers: list[ModifierKind] = []
    if data.get("mixin_capable") is True:
        modifiers.append(ModifierKind.MIXIN)
    for key, modifier in (("async", ModifierKind.ASYNC), ("frozen_object", ModifierKind.FROZEN)):
        if data.get(key) is True:
            modifiers.append(modifier)
    method_kind = parse_method_kind(data.get("method_kind"))
    if method_kind in (MethodKind.STATIC, MethodKind.CLASS):
        modifiers.append(
            ModifierKind.STATIC if method_kind is MethodKind.STATIC else ModifierKind.CLASS
        )
    return Entity(
        record.id,
        kind,
        _text(data.get("qualified_name")) or "",
        language,
        visibility=_visibility(data.get("visibility_detail"), _text(data.get("name"))),
        signature=(
            _signature(data)
            if kind in {EntityKind.METHOD, EntityKind.FUNCTION}
            and data.get("signature_complete") is not False
            else None
        ),
        annotation=_text(data.get("annotation")),
        modifiers=tuple(modifiers),
        presence=PresenceKind.DEFINED,
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        definition_contexts=_definition_contexts(data.get("definition_contexts")),
        initializer=_text(data.get("initializer")) if kind == EntityKind.BINDING else None,
    )


def _attribute_entities(item: Record, entity: Entity, language: str) -> list[Entity]:
    fields = item.data.get("attribute_declarations", item.data.get("fields"))
    literals = _texts(item.data.get("enum_members")) if entity.kind == EntityKind.ENUM else ()
    result: list[Entity] = []
    for field in _records(fields):
        name = _text(field.get("name")) or ""
        static = field.get("static")
        if static is not None and not isinstance(static, bool):
            raise ValueError("attribute static modifier must be boolean")
        result.append(
            Entity(
                _text(field.get("definition_id")) or stable_id("ATTR", item.id, name),
                EntityKind.ENUM_LITERAL if name in literals else EntityKind.ATTRIBUTE,
                f"{entity.qualified_name}.{name}",
                language,
                parent_id=item.id,
                visibility=_visibility(field.get("visibility")),
                annotation=_text(field.get("annotation")),
                modifiers=(ModifierKind.STATIC,) if static is True and name not in literals else (),
                presence=PresenceKind.DEFINED,
                evidence_ids=_texts(field.get("evidence_ids")) or item.evidence_ids,
                record_ids=(item.id,),
                definition_contexts=entity.definition_contexts,
            )
        )
    return result


def _source_entities(observation: Observation, language: str) -> list[Entity]:
    modules = observation.records("modules") or ()
    records = {item.id: item for item in modules}
    packages = observation.records("packages") or ()
    package_ids = {_text(item.data.get("qualified_name")): item.id for item in packages}
    module_ids = {_text(item.data.get("qualified_name")): item.id for item in modules}
    entities = [
        Entity(
            item.id,
            EntityKind.PACKAGE,
            _text(item.data.get("qualified_name")) or "",
            language,
            presence=PresenceKind.DEFINED,
            evidence_ids=tuple(
                sorted(
                    set(item.evidence_ids).union(
                        *(records[fact].evidence_ids for fact in item.fact_ids if fact in records)
                    )
                )
            ),
            record_ids=(item.id,),
        )
        for item in packages
    ]
    for item in modules:
        module_name: str = _text(item.data.get("qualified_name")) or ""
        module_parent = (
            module_name
            if PurePosixPath(_text(item.data.get("file")) or "").name == "__init__.py"
            else module_name.rpartition(".")[0]
        )
        entities.append(
            Entity(
                item.id,
                EntityKind.MODULE,
                module_name,
                language,
                parent_id=package_ids.get(module_parent),
                presence=PresenceKind.DEFINED,
                evidence_ids=item.evidence_ids,
                record_ids=(item.id,),
                file_path=_text(item.data.get("file")),
            )
        )
    symbols = observation.records("symbols") or ()
    symbol_ids: dict[str, list[str]] = {}
    for item in symbols:
        name = _text(item.data.get("qualified_name")) or ""
        definitions: list[str] = symbol_ids.setdefault(name, [])
        definitions.append(item.id)
    for item in symbols:
        entity = _symbol(item, language)
        parents = symbol_ids.get(_text(item.data.get("parent")) or "", [])
        parent = _text(item.data.get("lexical_parent_id"))
        if parent is None:
            if len(parents) > 1:
                raise ValueError("ambiguous lexical parent needs a definition-site identity")
            parent = parents[0] if parents else module_ids.get(_text(item.data.get("module")))
        entities.append(replace(entity, parent_id=parent))
        entities.extend(_attribute_entities(item, entity, language))
    return entities


def _source_resolution(value: JsonValue, message: str) -> ResolutionKind:
    status = parse_source_resolution(value)
    if status is None:
        raise ValueError(message)
    return {
        SourceResolution.RESOLVED: ResolutionKind.RESOLVED,
        SourceResolution.PARTIALLY_RESOLVED: ResolutionKind.PARTIAL,
        SourceResolution.UNRESOLVED: ResolutionKind.UNRESOLVED,
    }[status]


def _site_relationship(
    record: Record, kind: RelationshipKind, source: str, targets: tuple[str, ...]
) -> Relationship:
    status = _source_resolution(
        record.data.get("status"), "source relationship needs a resolution status"
    )
    resolved = status == ResolutionKind.RESOLVED and len(targets) == 1
    count = record.data.get("candidate_count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise ValueError("source candidate_count must be integer")
    if count is not None and count < len(_texts(record.data.get("targets"))):
        raise ValueError("source candidate count is smaller than its listed targets")
    truncated = record.data.get("candidates_truncated")
    if truncated is not None and not isinstance(truncated, bool):
        raise ValueError("source candidates_truncated must be boolean")
    if status == ResolutionKind.UNRESOLVED and targets:
        raise ValueError("unresolved source relationship has candidates")
    return Relationship(
        record.id,
        kind,
        source,
        targets[0] if resolved else None,
        ResolutionKind.RESOLVED
        if resolved
        else ResolutionKind.PARTIAL
        if status != ResolutionKind.UNRESOLVED
        else ResolutionKind.UNRESOLVED,
        candidate_ids=() if resolved else targets,
        expression=_text(record.data.get("expression")),
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        # The source count names qualified targets, not their definition sites.
        candidate_count=None if truncated is True or count is None else len(targets),
        candidates_truncated=truncated is True,
        reason=_text(record.data.get("reason")),
    )


def _endpoint(
    name: str,
    record: Record,
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> tuple[str, ...]:
    known = by_name.get(name)
    if known:
        return tuple(item.id for item in known)
    referenced = Entity(
        stable_id("REFENTITY", language, name),
        EntityKind.SYMBOL,
        name,
        language,
        presence=PresenceKind.REFERENCED,
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
    )
    entities.append(referenced)
    by_name[name] = [referenced]
    return (referenced.id,)


def _source_endpoint(
    record: Record,
    name: str,
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> tuple[str, ...]:
    identity = _text(record.data.get("source_definition_id"))
    if identity:
        if not any(entity.id == identity for entity in by_name.get(name, [])):
            raise ValueError("source definition does not match its recorded scope")
        return (identity,)
    if any(key == "source_definition_id" for key, _ in record.data.entries):
        # A missing declaration must not borrow another definition with the same name.
        source = Entity(
            stable_id("REFSCOPE", record.id),
            EntityKind.SYMBOL,
            name,
            language,
            presence=PresenceKind.REFERENCED,
            evidence_ids=record.evidence_ids,
            record_ids=(record.id,),
        )
        entities.append(source)
        return (source.id,)
    return _endpoint(name, record, by_name, entities, language)


def _reconcile_result_binding(
    previous: Entity | None,
    owner: Entity,
    source: str,
    name: str,
    target_kind: str,
    annotation: str | None,
    definition_contexts: tuple[DefinitionContext, ...],
) -> tuple[str, str | None, tuple[DefinitionContext, ...]]:
    qualified_name = f"{owner.qualified_name}.{name}"
    if previous is not None:
        if (
            previous.kind != "binding"
            or previous.parent_id != source
            or previous.initializer is not None
        ):
            raise ValueError("static result binding identity conflicts")
        if target_kind == "name":
            if (
                not previous.qualified_name.startswith(f"{owner.qualified_name}.")
                or previous.qualified_name.rsplit(".", 1)[-1] != name
            ):
                raise ValueError("static result binding identity conflicts")
            qualified_name = previous.qualified_name
        elif previous.qualified_name != qualified_name:
            raise ValueError("static result binding identity conflicts")
        if (
            previous.annotation is not None
            and annotation is not None
            and previous.annotation != annotation
        ):
            raise ValueError("static result binding identity conflicts")
        if (
            previous.definition_contexts
            and definition_contexts
            and tuple((item.kind, item.branch) for item in previous.definition_contexts)
            != tuple((item.kind, item.branch) for item in definition_contexts)
        ):
            raise ValueError("static result binding identity conflicts")
        annotation = annotation if annotation is not None else previous.annotation
        if not definition_contexts:
            definition_contexts = previous.definition_contexts
    return qualified_name, annotation, definition_contexts


def _result_binding_identity(site: RecordData) -> tuple[str, str, str, str]:
    if {key for key, _ in site.entries} != {
        "id",
        "name",
        "target_kind",
        "annotation",
        "initializer",
        "evidence_ids",
        "definition_contexts",
    } or not _texts(site.get("evidence_ids")):
        raise ValueError("static result binding fields or evidence mismatch")
    identity = _text(site.get("id")) or ""
    name = _text(site.get("name")) or ""
    initializer = _text(site.get("initializer")) or ""
    target_kind = _text(site.get("target_kind")) or ""
    if (
        not identity
        or not name
        or not initializer
        or target_kind not in {"name", "attribute", "subscript"}
    ):
        raise ValueError("invalid static result binding")
    return identity, name, initializer, target_kind


def _value_bindings(
    record: Record,
    source: str,
    entities: list[Entity],
    by_name: dict[str, list[Entity]],
    positions: dict[str, int],
    language: str,
) -> tuple[tuple[Entity, str], ...]:
    sites = _records(record.data.get("result_bindings"))
    if not sites:
        return ()
    owner = entities[positions[source]]
    result: list[tuple[Entity, str]] = []
    for site in sites:
        identity, name, initializer, target_kind = _result_binding_identity(site)
        previous_index = positions.get(identity)
        previous = entities[previous_index] if previous_index is not None else None
        annotation = _text(site.get("annotation"))
        definition_contexts = _definition_contexts(site.get("definition_contexts"))
        qualified_name, annotation, definition_contexts = _reconcile_result_binding(
            previous,
            owner,
            source,
            name,
            target_kind,
            annotation,
            definition_contexts,
        )
        value = Entity(
            identity,
            EntityKind.BINDING,
            qualified_name,
            language,
            parent_id=source,
            annotation=annotation,
            presence=PresenceKind.DEFINED,
            evidence_ids=tuple(
                sorted(
                    set(record.evidence_ids)
                    | set(_texts(site.get("evidence_ids")))
                    | set(previous.evidence_ids if previous else ())
                )
            ),
            record_ids=tuple(
                sorted(set((record.id,)) | set(previous.record_ids if previous else ()))
            ),
            definition_contexts=definition_contexts,
            initializer=initializer,
        )
        if previous_index is not None:
            entities[previous_index] = value
            by_name[value.qualified_name] = [
                value if item.id == identity else item for item in by_name[value.qualified_name]
            ]
        else:
            positions[identity] = len(entities)
            entities.append(value)
            values: list[Entity] = by_name.setdefault(value.qualified_name, [])
            values.append(value)
        result.append((value, target_kind))
    return tuple(result)


def _construction_sites(
    record: Record,
    source: str,
    bindings: tuple[tuple[Entity, str], ...],
    by_name: dict[str, list[Entity]],
) -> tuple[Relationship, ...]:
    construction = record.data.get("construction")
    if construction is None:
        return ()
    if not isinstance(construction, RecordData):
        raise ValueError("invalid construction record")
    status = _source_resolution(construction.get("status"), "invalid construction resolution")
    names = _texts(construction.get("targets"))
    truncated = construction.get("candidates_truncated")
    reason = _text(construction.get("reason"))
    if (
        {key for key, _ in construction.entries}
        != {"status", "targets", "candidates_truncated", "reason"}
        or (status == ResolutionKind.UNRESOLVED) != (not names)
        or not isinstance(truncated, bool)
        or not reason
    ):
        raise ValueError("invalid construction resolution")
    if not set(names) <= set(_texts(record.data.get("targets"))) or (
        status == ResolutionKind.RESOLVED
        and (
            parse_source_resolution(record.data.get("status")) is not SourceResolution.RESOLVED
            or truncated
            or len(names) != 1
        )
    ):
        raise ValueError("construction resolution conflicts with its call site")
    targets = tuple(
        sorted(
            {
                item.id
                for name in names
                for item in by_name.get(name, ())
                if item.kind in {"class", "interface", "enum"}
            }
        )
    )
    if status != ResolutionKind.UNRESOLVED and not targets:
        raise ValueError("construction needs a recorded classifier candidate")
    resolved = status == ResolutionKind.RESOLVED and len(targets) == 1 and not truncated
    relations: list[tuple[RelationshipKind, str, bool]] = [(RelationshipKind.CREATES, source, True)]
    relations.extend(
        (RelationshipKind.INSTANCE_OF, binding.id, target_kind == "name")
        for binding, target_kind in bindings
    )
    result: list[Relationship] = []
    for kind, caller, stored in relations:
        proven = resolved and stored
        unresolved = status == ResolutionKind.UNRESOLVED
        result.append(
            Relationship(
                stable_id("CONSTRUCTION", record.id, kind, caller),
                kind,
                caller,
                targets[0] if proven else None,
                ResolutionKind.RESOLVED
                if proven
                else ResolutionKind.UNRESOLVED
                if unresolved
                else ResolutionKind.PARTIAL,
                candidate_ids=() if proven or unresolved else targets,
                expression=_text(record.data.get("expression")),
                evidence_ids=record.evidence_ids,
                record_ids=(record.id,),
                candidate_count=None if unresolved or truncated else len(targets),
                candidates_truncated=truncated,
                reason=reason if stored else "Storage is unproven; initializer type is a candidate",
            )
        )
    return tuple(result)


def _namespace_memberships(observation: Observation, entities: list[Entity]) -> list[Relationship]:
    result: list[Relationship] = []
    modules = {entity.id: entity for entity in entities if entity.kind == EntityKind.MODULE}
    for group in observation.records("packages") or ():
        for member in group.fact_ids:
            if member not in modules:
                raise ValueError("namespace group refers to an unknown module")
            result.append(
                Relationship(
                    stable_id("MEMBERSHIP", group.id, member),
                    RelationshipKind.OWNS,
                    group.id,
                    member,
                    ResolutionKind.RESOLVED,
                    evidence_ids=modules[member].evidence_ids,
                    record_ids=(group.id, member),
                    reason="membership in the recorded namespace group; not lexical containment",
                )
            )
    return result


def _declaration_endpoint(
    record: Record, kind: str, lexical_owner: str, by_name: dict[str, list[Entity]]
) -> str | None:
    keys = {"declaration_scope", "declaration_definition_id"}
    present = keys & {key for key, _ in record.data.entries}
    if not present:
        return None
    name = _text(record.data.get("declaration_scope"))
    identity = _text(record.data.get("declaration_definition_id"))
    if kind != "references" or present != keys or not name or not identity:
        raise ValueError("reference declaration needs a scope and definition identity")
    if not any(
        entity.id == identity
        and entity.kind in {EntityKind.METHOD, EntityKind.FUNCTION}
        and entity.parent_id == lexical_owner
        for entity in by_name.get(name, [])
    ):
        raise ValueError("reference declaration does not match an operation")
    return identity


def _relationships(
    observation: Observation, entities: list[Entity], language: str
) -> tuple[Relationship, ...]:
    by_name: dict[str, list[Entity]] = {}
    positions: dict[str, int] = {}
    for index, entity in enumerate(entities):
        positions.setdefault(entity.id, index)
        if entity.kind != EntityKind.PACKAGE:
            definitions: list[Entity] = by_name.setdefault(entity.qualified_name, [])
            definitions.append(entity)

    result: list[Relationship] = []
    result.extend(_namespace_memberships(observation, entities))
    indexed_count = len(entities)
    for section, kind in (
        ("imports", RelationshipKind.IMPORTS),
        ("calls", RelationshipKind.CALLS),
        ("references", RelationshipKind.REFERENCES),
    ):
        for record in observation.records(section) or ():
            if section == "references" and record.kind == "source_role":
                continue
            source_name = (
                _text(
                    record.data.get(
                        "source_scope" if kind != RelationshipKind.IMPORTS else "source_module"
                    )
                )
                or ""
            )
            sources = _source_endpoint(record, source_name, by_name, entities, language)
            if len(sources) != 1:
                raise ValueError("ambiguous source scope needs a definition-site identity")
            declaration = _declaration_endpoint(record, kind, sources[0], by_name)
            if declaration is not None:
                sources = (declaration,)
            if kind == RelationshipKind.IMPORTS:
                target_name = _text(record.data.get("target_module")) or ""
                targets = _endpoint(target_name, record, by_name, entities, language)
                result.append(
                    Relationship(
                        record.id,
                        RelationshipKind.REFERENCES
                        if record.kind == SOURCE_SCRIPT_GLOBAL_KIND
                        else RelationshipKind.IMPORTS,
                        sources[0],
                        targets[0] if len(targets) == 1 else None,
                        ResolutionKind.RESOLVED if len(targets) == 1 else ResolutionKind.PARTIAL,
                        candidate_ids=() if len(targets) == 1 else targets,
                        expression=target_name,
                        evidence_ids=record.evidence_ids,
                        record_ids=(record.id,),
                    )
                )
            else:
                target_ids: dict[str, None] = {}
                for name in _texts(record.data.get("targets")):
                    for target in _endpoint(name, record, by_name, entities, language):
                        target_ids[target] = None
                targets = tuple(target_ids)
                result.append(_site_relationship(record, kind, sources[0], targets))
                if kind == RelationshipKind.CALLS:
                    for index in range(indexed_count, len(entities)):
                        positions.setdefault(entities[index].id, index)
                    bindings = _value_bindings(
                        record, sources[0], entities, by_name, positions, language
                    )
                    indexed_count = len(entities)
                    result.extend(_construction_sites(record, sources[0], bindings, by_name))
    result.extend(
        _classifier_relationships(observation.records("symbols") or (), by_name, entities, language)
    )
    return tuple(result)


def _classifier_relationships(
    records: tuple[Record, ...],
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> list[Relationship]:
    result: list[Relationship] = []
    for record in records:
        for base in _records(record.data.get("base_declarations")):
            if record.kind != "class" or base.get("relationship_kind") is None:
                raise ValueError("typed base needs a classifier source and relationship kind")
            base_kind = RelationshipKind(
                _vocabulary_text(base.get("relationship_kind"), default=RelationshipKind.INHERITS)
            )
            if base_kind not in _CLASSIFIER_RELATIONSHIPS:
                raise ValueError("invalid classifier relationship kind")
            base_targets = tuple(
                target
                for name in _texts(base.get("targets"))
                for target in _endpoint(name, record, by_name, entities, language)
            )
            site = replace(
                record,
                id=_text(base.get("id")) or "",
                data=base,
                evidence_ids=_texts(base.get("evidence_ids")),
            )
            edge = _site_relationship(site, base_kind, record.id, base_targets)
            result.append(replace(edge, record_ids=(record.id,)))
    return result


def _section_coverage(
    observation: Observation,
    scope_id: str,
    section: SourceSectionName,
    entity_kinds: tuple[EntityKind, ...],
    relationships: tuple[RelationshipKind, ...],
    available: bool,
) -> Coverage:
    status: CoverageStatus = CoverageStatus.COMPLETE
    reason: str | None = None
    if not available:
        status, reason = CoverageStatus.UNAVAILABLE, "profile does not publish this section"
    elif observation.coverage.status != Verdict.PASS:
        status, reason = CoverageStatus.PARTIAL, "source observation is incomplete"
    elif (
        section == SourceSectionName.CALLS
        and UnmeasurableScalar.CALLS_UNRESOLVED in profile_for(observation.analyzer.name).unmeasured
    ):
        status, reason = (
            CoverageStatus.PARTIAL,
            "observed call sites do not certify an exhaustive module call inventory",
        )
    elif section == SourceSectionName.SYMBOLS:
        status, reason = (
            CoverageStatus.PARTIAL,
            "symbol records do not certify an exhaustive module-level lexical inventory",
        )
    elif section == SourceSectionName.REFERENCES:
        status, reason = (
            CoverageStatus.PARTIAL,
            "reference collector omits unresolved and external symbol uses",
        )
    return Coverage(scope_id, entity_kinds, relationships, status, reason)


def _partial_inventory_coverage(
    entity: Entity, value_modules: set[str | None], base_modules: set[str | None]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    result.append(
        Coverage(
            entity.id,
            (EntityKind.BINDING,),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in value_modules
            else CoverageStatus.UNAVAILABLE,
            reason="call-result assignments are recorded; other binding forms remain incomplete"
            if entity.qualified_name in value_modules
            else "the source facts do not certify a complete static binding inventory",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=(
                RelationshipKind.INHERITS,
                RelationshipKind.REALIZES,
                RelationshipKind.MIXES_IN,
            ),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in base_modules
            else CoverageStatus.UNAVAILABLE,
            reason="explicit bases are recorded; the classifier inventory is not exhaustive"
            if entity.qualified_name in base_modules
            else "no typed classifier relationship facts were recorded",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=(RelationshipKind.CREATES, RelationshipKind.INSTANCE_OF),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in value_modules
            else CoverageStatus.UNAVAILABLE,
            reason="constructor sites are recorded; result typing and inventory remain partial"
            if entity.qualified_name in value_modules
            else "adapter has no typed instance relationship facts",
        )
    )
    result.append(
        Coverage(
            entity.id,
            (EntityKind.ATTRIBUTE, EntityKind.ENUM_LITERAL),
            status=CoverageStatus.PARTIAL,
            reason="class-body declarations are recorded; instance assignments remain unmeasured",
        )
    )
    return tuple(result)


def _member_inventory_coverage(
    observation: Observation, entities: list[Entity]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    members: dict[tuple[str, EntityKind], set[str]] = {}
    for entity in entities:
        if entity.parent_id is not None:
            members.setdefault((entity.parent_id, entity.kind), set()).add(entity.id)
    proof = validated_member_inventory_proof(observation)
    approved = set(proof.fact_ids) if proof is not None else set()
    symbols = observation.records("symbols") or ()
    for item in symbols:
        for inventory in member_inventories(item.data.get("member_inventories")):
            kinds: tuple[EntityKind, ...] = (
                (EntityKind.ATTRIBUTE, EntityKind.ENUM_LITERAL)
                if inventory.kind == MemberKind.ATTRIBUTE
                and parse_symbol_class_kind(item.data.get("class_kind")) is SymbolClassKind.ENUM
                else (EntityKind(inventory.kind),)
            )
            actual = {identity for kind in kinds for identity in members.get((item.id, kind), ())}
            if item.kind != "class" or actual != set(inventory.definition_ids):
                raise ValueError("member inventory identities disagree with their owner")
            complete = (
                inventory.status == InventoryStatus.COMPLETE
                and (observation.coverage.status == Verdict.PASS or item.id in approved)
                and (
                    "enum_literal" not in kinds
                    or observation.analyzer.name
                    in {
                        "archkeel-dart-analyzer",
                        "archkeel-typescript-imports",
                    }
                )
            )
            result.append(
                Coverage(
                    item.id,
                    kinds,
                    status=CoverageStatus.COMPLETE if complete else CoverageStatus.PARTIAL,
                    reason=None
                    if complete
                    else (
                        "only literal enum assignments are measured"
                        if "enum_literal" in kinds
                        else inventory.reason or "source observation is incomplete"
                    ),
                )
            )
    return tuple(result)


def _coverage(observation: Observation, entities: list[Entity]) -> tuple[Coverage, ...]:
    source_kinds: tuple[EntityKind, ...] = (
        EntityKind.CLASS,
        EntityKind.INTERFACE,
        EntityKind.ENUM,
        EntityKind.MIXIN,
        EntityKind.METHOD,
        EntityKind.FUNCTION,
        EntityKind.TYPE_ALIAS,
        EntityKind.CONSTANT,
    )
    sections: tuple[
        tuple[SourceSectionName, tuple[EntityKind, ...], tuple[RelationshipKind, ...]], ...
    ] = (
        (SourceSectionName.SYMBOLS, source_kinds, ()),
        (SourceSectionName.IMPORTS, (), (RelationshipKind.IMPORTS,)),
        (SourceSectionName.CALLS, (), (RelationshipKind.CALLS,)),
        (SourceSectionName.REFERENCES, (), (RelationshipKind.REFERENCES,)),
    )
    profile = profile_for(observation.analyzer.name)
    value_modules = {
        _text(item.data.get("source_module"))
        for item in observation.records("calls") or ()
        if item.data.get("result_bindings") is not None
    }
    symbols = observation.records("symbols") or ()
    base_modules = {
        _text(item.data.get("module"))
        for item in symbols
        if item.data.get("base_declarations") is not None
    }
    result: list[Coverage] = []
    result.extend(_member_inventory_coverage(observation, entities))
    for item in symbols:
        if item.data.get("base_declarations") is None:
            continue
        bases = _records(item.data.get("base_declarations"))
        complete = observation.coverage.status == Verdict.PASS and all(
            parse_source_resolution(base.get("status")) is SourceResolution.RESOLVED
            for base in bases
        )
        result.append(
            Coverage(
                item.id,
                relationship_kinds=(
                    RelationshipKind.INHERITS,
                    RelationshipKind.REALIZES,
                    RelationshipKind.MIXES_IN,
                ),
                status=CoverageStatus.COMPLETE if complete else CoverageStatus.PARTIAL,
                reason=None if complete else "a base binding or classifier kind is not proven",
            )
        )
    for entity in entities:
        if entity.kind == EntityKind.PACKAGE:
            result.append(
                Coverage(
                    entity.id,
                    relationship_kinds=(RelationshipKind.OWNS,),
                    status=CoverageStatus.COMPLETE
                    if observation.coverage.status == Verdict.PASS
                    else CoverageStatus.PARTIAL,
                    reason=None
                    if observation.coverage.status == Verdict.PASS
                    else "source observation is incomplete",
                )
            )
        if entity.kind != EntityKind.MODULE or entity.presence != PresenceKind.DEFINED:
            continue
        for section, entity_kinds, relationships in sections:
            available = (
                section not in profile.absent_sections and observation.records(section) is not None
            )
            result.append(
                _section_coverage(
                    observation, entity.id, section, entity_kinds, relationships, available
                )
            )
        result.extend(_partial_inventory_coverage(entity, value_modules, base_modules))
    return tuple(result)


def observed_graph(observation: Observation) -> ArchitectureGraph:
    profile = profile_for(observation.analyzer.name)
    language = next(
        language for language, entry in PROFILES.items() if entry.analyzer == profile.analyzer
    )
    entities = _source_entities(observation, language)
    relationships = _relationships(observation, entities, language)
    graph = ArchitectureGraph(
        OriginKind.OBSERVED,
        tuple(sorted(entities, key=lambda entity: entity.id)),
        tuple(sorted(relationships, key=lambda edge: edge.id)),
        _coverage(observation, entities),
        observation.evidence,
    )
    graph.validate()
    return graph
