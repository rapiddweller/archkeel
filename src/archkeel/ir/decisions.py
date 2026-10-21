# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive undecided component pairs from one observation alone (AD-15).

Decision summaries and full lists read the same projected dependency decisions and observed
component edges, so validation and reports share one derivation.
"""

from __future__ import annotations

import json
import re
from collections import Counter as _Counter
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath as _PurePosixPath
from typing import Final as _Final

from .baseline import ViolationFingerprint as _ViolationFingerprint
from .baseline import violation_rows
from .bindings import unread_bindings
from .codec_contract import parse_dependency_selector
from .duplication import repeated_logic
from .facts import RuntimeRequirementState as _RuntimeRequirementState
from .facts import SourceProfile as _SourceProfile
from .facts_codec import thaw_data as _thaw_data
from .facts_validation import validate_source_bindings
from .interfaces import component_owners, owner_of
from .measurements import RatchetError
from .model import (
    RULE_RECORD_KINDS,
    AllowedDependencyRule,
    ArchitectureRuleKind,
    ComparisonStatus,
    ComponentOwnership,
    ComponentOwnershipInput,
    DecisionMaker,
    Evidence,
    EvidenceClass,
    ForbiddenDependencyRule,
    JsonValue,
    Observation,
    OpenDecision,
    Record,
    RecordData,
    ReviewClaims,
    RuleAssessment,
    RuleAssessmentStatus,
    RuntimeInfo,
    Section,
    Verdict,
    ViolationCounts,
    dependency_owners,
    in_scope,
    module_in_ownership,
    package_owners,
    stable_id,
)
from .model import (
    RuleUncertaintyCause as RuleUncertaintyCause,
)
from .references import unreferenced_symbols
from .structure import oversized_insides
from .type_fanin import type_fanin

_DECIDING_KINDS = frozenset({"forbidden_dependency", "allowed_dependency"})

# The two kinds a component declaration reaches the observation under, one per level (AD-34).
_COMPONENT_KINDS = frozenset({"component_responsibility", "inside_component_responsibility"})

# The provenance every drafted dependency option cites; init writes this file alongside
# the contract, so the path already exists by the time an architect copies an option in.
DOCUMENT_PATH: _Final = "docs/architecture/architecture.md"

_PLACEHOLDER_RATIONALE: _Final = "TODO: the architect's reason for this decision."


@dataclass(frozen=True, slots=True)
class RuleUncertaintyAction:
    cause: RuleUncertaintyCause
    architect_actionable: bool | None
    next_action: str


@dataclass(frozen=True, slots=True)
class RuleUncertainty:
    actions: tuple[RuleUncertaintyAction, ...]
    evidence: tuple[Record, ...]
    undecided_positions: int


_INCOMPLETE_EXECUTION_ACTION = RuleUncertaintyAction(
    RuleUncertaintyCause.INCOMPLETE_EXECUTION,
    False,
    "Complete source observation before judging this rule.",
)


_UNSUPPORTED_TYPE_ACTION = RuleUncertaintyAction(
    RuleUncertaintyCause.UNSUPPORTED_ANALYSIS,
    False,
    "A contract decision cannot resolve this analysis gap; inspect the recorded type evidence "
    "and improve analyzer support or provide provable source annotations or re-export routes.",
)


_BOUNDARY_TYPE_TOTALS = frozenset({"positions", "decided", "undecided", "undecidable_positions"})
_BOUNDARY_POSITION_FIELDS = frozenset(
    {"module", "qualified_name", "position", "annotation", "reason", "occurrence"}
)


def _boundary_position_key(data: RecordData) -> tuple[str, str, str, str, str, int]:
    if not _BOUNDARY_POSITION_FIELDS <= frozenset(key for key, _ in data.entries):
        raise RatchetError("boundary_type_position has incomplete coordinate data")
    module = data.get("module")
    qualified_name = data.get("qualified_name")
    position = data.get("position")
    annotation = data.get("annotation")
    reason = data.get("reason")
    occurrence = data.get("occurrence")
    if (
        not isinstance(module, str)
        or not module
        or not isinstance(qualified_name, str)
        or not qualified_name
        or not isinstance(position, str)
        or not position
        or not isinstance(annotation, str)
        or not isinstance(reason, str)
        or not reason
        or not isinstance(occurrence, int)
        or isinstance(occurrence, bool)
        or occurrence < 0
    ):
        raise RatchetError("boundary_type_position has invalid coordinate data")
    return module, qualified_name, position, annotation, reason, occurrence


def _boundary_type_undecided(
    record: Record, position_records: tuple[Record, ...], analyzer_version: str
) -> tuple[int, set[str]]:
    data = record.data
    positions = record.data.get("positions")
    decided = record.data.get("decided")
    undecided = record.data.get("undecided")
    reason_counts = {
        reason: value
        for reason, value in record.data.entries
        if reason not in _BOUNDARY_TYPE_TOTALS
    }
    valid_reason_counts = {
        reason: value
        for reason, value in reason_counts.items()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }
    if (
        not isinstance(positions, int)
        or isinstance(positions, bool)
        or positions <= 0
        or not isinstance(decided, int)
        or isinstance(decided, bool)
        or decided < 0
        or not isinstance(undecided, int)
        or isinstance(undecided, bool)
        or undecided < 0
        or positions != decided + undecided
        or len(valid_reason_counts) != len(reason_counts)
        or sum(valid_reason_counts.values()) != undecided
    ):
        raise RatchetError("boundary_type_limit has incoherent aggregate counts")
    details_present = "undecidable_positions" in dict(data.entries)
    details = data.get("undecidable_positions")
    matching = tuple(item for item in position_records if item.rule_ids == record.rule_ids)
    if not details_present:
        if matching:
            raise RatchetError("boundary_type_limit is missing position details")
        try:
            version = tuple(int(part) for part in analyzer_version.split("."))
        except ValueError as error:
            raise RatchetError("invalid analyzer version for boundary type details") from error
        if len(version) != 3 or any(part < 0 for part in version):
            raise RatchetError("invalid analyzer version for boundary type details")
        if version >= (0, 43, 0):
            raise RatchetError("boundary_type_limit is missing position details")
        return (
            sum(
                value for reason, value in valid_reason_counts.items() if reason != "external_type"
            ),
            set(),
        )
    if not isinstance(details, tuple) or not details or len(record.rule_ids) != 1:
        raise RatchetError("boundary_type_limit has invalid position details")
    expected: list[tuple[str, str, str, str, str, int]] = []
    for detail in details:
        if not isinstance(detail, RecordData):
            raise RatchetError("boundary_type_limit has invalid position details")
        key = _boundary_position_key(detail)
        if key[4] not in valid_reason_counts:
            raise RatchetError("boundary_type_limit has an uncounted detail reason")
        expected.append(key)
    expected_coordinates = [(key[0], key[1], key[2], key[5]) for key in expected]
    if len(set(expected_coordinates)) != len(expected_coordinates):
        raise RatchetError("boundary_type_limit has duplicate position coordinates")
    if len(expected) != undecided:
        raise RatchetError("boundary_type_limit detail count mismatch")
    for reason, count in valid_reason_counts.items():
        if count != sum(1 for key in expected if key[4] == reason):
            raise RatchetError("boundary_type_limit detail reason counts mismatch")
    actual = [_boundary_position_key(item.data) for item in matching]
    actual_coordinates = [(key[0], key[1], key[2], key[5]) for key in actual]
    if len(set(actual_coordinates)) != len(actual_coordinates):
        raise RatchetError("boundary_type_position has duplicate logical coordinates")
    if sorted(actual) != sorted(expected):
        raise RatchetError("boundary_type_limit detail records are missing or inconsistent")
    return (
        sum(1 for key in expected if key[4] != "external_type"),
        {item.id for item in matching},
    )


def _unknown_evidence_and_counts(
    observation: Observation,
) -> tuple[int, dict[str, int], dict[str, tuple[Record, ...]]]:
    """Select exactly the records and counts used by the UNKNOWN ratchet (AD-92/67)."""
    failed = {record.id for record in observation.coverage.failures}
    records = observation.records("unknowns")
    if records is None:
        raise RatchetError("unknowns must be a record list")
    positions = tuple(record for record in records if record.kind == "boundary_type_position")
    matched_positions: set[str] = set()
    totals: _Counter[str] = _Counter()
    selected: dict[str, list[Record]] = {}
    total = 0
    disclaimers = {"dynamic_call_limit", "context_alias_limit", "private_attribute_access_limit"}
    for record in records:
        if (
            record.id in failed
            or record.kind in disclaimers
            or record.kind == "boundary_type_position"
        ):
            continue
        if record.kind == "boundary_type_limit":
            count, matched = _boundary_type_undecided(
                record, positions, observation.analyzer.version
            )
            matched_positions.update(matched)
        else:
            raw_count = record.data.get("undecided")
            count = (
                raw_count
                if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count > 0
                else 1
            )
        if not count:
            continue
        total += count
        for rule_id in set(record.rule_ids):
            totals[rule_id] += count
            selected.setdefault(rule_id, []).append(record)
    if matched_positions != {item.id for item in positions}:
        raise RatchetError("boundary_type_position has no matching aggregate")
    for record in positions:
        if record.data.get("reason") == "external_type":
            continue
        for rule_id in set(record.rule_ids):
            if rule_id in selected:
                selected[rule_id].append(record)
    return (
        total,
        dict(totals),
        {
            rule_id: tuple(sorted(items, key=lambda item: item.id))
            for rule_id, items in selected.items()
        },
    )


def _rule_uncertainty_action(record: Record) -> RuleUncertaintyAction:
    if record.kind == "rule_ownership_blocker":
        return RuleUncertaintyAction(
            RuleUncertaintyCause.MISSING_OWNERSHIP,
            True,
            "Assign each affected module to exactly one component.",
        )
    route_details = record.data.get("undecidable_positions")
    if record.kind == "boundary_type_route":
        return _UNSUPPORTED_TYPE_ACTION
    elif record.kind == "rule-unsupported-by-profile":
        return RuleUncertaintyAction(
            RuleUncertaintyCause.UNSUPPORTED_ANALYSIS,
            False,
            "A contract decision cannot resolve this analysis gap; use an analyzer profile "
            "that supports this rule.",
        )
    elif record.kind == "inside_source_domain_incomplete":
        return RuleUncertaintyAction(
            RuleUncertaintyCause.MISSING_INTENT,
            True,
            "Align the affected child component's packages/exact_modules with the parent "
            "component's source domain.",
        )
    elif record.kind == "component_scope_assignment_incomplete":
        return _INCOMPLETE_EXECUTION_ACTION
    elif record.kind == "boundary_type_position" and record.data.get("reason") in {
        "unresolved_reexport_route",
        "forward_reference",
    }:
        return _UNSUPPORTED_TYPE_ACTION
    elif (
        record.kind == "boundary_type_limit"
        and isinstance(route_details, tuple)
        and any(
            isinstance(item, RecordData)
            and item.get("reason") in {"unresolved_reexport_route", "forward_reference"}
            for item in route_details
        )
    ):
        return _UNSUPPORTED_TYPE_ACTION
    else:
        return RuleUncertaintyAction(
            RuleUncertaintyCause.UNKNOWN,
            None,
            "Inspect the recorded evidence to determine the cause.",
        )


def rule_uncertainty_evidence(observation: Observation) -> dict[str, RuleUncertainty]:
    """Return typed causes and causal evidence using the same position semantics as ratchets."""
    _, counts, unknown_evidence = _unknown_evidence_and_counts(observation)
    complete_scopes = {
        row.id
        for row in rule_assessments(
            observation,
            undecided_by_rule=counts,
            complete=observation.coverage.status == Verdict.PASS,
        )
        if row.evaluation_proven
    }
    records_by_rule = {rule_id: list(records) for rule_id, records in unknown_evidence.items()}
    ownership_blockers = tuple(
        record
        for record in observation.records("scope_observations") or ()
        if record.kind == "rule_ownership_blocker"
    )
    for record in (*ownership_blockers, *observation.coverage.failures):
        for rule_id in record.rule_ids:
            records_by_rule.setdefault(rule_id, []).append(record)
    if observation.coverage.status != Verdict.PASS or observation.coverage.failures:
        for declaration in observation.records("declarations") or ():
            if (
                declaration.evidence_class == EvidenceClass.DECLARED_RULE
                and declaration.kind in RULE_RECORD_KINDS
                and declaration.id not in complete_scopes
            ):
                records_by_rule.setdefault(declaration.id, [])

    result: dict[str, RuleUncertainty] = {}
    for rule_id, records in sorted(records_by_rule.items()):
        actions = {_rule_uncertainty_action(record) for record in records}
        if (
            observation.coverage.status != Verdict.PASS or observation.coverage.failures
        ) and rule_id not in complete_scopes:
            actions |= {_INCOMPLETE_EXECUTION_ACTION}
        result[rule_id] = RuleUncertainty(
            tuple(sorted(actions, key=lambda item: (item.cause.value, item.next_action))),
            tuple(sorted(records, key=lambda item: item.id)),
            counts.get(rule_id, 0),
        )
    return result


def unknown_positions_by_rule(observation: Observation) -> dict[str, int]:
    return _unknown_evidence_and_counts(observation)[1]


def unknown_positions(observation: Observation) -> int:
    return _unknown_evidence_and_counts(observation)[0]


def _decides_this_level(record: Record) -> bool:
    """False for a rule a component's inside declares: it decides that level's pairs, not these.

    The parent id is the signal the analyzer writes on every inside record (AD-36); reading the
    rule id's prefix instead would decide behaviour from a name.
    """
    return record.data.get("parent_id") is None


def _decided_component_pairs(
    observation: Observation, components: tuple[ComponentOwnership, ...]
) -> set[tuple[str, str]]:
    """Pairs a `forbidden_dependency` or `allowed_dependency` rule decides.

    A rule naming uniquely declared package selectors decides their whole pair, including
    exact members. A submodule endpoint or `target_symbol` remains partial.
    """
    decided: set[tuple[str, str]] = set()
    owners = dependency_owners(components)
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS or not _decides_this_level(record):
            continue
        selector = parse_dependency_selector(record)
        pair = selector.component_pair(owners)
        if pair is not None:
            decided.add(pair)
    return decided


def _component_import_sites(
    observation: Observation, components: tuple[ComponentOwnership, ...]
) -> _Counter[tuple[str, str]]:
    """Import-site counts per component pair, from the analyzer's own module-level edges."""
    sites: _Counter[tuple[str, str]] = _Counter()
    for record in observation.records("dependency_edges") or ():
        if record.kind != "module_dependency":
            continue
        source_module = record.data.get("source")
        target_module = record.data.get("target")
        count = record.data.get("count")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        if not isinstance(count, int):
            continue
        source = owner_of(source_module, components)
        target = owner_of(target_module, components)
        if source is not None and target is not None and source != target:
            sites[(source, target)] += count
    return sites


