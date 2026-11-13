# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind dependency proof content identically at issuance and replay (AD-237)."""

from __future__ import annotations

import re
from collections.abc import Iterable as _Iterable

from .facts import RuntimeRequirementState
from .identity_memo import IdentityMemo
from .model import Evidence, Observation, Record, RecordData, RuntimeInfo, Section, stable_id
from .state_facts import ProducerKind, VerifiedBinary
from .store_seam import active_store

_REPLAYED: IdentityMemo[Observation, str] = IdentityMemo()


def dependency_runtime_identity(runtime: RuntimeInfo, binary: VerifiedBinary | None) -> RecordData:
    fields = (
        ("name", runtime.name),
        ("required", runtime.required),
        ("requirement_state", runtime.requirement_state),
        ("version", runtime.version),
    )
    return RecordData(((("code_digest", binary.digest),) if binary is not None else ()) + fields)


def dependency_runtime_rejection(observation: Observation, proof: RecordData) -> str | None:
    verified = observation.verified_binary
    if (
        verified is None
        or observation.producer_kind != ProducerKind.BUNDLED
        or observation.analyzer.name != verified.analyzer
        or verified.runtime is None
    ):
        return "dependency_scope_runtime_unverified"
    if observation.runtime != verified.runtime or not native_runtime_valid(verified.runtime):
        return "dependency_scope_runtime_claim_invalid"
    runtime = proof.get("runtime")
    digest = runtime.get("code_digest") if isinstance(runtime, RecordData) else None
    if not digest:
        return "dependency_scope_runtime_digest_missing"
    return "dependency_scope_runtime_digest_mismatch" if digest != verified.digest else None


def native_runtime_valid(runtime: RuntimeInfo) -> bool:
    lower = re.fullmatch(r">=([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", runtime.required or "")
    version = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", runtime.version)
    return (
        runtime.name == "rust"
        and runtime.requirement_state == RuntimeRequirementState.DECLARED
        and lower is not None
        and version is not None
        and tuple(map(int, version.groups())) >= tuple(int(v or 0) for v in lower.groups())
    )


def dependency_binding_id(
    sections: _Iterable[Section],
    failures: _Iterable[Record],
    evidence: _Iterable[Evidence],
    *,
    include_calls: bool = False,
    include_source_ownership: bool = False,
) -> str:
    """Bind dependency proof content identically at issuance and replay (AD-237)."""
    bound = [
        record
        for section in sections
        for record in section.records
        if section.name in {"modules", "imports", "symbols"}
        or section.name == "references"
        and (
            record.kind == "script_namespace_effect"
            or include_calls
            or include_source_ownership
            and record.kind in {"source_role", "value_reference", "attribute_reference"}
        )
        or include_calls
        and section.name == "calls"
        or section.name == "declarations"
        and (
            record.kind
            in {
                "component_responsibility",
                "inside_component_responsibility",
                "complete_requires",
            }
            or include_calls
            and record.kind
            in {
                "call_owner",
                "forbidden_call_argument",
                "catalog_argument",
                "catalog_use",
                "forbidden_effect_under_condition",
            }
            or record.kind == "protocol_declarations"
            or include_source_ownership
            and record.kind == "source_ownership"
        )
    ]
    bound.extend(failures)
    records = sorted(bound, key=lambda item: item.id)
    entries = sorted(evidence, key=lambda item: item.id)
    store = active_store()
    if store is not None:
        # AD-346: the store holds the whole records; the shell holds only their read-set.
        return store.bind(
            [item.id if store.holds_record(item.id) else {"repr": repr(item)} for item in records],
            [
                item.id if store.holds_evidence(item.id) else {"repr": repr(item)}
                for item in entries
            ],
        )
    return stable_id("DEPENDENCY-PROOF", repr((tuple(records), tuple(entries))))


def replayed_dependency_binding_id(observation: Observation, **flags: bool) -> str:
    """Recompute the binding of one observation object once per flag set.

    A saved or changed observation is another object, so it binds again.
    """
    return _REPLAYED.get(
        observation,
        tuple(sorted(flags.items())),
        lambda: dependency_binding_id(
            observation.sections, observation.coverage.failures, observation.evidence, **flags
        ),
    )
