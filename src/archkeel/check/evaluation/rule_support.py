# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared import matching and evaluator receipts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import Literal as _Literal
from typing import TypeAlias

from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import (
    ArchitectureRule,
    ComponentOwnership,
    EvidenceClass,
    ForbiddenDependencyRule,
    declared_package_pair,
    module_in_ownership,
    stable_id,
)

# AD-97: an import either decides a symbol rule or, when the scan cannot see which names it
# uses (a Dart import without `show`), leaves it undecided -- never a pass, never a violation.
_Verdict: TypeAlias = _Literal["violation", "allowed", "undecided"]


UncertainReexportOrigins: TypeAlias = dict[str, frozenset[str]]


FacadeEntry: TypeAlias = tuple[str, str, str, bool]


DeclaredFacade: TypeAlias = tuple[str, str, list[tuple[str, str]], str, tuple[FacadeEntry, ...]]


ReexportIndex: TypeAlias = tuple[
    dict[str, tuple[RawRecord, ...]],
    dict[str, tuple[RawRecord, ...]],
    frozenset[tuple[str, str]],
]


def _reexport_index(imports: Sequence[RawRecord]) -> ReexportIndex:
    by_origin: dict[str, list[RawRecord]] = defaultdict(list)
    by_alias: dict[str, list[RawRecord]] = defaultdict(list)
    reexport_origins: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in imports:
        data = item["data"]
        origin = data.get("origin_definition")
        alias = f"{data['source_module']}.{data['binding']}"
        alias_records: list[RawRecord] = by_alias[alias]
        alias_records.append(item)
        if data.get("reexport"):
            for chain_alias in data.get("reexport_chain", ()):
                chain_records: list[RawRecord] = by_alias[chain_alias]
                chain_records.append(item)
            if isinstance(origin, str):
                origin_records: list[RawRecord] = by_origin[origin]
                origin_records.append(item)
                binding_origins: set[str] = reexport_origins[
                    (data["source_module"], data["binding"])
                ]
                binding_origins.add(origin)
    ambiguous = frozenset(
        binding for binding, origins in reexport_origins.items() if len(origins) > 1
    )
    return (
        {key: tuple(value) for key, value in by_origin.items()},
        {key: tuple(value) for key, value in by_alias.items()},
        ambiguous,
    )


def _forbidden_dependency_verdicts(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    components: tuple[ComponentOwnership, ...],
    source_modules: frozenset[str] | None = None,
) -> Iterator[tuple[ForbiddenDependencyRule, RawRecord, _Verdict]]:
    """Yield each (rule, import) pair whose modules a forbidden_dependency rule names.

    A rule without `target_symbol` rejects every such import. One with it rejects the import
    naming that symbol, lets one naming another pass, and cannot decide one whose names the
    scan does not know.
    """
    by_label = {label: (packages, exact) for label, packages, exact in components}
    for rule in rules:
        if not isinstance(rule, ForbiddenDependencyRule):
            continue
        # A rule whose source and target each name a declared component package exactly,
        # with no target_symbol, decides (ir.decisions) and so enforces the whole ordered
        # component pair: every package of the source component against every package of
        # the target. A rule scoped to a submodule or a target_symbol keeps module matching.
        pair = declared_package_pair(rule.source, rule.target, rule.target_symbol, components)
        if pair is not None:
            sources = by_label[pair[0]]
            targets = by_label[pair[1]]
        else:
            sources = ((rule.source,), ())
            targets = ((rule.target,), ())
        allowed_sources = frozenset(rule.allowed_sources)
        for item in imports:
            if source_modules is not None and item["data"]["source_module"] not in source_modules:
                continue
            data = item["data"]
            if not module_in_ownership(data["source_module"], *sources) or not module_in_ownership(
                data["target_module"], *targets
            ):
                continue
            if data["source_module"] in allowed_sources:
                continue
            if data["under_type_checking"] and not rule.include_type_checking:
                continue
            if rule.target_symbol is None or data["symbol"] == rule.target_symbol:
                yield rule, item, "violation"
            else:
                yield rule, item, "allowed" if data["symbols_known"] else "undecided"


def _forbidden_dependency_matches(
    imports: Sequence[RawRecord],
    rules: Sequence[ArchitectureRule],
    components: tuple[ComponentOwnership, ...],
    source_modules: frozenset[str] | None = None,
) -> Iterator[tuple[ForbiddenDependencyRule, RawRecord]]:
    """Yield each (rule, import) pair a forbidden_dependency rule rejects.

    AD-18: interface_boundary reuses this to skip an import a forbidden rule already
    rejects, instead of a second matcher that could drift from this one (SPOT).
    """
    for rule, item, verdict in _forbidden_dependency_verdicts(
        imports, rules, components, source_modules
    ):
        if verdict == "violation":
            yield rule, item


def exports_by_module(modules: Sequence[RawRecord]) -> dict[str, frozenset[str]]:
    """Map each scanned module to its literal `__all__`, or an empty set when it declares none.

    Shared by `interface_boundary` and `boundary_types` (AD-63): both need the same answer to
    "does this module's `__all__` narrow which of its names are public", so both read it from
    here instead of two readings of the same `modules` section drifting apart. Public, not a
    module-private helper: `scanner.scan_repository` computes it once and hands it to both
    `rule_violations` and `rule_subject_failures` too (issue #56).
    """
    return {
        item["data"]["qualified_name"]: frozenset(item["data"]["all_exports"]) for item in modules
    }


def _rule_evaluation_receipt(
    rule: ArchitectureRule,
    scope: str,
    evaluated: Sequence[RawRecord],
    *,
    subjects: Sequence[str] | None = None,
    data: dict[str, object] | None = None,
) -> RawRecord:
    names = tuple(
        sorted(
            {
                name
                for item in evaluated
                for name in (item["data"].get("qualified_name"), item["data"].get("module"))
                if isinstance(name, str)
            }
        )
    )
    return classified(
        item_id=stable_id("RULE-EVALUATION", scope, rule.id),
        evidence_class=EvidenceClass.FACT,
        area="rules",
        kind="rule_evaluation",
        title=f"{rule.id} evaluator completed",
        subjects=list(subjects if subjects is not None else names),
        rule_ids=[rule.id],
        fact_ids=[item["id"] for item in evaluated],
        evidence_ids=sorted({evidence for item in evaluated for evidence in item["evidence_ids"]}),
        data={"scope": scope, **(data or {})},
    )