def _ownership_with_exact_modules(
    components: tuple[ComponentOwnershipInput, ...],
) -> tuple[ComponentOwnership, ...]:
    normalized: list[ComponentOwnership] = []
    for component in components:
        if len(component) == 2:
            normalized.append((component[0], component[1], ()))
        else:
            label, packages, exact_modules = component
            normalized.append((label, packages, exact_modules))
    return tuple(normalized)


def _open_decision(
    source: str, target: str, packages: dict[str, tuple[str, ...]], import_sites: int
) -> OpenDecision:
    source_package = packages[source][0]
    target_package = packages[target][0]
    forbidden_id, allowed_id = dependency_rule_ids(source, target)
    return OpenDecision(
        source,
        target,
        source_package,
        target_package,
        import_sites > 0,
        import_sites,
        ForbiddenDependencyRule(
            forbidden_id,
            ArchitectureRuleKind.FORBIDDEN_DEPENDENCY,
            source_package,
            target_package,
            True,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            DecisionMaker.AGENT,
        ),
        AllowedDependencyRule(
            allowed_id,
            ArchitectureRuleKind.ALLOWED_DEPENDENCY,
            source_package,
            target_package,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            DecisionMaker.AGENT,
        ),
    )


def _exact_open_decision(
    source: str,
    target: str,
    components: dict[str, ComponentOwnership],
    import_sites: int,
) -> OpenDecision:
    source_packages, source_exact = components[source][1:]
    target_packages, target_exact = components[target][1:]
    return OpenDecision(
        source,
        target,
        source_packages[0] if source_packages else None,
        target_packages[0] if target_packages else None,
        import_sites > 0,
        import_sites,
        None,
        None,
        source_packages,
        target_packages,
        source_exact,
        target_exact,
        "exact_ownership_suggestions_not_generated",
    )


