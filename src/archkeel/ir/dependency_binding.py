# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind dependency proof content identically at issuance and replay (AD-237)."""

from __future__ import annotations

from collections.abc import Iterable as _Iterable

from .identity_memo import IdentityMemo
from .model import Evidence, Observation, Record, Section, stable_id
from .store_seam import active_store

_REPLAYED: IdentityMemo[Observation, str] = IdentityMemo()


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
