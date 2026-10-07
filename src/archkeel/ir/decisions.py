# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive undecided component pairs from one observation alone (AD-15).

One function reads the projected dependency decisions and the observed component edges, so
validation and a report rendered later from `architecture.json` bytes share one derivation.
"""

from __future__ import annotations

from collections import Counter as _Counter
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath as _PurePosixPath
from typing import Final as _Final

from .baseline import ViolationFingerprint as _ViolationFingerprint
from .baseline import violation_rows
from .bindings import unread_bindings
from .duplication import repeated_logic
from .interfaces import component_owners, owner_of
from .measurements import RatchetError
from .model import (
    RULE_RECORD_KINDS,
    AllowedDependencyRule,
    ComparisonStatus,
    ComponentOwnership,
    ComponentOwnershipInput,
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
    ViolationCounts,
    declared_package_pair,
    in_scope,
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
    records_by_rule = {rule_id: list(records) for rule_id, records in unknown_evidence.items()}
    ownership_blockers = tuple(
        record
        for record in observation.records("scope_observations") or ()
        if record.kind == "rule_ownership_blocker"
    )
    for record in (*ownership_blockers, *observation.coverage.failures):
        for rule_id in record.rule_ids:
            records_by_rule.setdefault(rule_id, []).append(record)
    if observation.coverage.status != "PASS" or observation.coverage.failures:
        for declaration in observation.records("declarations") or ():
            if (
                declaration.evidence_class == EvidenceClass.DECLARED_RULE
                and declaration.kind in RULE_RECORD_KINDS
            ):
                records_by_rule.setdefault(declaration.id, [])

    result: dict[str, RuleUncertainty] = {}
    for rule_id, records in sorted(records_by_rule.items()):
        actions = {_rule_uncertainty_action(record) for record in records}
        if observation.coverage.status != "PASS" or observation.coverage.failures:
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
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS or not _decides_this_level(record):
            continue
        source_module = record.data.get("source")
        target_module = record.data.get("target")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        target_symbol = record.data.get("target_symbol")
        if target_symbol is not None and not isinstance(target_symbol, str):
            continue
        pair = declared_package_pair(
            source_module,
            target_module,
            target_symbol,
            components,
        )
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
            "forbidden_dependency",
            source_package,
            target_package,
            True,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
        ),
        AllowedDependencyRule(
            allowed_id,
            "allowed_dependency",
            source_package,
            target_package,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
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


def requires_declared(observation: Observation) -> bool:
    """True when a `complete_requires` rule decides every component pair by absence (AD-32)."""
    return any(
        record.kind == "complete_requires" and _decides_this_level(record)
        for record in observation.records("declarations") or ()
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
    if requires_declared(observation):
        return ()
    resolved = (
        component_owners(observation)
        if components is None
        else _ownership_with_exact_modules(components)
    )
    package_selectors = tuple((label, packages) for label, packages, _ in resolved if packages)
    packages = dict(package_selectors)
    labels = {label for label, _, _ in resolved}
    expected = {(source, target) for source in labels for target in labels if source != target}
    decided = _decided_component_pairs(observation, resolved)
    sites = _component_import_sites(observation, resolved)
    declarations = {label: component for component in resolved for label in (component[0],)}
    return tuple(
        sorted(
            (
                (
                    _open_decision(source, target, packages, sites[(source, target)])
                    if not declarations[source][2] and not declarations[target][2]
                    else _exact_open_decision(source, target, declarations, sites[(source, target)])
                )
                for source, target in expected - decided
            ),
            key=lambda item: (-item.import_sites, item.source, item.target),
        )
    )


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
    return len(candidates) if status == "SUPPORTED" else None


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
        return "DECLARATION", "Permission declaration; it does not evaluate conformance."
    if violations:
        return "FAIL", "The evaluator recorded one or more violations."
    if not complete:
        return "UNKNOWN", "The observation is incomplete; a complete evaluator scope is not proven."
    if not receipt:
        return "UNKNOWN", "No complete evaluator receipt exists for this rule and scope."
    if undecided:
        return "UNKNOWN", "The evaluator left one or more positions undecided."
    return "PASS", "The evaluator completed this rule's observed scope without violations."


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


def _rule_receipt_complete(declaration: Record, receipt: Record | None) -> bool:
    if declaration.kind == "no_component_cycles":
        return receipt is not None and receipt.data.get("cycle_scope_complete") is True
    return receipt is not None and receipt.data.get("assessment_complete", True) is True


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
        if record.evidence_class.value == "DECLARED_RULE" and record.kind in RULE_RECORD_KINDS
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
        receipt_complete = _rule_receipt_complete(declaration, receipt)
        evaluation_proven = complete and receipt_complete
        declared_only = declaration.kind == "allowed_dependency"
        status, reason = _rule_status(
            declared_only=declared_only,
            violations=violation_count,
            complete=complete,
            receipt=receipt_complete,
            undecided=undecided,
        )
        if declaration.kind == "layer_order" and status == "PASS":
            reason = "Declared requires permissions follow the selected layer order."
        if status == "UNKNOWN" and complete and not receipt_complete:
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
        and assessment.status in {"PASS", "FAIL"}
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