def _materialize_open_decision(
    source: str,
    target: str,
    import_sites: int,
    packages: dict[str, tuple[str, ...]],
    declarations: dict[str, ComponentOwnership],
) -> OpenDecision:
    if declarations[source][2] or declarations[target][2]:
        return _exact_open_decision(source, target, declarations, import_sites)
    return _open_decision(source, target, packages, import_sites)


def requires_declared(observation: Observation) -> bool:
    """True when a `complete_requires` rule decides every component pair by absence (AD-32)."""
    return any(
        record.kind == "complete_requires" and _decides_this_level(record)
        for record in observation.records("declarations") or ()
    )


def _open_decision_context(
    observation: Observation,
    components: tuple[ComponentOwnershipInput, ...] | None,
) -> (
    tuple[
        tuple[ComponentOwnership, ...],
        set[str],
        set[tuple[str, str]],
        _Counter[tuple[str, str]],
    ]
    | None
):
    if requires_declared(observation):
        return None
    resolved = (
        component_owners(observation)
        if components is None
        else _ownership_with_exact_modules(components)
    )
    labels = {label for label, _, _ in resolved}
    return (
        resolved,
        labels,
        _decided_component_pairs(observation, resolved),
        _component_import_sites(observation, resolved),
    )


def open_decisions(
    observation: Observation,
    components: tuple[ComponentOwnershipInput, ...] | None = None,
) -> tuple[OpenDecision, ...]:
    """Derive undecided component pairs, heaviest observed edges first (AD-15).

    `components` lets `init` supply the components it just drafted, before any contract
    declares them; `validate` and a report rendered later from `architecture.json` bytes
    pass none and read the observation's own declared components instead.

    A contract carrying `complete_requires` owes no pair decision at all: there absence
    forbids, so an unlisted pair is decided rather than open (AD-32).
    """
    context = _open_decision_context(observation, components)
    if context is None:
        return ()
    resolved, labels, decided, sites = context
    package_selectors = tuple((label, packages) for label, packages, _ in resolved if packages)
    packages = dict(package_selectors)
    expected = {(source, target) for source in labels for target in labels if source != target}
    declarations = {label: component for component in resolved for label in (component[0],)}
    return tuple(
        sorted(
            (
                _materialize_open_decision(
                    source, target, sites[(source, target)], packages, declarations
                )
                for source, target in expected - decided
            ),
            key=lambda item: (-item.import_sites, item.source, item.target),
        )
    )


def open_decision_summary(
    observation: Observation,
    components: tuple[ComponentOwnershipInput, ...] | None = None,
) -> tuple[tuple[OpenDecision, ...], int]:
    """Return observed undecided crossings and the exact total without building every pair."""
    context = _open_decision_context(observation, components)
    if context is None:
        return (), 0
    resolved, labels, decided, sites = context
    decided_count = sum(
        source in labels and target in labels and source != target for source, target in decided
    )
    total = len(labels) * (len(labels) - 1) - decided_count
    observed = sorted(
        (
            (source, target, count)
            for (source, target), count in sites.items()
            if source != target
            and source in labels
            and target in labels
            and (source, target) not in decided
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    packages = {label: package for label, package, _ in resolved if package}
    declarations = {label: component for component in resolved for label in (component[0],)}
    decisions = tuple(
        _materialize_open_decision(source, target, count, packages, declarations)
        for source, target, count in observed
    )
    return decisions, total


def identifier(label: str) -> str:
    return label.upper().replace("_", "-")


def _component_deciders(record: Record) -> list[JsonValue]:
    """Who decided each edge and the interface this component record declares (AD-50).

    One `requires` entry is one decision, and a declared `public` list is one more, whether
    it names entries or is empty: declaring no public surface is itself the interface
    decision. A component that declares no `public` at all recorded none.
    """
    requires = record.data.get("requires")
    entries = requires if isinstance(requires, tuple) else ()
    deciders = [entry.get("decided_by") for entry in entries if isinstance(entry, RecordData)]
    if isinstance(record.data.get("public"), tuple):
        deciders.append(record.data.get("decided_by"))
    return deciders


def agent_decisions(observation: Observation) -> tuple[int, int]:
    """Count the decisions `decided_by` the agent against every decision recorded (AD-50).

    A decision is one rule declaration (AD-16), one `requires` entry, or one declared
    `public` list: in a target-first contract the edge and the facade are decisions as much
    as a rule is, and a review that counted rules alone could not find them. A decision
    nobody attributed counts in the total alone, because it was still made.

    Reads the analyzer's own projected declarations, the same evidence `open_decisions`
    reads, so validation and a report rendered later from `architecture.json` bytes alone
    share one derivation with no second contract read. What an inside declares counts here,
    unlike in the pair derivations above: it is a decision somebody made, whichever level it
    governs, and an agent decision nobody reviewed is no less unreviewed one level down.
    """
    deciders: list[JsonValue] = []
    for record in observation.records("declarations") or ():
        if record.kind in RULE_RECORD_KINDS:
            deciders.append(record.data.get("decided_by"))
        elif record.kind in _COMPONENT_KINDS:
            deciders.extend(_component_deciders(record))
    agent = sum(decider == "agent" for decider in deciders)
    return agent, len(deciders)


def _named(status: ComparisonStatus, candidates: tuple[object, ...]) -> int | None:
    """An unsupported claim names nothing, which is not the same as finding nothing (AD-5)."""
    return len(candidates) if status is ComparisonStatus.SUPPORTED else None


def review_claims(observation: Observation) -> ReviewClaims:
    """Count every review claim once, so terminal, JSON and page cannot disagree (AD-35).

    Derived here beside `agent_decisions` and `open_decisions`, the other counts a result
    carries, so a report rendered later from `architecture.json` bytes alone still agrees.
    """
    symbols = unreferenced_symbols(observation)
    insides = oversized_insides(observation)
    bindings = unread_bindings(observation)
    logic = repeated_logic(observation)
    fanin = type_fanin(observation)
    return ReviewClaims(
        _named(symbols.status, symbols.candidates),
        _named(insides.status, insides.candidates),
        _named(bindings.status, bindings.candidates),
        _named(logic.status, logic.candidates),
        _named(fanin.status, fanin.candidates),
    )


def violation_counts(observation: Observation) -> ViolationCounts:
    """Group one observation's violations by rule and by the component pair they cross (AD-51).

    A rule with no violation is absent: the contract already lists every rule, while this
    answers how many remain. Built on `ir.baseline.violation_rows` (AD-54), whose own
    `source_component`/`target_component` already come from the record's `source_module` and
    `target_module`, never from the position of a subject, which `classified` sorts. A
    violation that names no import, such as a construct, an unassigned module or a cycle,
    crosses no pair and is counted by rule alone. `fingerprint.rules[0]` never needs a
    fallback: `embedded.violations` sets exactly one rule id on every violation it produces,
    and `ir.codec.parse_record` (AD-54) rejects a VIOLATION record read back with none.
    """
    rules: _Counter[str] = _Counter()
    pairs: _Counter[tuple[str, str]] = _Counter()
    for row in violation_rows(observation):
        rules[row.fingerprint.rules[0]] += 1
        if (
            row.source_component is not None
            and row.target_component is not None
            and row.source_component != row.target_component
        ):
            pairs[(row.source_component, row.target_component)] += 1
    return ViolationCounts(
        tuple(
            (rule, count)
            for rule, count in sorted(rules.items(), key=lambda item: (-item[1], item[0]))
        ),
        tuple(
            (source, target, count)
            for (source, target), count in sorted(
                pairs.items(), key=lambda item: (-item[1], item[0])
            )
        ),
    )


def _rule_status(
    *, declared_only: bool, violations: int, complete: bool, receipt: bool, undecided: int
) -> tuple[RuleAssessmentStatus, str]:
    if declared_only:
        return (
            RuleAssessmentStatus.DECLARATION,
            "Permission declaration; it does not evaluate conformance.",
        )
    if violations:
        return RuleAssessmentStatus.FAIL, "The evaluator recorded one or more violations."
    if not complete:
        return (
            RuleAssessmentStatus.UNKNOWN,
            "The observation is incomplete; a complete evaluator scope is not proven.",
        )
    if not receipt:
        return (
            RuleAssessmentStatus.UNKNOWN,
            "No complete evaluator receipt exists for this rule and scope.",
        )
    if undecided:
        return RuleAssessmentStatus.UNKNOWN, "The evaluator left one or more positions undecided."
    return (
        RuleAssessmentStatus.PASS,
        "The evaluator completed this rule's observed scope without violations.",
    )


def _ownership_blocker_reason(observation: Observation, rule_id: str) -> str | None:
    blockers = sorted(
        (
            record
            for record in observation.records("scope_observations") or ()
            if record.kind == "rule_ownership_blocker" and rule_id in record.rule_ids
        ),
        key=lambda record: record.subjects,
    )
    reasons = [
        value for record in blockers if isinstance((value := record.data.get("reason")), str)
    ]
    return " ".join(reasons) if reasons else None


def _numeric_scope_proven(observation: Observation, receipt: Record) -> bool:
    proof = receipt.data.get("numeric_scope_proof")
    coverage = observation.coverage
    selected_files = proof.get("selected_files") if isinstance(proof, RecordData) else None
    module_ids = proof.get("module_ids") if isinstance(proof, RecordData) else None
    operation_ids = proof.get("operation_ids") if isinstance(proof, RecordData) else None
    modules_records = observation.records("modules") or ()
    numeric_records = tuple(
        item for item in observation.records("constructs") or () if item.kind == "numeric_operand"
    )
    evidence = observation.evidence
    inventory_binding = numeric_operand_inventory_binding_id(
        observation.sections, coverage.failures, evidence
    )
    return (
        isinstance(proof, RecordData)
        and {key for key, _ in proof.entries}
        == {
            "source_digest",
            "source_scope",
            "contract_digest",
            "observation_schema_version",
            "scope",
            "selected_files",
            "module_ids",
            "operation_ids",
            "binding_id",
            "result_digest",
        }
        and proof.get("source_digest") == observation.source.source_digest
        and proof.get("source_scope") == observation.source.scope
        and proof.get("contract_digest") == observation.contract.digest
        and proof.get("observation_schema_version") == observation.schema_version
        and proof.get("scope") == receipt.data.get("scope")
        and isinstance(selected_files, tuple)
        and bool(selected_files)
        and all(isinstance(path, str) for path in selected_files)
        and len(set(selected_files)) == len(selected_files)
        and coverage.files_discovered
        == coverage.files_read
        == coverage.files_parsed
        == len(selected_files)
        and set(selected_files) == {item.data.get("file") for item in modules_records}
        and isinstance(module_ids, tuple)
        and module_ids == tuple(sorted(item.id for item in modules_records))
        and isinstance(operation_ids, tuple)
        and operation_ids == tuple(sorted(item.id for item in numeric_records))
        and proof.get("result_digest")
        == rule_result_digest(observation.sections, receipt.rule_ids[0])
        and proof.get("binding_id")
        == rule_evaluation_binding_id(inventory_binding, receipt, observation.schema_version)
    )


def _numeric_receipt_complete(
    observation: Observation, declaration: Record, receipt: Record | None
) -> bool:
    if receipt is None:
        return False
    threshold = declaration.data.get("minimum_value")
    suffix = declaration.data.get("terminal_suffix")
    form = declaration.data.get("form")
    if (
        not isinstance(threshold, int)
        or isinstance(threshold, bool)
        or not isinstance(suffix, str)
        or not isinstance(form, str)
    ):
        return False
    selected = set(receipt.subjects)
    expected_modules = _source_rule_modules(observation, declaration)
    operations = tuple(
        item
        for item in observation.records("constructs") or ()
        if item.kind == "numeric_operand"
        and item.data.get("module") in selected
        and isinstance(subject := item.data.get("subject"), str)
        and subject[len(subject) - len(suffix) :] == suffix
        and form in {"both", item.data.get("form")}
    )
    binding = stable_id(
        "NUMERIC-OPERAND",
        declaration.id,
        json.dumps(
            sorted((item.id, _thaw_data(item.data)) for item in operations),
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return (
        receipt.rule_ids == (declaration.id,)
        and receipt.data.get("assessment_complete") is True
        and receipt.data.get("threshold") == threshold
        and receipt.data.get("terminal_suffix") == suffix
        and receipt.data.get("form") == form
        and bool(selected)
        and selected == expected_modules
        and observation.coverage.status == Verdict.PASS
        and not observation.coverage.failures
        and set(receipt.fact_ids) == {item.id for item in operations}
        and receipt.data.get("operation_binding") == binding
        and _numeric_scope_proven(observation, receipt)
    )


def _rule_receipt_complete(
    observation: Observation, declaration: Record, receipt: Record | None
) -> bool:
    if declaration.kind == "no_component_cycles":
        return receipt is not None and receipt.data.get("cycle_scope_complete") is True
    if declaration.kind in {"call_owner", "forbidden_call_argument"}:
        return (
            receipt is not None
            and receipt.rule_ids == (declaration.id,)
            and _call_owner_receipt_complete(observation, receipt)
        )
    if declaration.kind == "bounded_numeric_operand":
        return _numeric_receipt_complete(observation, declaration, receipt)
    if declaration.kind == "protocol_declarations":
        return (
            receipt is not None
            and receipt.rule_ids == (declaration.id,)
            and _protocol_declaration_receipt_complete(observation, receipt)
        )
    return receipt is not None and receipt.data.get("assessment_complete", True) is True


def _declared_scope_ownership(record: Record) -> ComponentOwnership:
    exact = record.data.get("exact_modules")
    return (
        record.title,
        record.subjects,
        (
            tuple(name for name in exact if isinstance(name, str))
            if isinstance(exact, tuple)
            else ()
        ),
    )


def _source_rule_modules(observation: Observation, declaration: Record) -> frozenset[str]:
    """Rebuild a source selector inside every enclosing physical ownership boundary."""
    source = declaration.data.get("source")
    if not isinstance(source, str):
        return frozenset()
    parent_id = declaration.data.get("parent_id")
    components = tuple(
        item for item in observation.records("declarations") or () if item.kind in _COMPONENT_KINDS
    )
    siblings = tuple(
        _declared_scope_ownership(item)
        for item in components
        if item.data.get("parent_id") == parent_id
    )
    owners = package_owners((label, packages) for label, packages, _ in siblings)
    owner = owners.get(source)
    packages, exact = next(
        ((packages, exact) for label, packages, exact in siblings if label == owner),
        ((source,), ()),
    )
    names = frozenset(
        name
        for item in observation.records("modules") or ()
        if isinstance(name := item.data.get("qualified_name"), str)
        and module_in_ownership(name, packages, exact)
    )
    visited: set[str] = set()
    while parent_id is not None:
        if not isinstance(parent_id, str) or parent_id in visited:
            return frozenset()
        visited.add(parent_id)
        parents = tuple(
            item
            for item in components
            if (
                f"{ancestor}:{item.title}"
                if isinstance(ancestor := item.data.get("parent_id"), str)
                else item.title
            )
            == parent_id
        )
        if len(parents) != 1:
            return frozenset()
        parent = parents[0]
        _, packages, exact = _declared_scope_ownership(parent)
        names = frozenset(name for name in names if module_in_ownership(name, packages, exact))
        parent_id = parent.data.get("parent_id")
    return names


def _dependency_receipt_ownership(
    observation: Observation, declaration: Record, receipt: Record
) -> bool:
    parent_id = declaration.data.get("parent_id")
    declarations = observation.records("declarations") or ()
    parents = [
        item
        for item in declarations
        if item.kind in _COMPONENT_KINDS and (item.id == parent_id or item.title == parent_id)
    ]
    parent = parents[0] if len(parents) == 1 else None
    components = tuple(
        _declared_scope_ownership(item)
        for item in declarations
        if item.kind in _COMPONENT_KINDS and item.data.get("parent_id") == parent_id
    )
    names = {
        str(item.data.get("qualified_name"))
        for item in observation.records("modules") or ()
        if parent_id is None
        or parent is not None
        and module_in_ownership(
            str(item.data.get("qualified_name")),
            *_declared_scope_ownership(parent)[1:],
        )
    }
    return (
        bool(names)
        and set(receipt.subjects) == names
        and all(owner_of(name, components) is not None for name in names)
    )


def dependency_binding_id(
    sections: _Iterable[Section],
    failures: _Iterable[Record],
    evidence: _Iterable[Evidence],
    *,
    include_calls: bool = False,
) -> str:
    """Bind dependency proof content identically at issuance and replay (AD-237)."""
    bound = [
        record
        for section in sections
        for record in section.records
        if section.name in {"modules", "imports", "symbols"}
        or section.name == "references"
        and record.kind == "script_namespace_effect"
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
            and record.kind in {"call_owner", "forbidden_call_argument"}
            or record.kind == "protocol_declarations"
        )
    ]
    bound.extend(failures)
    return stable_id(
        "DEPENDENCY-PROOF",
        repr(
            (
                tuple(sorted(bound, key=lambda item: item.id)),
                tuple(sorted(evidence, key=lambda item: item.id)),
            )
        ),
    )


def numeric_operand_inventory_binding_id(
    sections: _Iterable[Section],
    failures: _Iterable[Record],
    evidence: _Iterable[Evidence],
) -> str:
    """Bind physical modules, numeric operation proofs, declarations and their evidence."""
    bound = [
        record
        for section in sections
        for record in section.records
        if section.name == "modules"
        or section.name == "constructs"
        and record.kind == "numeric_operand"
        or section.name == "declarations"
        and (record.kind == "bounded_numeric_operand" or record.kind in _COMPONENT_KINDS)
    ]
    bound.extend(failures)
    return stable_id(
        "NUMERIC-OPERAND-INVENTORY",
        repr(
            (
                tuple(sorted(bound, key=lambda item: item.id)),
                tuple(sorted(evidence, key=lambda item: item.id)),
            )
        ),
    )


def rule_evaluation_binding_id(
    inventory_binding_id: str, receipt: Record, observation_schema_version: str
) -> str:
    """Bind one evaluator claim without recursively including its own proof."""
    claim = (
        receipt.id,
        receipt.evidence_class,
        receipt.area,
        receipt.kind,
        receipt.title,
        receipt.subjects,
        receipt.evidence_ids,
        receipt.rule_ids,
        receipt.fact_ids,
        receipt.provenance,
        tuple(
            (key, value)
            for key, value in sorted(receipt.data.entries)
            if key not in {"call_scope_proof", "numeric_scope_proof", "protocol_scope_proof"}
        ),
    )
    return stable_id(
        "RULE-EVALUATION-PROOF", observation_schema_version, inventory_binding_id, repr(claim)
    )


def rule_result_digest(sections: _Iterable[Section], rule_id: str) -> str:
    """Bind every rule-linked violation or unknown to its section and complete record."""
    selected = tuple(
        sorted(
            (
                (section.name, record)
                for section in sections
                for record in section.records
                if rule_id in record.rule_ids
                and record.evidence_class in {EvidenceClass.VIOLATION, EvidenceClass.UNKNOWN}
            ),
            key=lambda item: (item[0], item[1].id, repr(item[1])),
        )
    )
    return stable_id("RULE-RESULT", rule_id, repr(selected))


def _native_scope_runtime_valid(runtime: RuntimeInfo) -> bool:
    """Replay only a simple numeric Python lower bound already validated by Core."""
    if (
        runtime.name != "python"
        or runtime.requirement_state != _RuntimeRequirementState.DECLARED
        or runtime.required is None
        or re.fullmatch(r">=[0-9]+\.[0-9]+(?:\.[0-9]+)?", runtime.required) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", runtime.version) is None
    ):
        return False
    actual = tuple(int(value) for value in re.findall(r"[0-9]+", runtime.version))
    lower = tuple(int(value) for value in re.findall(r"[0-9]+", runtime.required))
    return actual >= (*lower, 0)[:3]


def _dependency_gaps_complete(
    observation: Observation,
    receipt: Record,
    module_paths: dict[str, str],
    records: dict[str, Record],
    selected: tuple[JsonValue, ...],
) -> bool:
    evidence = {item.id: item for item in observation.evidence}
    if any(gap.kind != "source_resolution_gap" for gap in observation.coverage.failures):
        return False
    try:
        validate_source_bindings(
            observation.coverage.failures,
            module_paths,
            {},
            evidence,
            import_ids=(),
            selected_inputs=tuple(str(path) for path in selected),
            source_records=records,
            allow_script_effects=observation.analyzer.name == _SourceProfile.TYPESCRIPT,
        )
    except ValueError:
        return False
    return all(
        records.get(gap.id) == gap
        and not (
            gap.data.get("resolution_dimension") == "imports"
            and gap.data.get("source_module", gap.data.get("module")) in receipt.subjects
        )
        for gap in observation.coverage.failures
    )


def _scoped_dependency_receipt(
    observation: Observation, declaration: Record, receipt: Record | None
) -> bool:
    """Replay an explicit Core proof; old receipts cannot override incomplete observation."""
    if (
        declaration.kind != "complete_requires"
        or receipt is None
        or not _dependency_receipt_ownership(observation, declaration, receipt)
    ):
        return False
    proof = receipt.data.get("dependency_scope_proof")
    runtime = observation.runtime
    coverage = observation.coverage
    if (
        not isinstance(proof, RecordData)
        or runtime is None
        or not _native_scope_runtime_valid(runtime)
        or coverage.rules != Verdict.PASS
        or proof.get("source_digest") != observation.source.source_digest
        or proof.get("contract_digest") != observation.contract.digest
        or proof.get("binding_id")
        != dependency_binding_id(observation.sections, coverage.failures, observation.evidence)
        or proof.get("runtime")
        != RecordData(
            (
                ("name", runtime.name),
                ("required", runtime.required),
                ("requirement_state", runtime.requirement_state),
                ("version", runtime.version),
            )
        )
    ):
        return False
    selected = proof.get("selected_files")
    if (
        not isinstance(selected, tuple)
        or not selected
        or any(not isinstance(path, str) for path in selected)
        or len(set(selected)) != len(selected)
        or coverage.files_discovered != len(selected)
        or coverage.files_read != len(selected)
        or coverage.files_parsed != len(selected)
        or proof.get("gap_ids") != tuple(sorted(gap.id for gap in coverage.failures))
        or not coverage.failures
    ):
        return False
    records = {record.id: record for section in observation.sections for record in section.records}
    modules = observation.records("modules") or ()
    if proof.get("module_ids") != tuple(sorted(record.id for record in modules)) or proof.get(
        "import_ids"
    ) != tuple(sorted(record.id for record in observation.records("imports") or ())):
        return False
    paths = {record.data.get("qualified_name"): record.data.get("file") for record in modules}
    if any(
        not isinstance(name, str) or not isinstance(path, str) or path not in selected
        for name, path in paths.items()
    ):
        return False
    module_paths = {str(name): str(path) for name, path in paths.items()}
    evaluated = [record for record in modules if record.id in receipt.fact_ids]
    if (
        not evaluated
        or len(evaluated) != len(receipt.fact_ids)
        or set(receipt.subjects) != {record.data.get("qualified_name") for record in evaluated}
    ):
        return False
    return _dependency_gaps_complete(observation, receipt, module_paths, records, selected)


def _rule_scope_complete(
    observation: Observation, declaration: Record, receipt: Record | None, complete: bool
) -> bool:
    return (complete and observation.coverage.status == Verdict.PASS) or _scoped_dependency_receipt(
        observation, declaration, receipt
    )


def _call_owner_receipt_complete(observation: Observation, receipt: Record | None) -> bool:
    if receipt is None or not isinstance(
        (proof := receipt.data.get("call_scope_proof")), RecordData
    ):
        return False
    coverage = observation.coverage
    selected = proof.get("selected_files")
    return (
        coverage.status == Verdict.PASS
        and not coverage.failures
        and bool(receipt.rule_ids)
        and proof.get("result_digest")
        == rule_result_digest(observation.sections, receipt.rule_ids[0])
        and isinstance(selected, tuple)
        and bool(selected)
        and coverage.files_discovered
        == coverage.files_read
        == coverage.files_parsed
        == len(selected)
        and len(set(selected)) == len(selected)
        and set(selected) == {r.data.get("file") for r in observation.records("modules") or ()}
        and proof.get("source_digest") == observation.source.source_digest
        and proof.get("source_scope") == observation.source.scope
        and proof.get("contract_digest") == observation.contract.digest
        and proof.get("binding_id")
        == rule_evaluation_binding_id(
            dependency_binding_id(
                observation.sections, coverage.failures, observation.evidence, include_calls=True
            ),
            receipt,
            observation.schema_version,
        )
    )


def protocol_declaration_result_digest(records: _Iterable[Record], rule_id: str) -> str:
    """Bind protocol declaration verdicts to their source-derived result records."""
    selected = tuple(
        sorted(
            (
                record.kind,
                record.id,
                record.evidence_class,
                record.area,
                record.title,
                record.subjects,
                record.evidence_ids,
                record.rule_ids,
                record.fact_ids,
                record.provenance,
                record.data,
            )
            for record in records
            if rule_id in record.rule_ids
            and record.kind in {"protocol_declaration", "protocol_declaration_limit"}
        )
    )
    return stable_id("PROTOCOL-DECLARATION-RESULT", rule_id, repr(selected))


def _protocol_declaration_receipt_complete(observation: Observation, receipt: Record) -> bool:
    proof = receipt.data.get("protocol_scope_proof")
    if not isinstance(proof, RecordData):
        return False
    coverage = observation.coverage
    selected = proof.get("selected_files")
    records = tuple(record for section in observation.sections for record in section.records)
    rule_id = receipt.rule_ids[0]
    return (
        coverage.status == Verdict.PASS
        and not coverage.failures
        and isinstance(selected, tuple)
        and bool(selected)
        and coverage.files_discovered
        == coverage.files_read
        == coverage.files_parsed
        == len(selected)
        and len(set(selected)) == len(selected)
        and set(selected) == {r.data.get("file") for r in observation.records("modules") or ()}
        and proof.get("source_digest") == observation.source.source_digest
        and proof.get("source_scope") == observation.source.scope
        and proof.get("contract_digest") == observation.contract.digest
        and all(
            section.name == "violations"
            if record.kind == "protocol_declaration"
            else section.name == "unknowns"
            for section in observation.sections
            for record in section.records
            if rule_id in record.rule_ids
            and record.kind in {"protocol_declaration", "protocol_declaration_limit"}
        )
        and proof.get("result_digest") == protocol_declaration_result_digest(records, rule_id)
        and proof.get("binding_id")
        == rule_evaluation_binding_id(
            dependency_binding_id(observation.sections, coverage.failures, observation.evidence),
            receipt,
            observation.schema_version,
        )
    )


def rule_assessments(
    observation: Observation,
    *,
    undecided_by_rule: _Mapping[str, int],
    complete: bool = True,
) -> tuple[RuleAssessment, ...]:
    """Project evaluator receipts and findings into one row per declared rule."""
    records = {record.id: record for section in observation.sections for record in section.records}
    declarations = [
        record
        for record in records.values()
        if record.evidence_class == EvidenceClass.DECLARED_RULE and record.kind in RULE_RECORD_KINDS
    ]
    violations: _Counter[str] = _Counter(
        rule_id for record in observation.records("violations") or () for rule_id in record.rule_ids
    )
    components = [record for record in records.values() if record.kind in _COMPONENT_KINDS]
    receipts = {
        record.rule_ids[0]: record
        for record in observation.records("scope_observations") or ()
        if record.kind == "rule_evaluation" and record.rule_ids
    }
    rows: list[RuleAssessment] = []
    for declaration in declarations:
        identifier = declaration.id
        undecided = undecided_by_rule.get(identifier, 0)
        violation_count = violations[identifier]
        receipt = receipts.get(identifier)
        receipt_complete = _rule_receipt_complete(observation, declaration, receipt)
        scope_complete = _rule_scope_complete(observation, declaration, receipt, complete)
        evaluation_proven = scope_complete and receipt_complete
        declared_only = declaration.kind == "allowed_dependency"
        status, reason = _rule_status(
            declared_only=declared_only,
            violations=violation_count,
            complete=scope_complete,
            receipt=receipt_complete,
            undecided=undecided,
        )
        if declaration.kind == "layer_order" and status == RuleAssessmentStatus.PASS:
            reason = "Declared requires permissions follow the selected layer order."
        if status == RuleAssessmentStatus.UNKNOWN and scope_complete and not receipt_complete:
            ownership_reason = _ownership_blocker_reason(observation, identifier)
            if ownership_reason is not None:
                reason = ownership_reason
        parent_id = declaration.data.get("parent_id")
        scope = str(parent_id) if isinstance(parent_id, str) else "root"
        parent = records.get(scope)
        if parent is not None:
            scope = parent.title
        rule_components = {
            component.title
            for component in components
            if component.id == parent_id
            or any(
                in_scope(subject, package)
                for subject in declaration.subjects
                for package in component.subjects
            )
        }
        decided_by = declaration.data.get("decided_by", "UNKNOWN")
        rationale = declaration.data.get("rationale", "")
        rows.append(
            RuleAssessment(
                identifier,
                declaration.kind,
                status,
                evaluation_proven,
                violation_count,
                undecided,
                decided_by if isinstance(decided_by, str) else "UNKNOWN",
                rationale if isinstance(rationale, str) else "",
                declaration.provenance,
                reason,
                scope,
                tuple(sorted(rule_components)),
            )
        )
    return tuple(sorted(rows, key=lambda item: (item.scope, item.id)))


def rule_assessment_applies_to_component(
    assessment: RuleAssessment,
    rule_parent_id: str | None,
    component_parent_id: str | None,
    component_label: str | None,
) -> bool:
    """Whether Core's evaluated rule scope includes one authenticated component."""
    return rule_parent_id == component_parent_id and (
        not assessment.components
        or component_label is not None
        and component_label in assessment.components
    )


def cycle_scope_receipt_covers(
    fingerprint: _ViolationFingerprint, rule_id: str, observation: Observation
) -> bool:
    """Whether the selected cycle rule covered an SCC inside its evaluated graph."""
    rule = next(
        (
            record
            for record in observation.records("declarations") or ()
            if record.id == rule_id and record.kind == "no_component_cycles"
        ),
        None,
    )
    if rule is None:
        return False
    component_cycle = rule.data.get("level") is None
    for receipt in observation.records("scope_observations") or ():
        if (
            receipt.kind != "rule_evaluation"
            or rule_id not in receipt.rule_ids
            or receipt.data.get("cycle_scope_complete") is not True
        ):
            continue
        if component_cycle:
            selected = receipt.data.get("cycle_scope_components")
            graph = receipt.data.get("cycle_graph_components")
            if (
                isinstance(selected, (list, tuple))
                and all(isinstance(item, str) for item in selected)
                and isinstance(graph, (list, tuple))
                and all(isinstance(item, str) for item in graph)
                and set(fingerprint.subjects) & set(selected)
                and set(fingerprint.subjects) <= set(graph)
            ):
                return True
        elif set(fingerprint.subjects) & set(receipt.subjects) and set(
            fingerprint.subjects
        ) <= _evaluated_module_names(receipt, observation):
            return True
    return False


def _evaluated_module_names(receipt: Record, observation: Observation) -> set[str]:
    fact_ids = set(receipt.fact_ids)
    return {
        module
        for record in observation.records("modules") or ()
        if record.id in fact_ids and isinstance((module := record.data.get("qualified_name")), str)
    }


def baseline_fingerprint_covered(
    fingerprint: _ViolationFingerprint,
    roles: tuple[tuple[str, str], ...],
    observation: Observation,
    assessments: _Mapping[str, RuleAssessment],
) -> bool:
    """Require current evaluator evidence for every prior subject being resolved."""
    receipts = {
        rule_id: tuple(
            record
            for record in observation.records("scope_observations") or ()
            if record.kind == "rule_evaluation" and rule_id in record.rule_ids
        )
        for rule_id in fingerprint.rules
    }
    if not all(
        (assessment := assessments.get(rule_id)) is not None
        and assessment.evaluation_proven
        and assessment.status in {RuleAssessmentStatus.PASS, RuleAssessmentStatus.FAIL}
        and assessment.undecided == 0
        and receipts[rule_id]
        for rule_id in fingerprint.rules
    ):
        return False
    modules = {
        module: record
        for record in observation.records("modules") or ()
        if isinstance((module := record.data.get("qualified_name")), str)
    }
    subjects = {source for source, _ in roles} if roles else set(fingerprint.subjects)
    cycles = {
        record.id: record
        for record in observation.records("declarations") or ()
        if record.kind == "no_component_cycles"
    }
    for rule_id in fingerprint.rules:
        if rule_id not in cycles:
            for subject in subjects:
                if not any(
                    subject in receipt.subjects
                    or any(
                        subject.startswith(f"{module}.")
                        and module in receipt.subjects
                        and _PurePosixPath(str(modules[module].data.get("file", ""))).name
                        != "__init__.py"
                        for module in modules
                        if module in receipt.subjects
                    )
                    for receipt in receipts[rule_id]
                ):
                    return False
        elif not cycle_scope_receipt_covers(fingerprint, rule_id, observation):
            return False
    return True


def dependency_rule_ids(source: str, target: str) -> tuple[str, str]:
    """Return the `(forbidden, allowed)` rule ids AD-15 gives one directed component pair.

    The only owner of this id scheme: `init`, every open-decision option, and a
    hand-written `forbidden_dependency` or `allowed_dependency` rule all agree with this
    function by construction, never by convention.
    """
    return (
        f"DEP-{identifier(source)}-NO-{identifier(target)}",
        f"DEP-{identifier(source)}-ALLOWS-{identifier(target)}",
    )
