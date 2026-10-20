# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import ast
import subprocess
from collections import Counter as _Counter
from dataclasses import replace
from pathlib import Path
from typing import Literal as _Literal

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    ComponentIntent,
    RuleAssessment,
)
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.baseline import (
    ViolationFingerprint,
    cycle_contractions,
    observed_violations,
    require_declared_filter,
    select_violations,
)
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    decode_json,
    parse_observation,
    parse_validation_baseline,
    result_bytes,
)
from archkeel.ir.decisions import (
    agent_decisions,
    baseline_fingerprint_covered,
    cycle_scope_receipt_covers,
    open_decisions,
    review_claims,
    rule_assessment_applies_to_component,
    rule_assessments,
    violation_counts,
)
from archkeel.ir.diagnostics import Diagnostic as Diagnostic
from archkeel.ir.diagnostics import DiagnosticError as DiagnosticError
from archkeel.ir.diagnostics import ReportLocation as ReportLocation
from archkeel.ir.facts import (
    CallBinding,
    CallBindingOrigin,
    Evidence,
    JsonValue,
    Record,
    RecordData,
    SourceSectionName,
    call_binding,
)
from archkeel.ir.facts_codec import (
    selector_receiver_site_matches,
)
from archkeel.ir.facts_validation import validate_source_bindings
from archkeel.ir.model import (
    AssessmentStatus as _AssessmentStatus,
)
from archkeel.ir.model import (
    BaselineViolationComparison,
    CallRow,
    EvidenceClass,
    FilteredViolation,
    Observation,
    ObservationResult,
    ReportFilter,
    RunResult,
)
from archkeel.ir.model import (
    Command as _Command,
)
from archkeel.ir.model import DiagnosticKind as _DiagnosticKind
from archkeel.ir.model import (
    ExpectationOutcome as _ExpectationOutcome,
)
from archkeel.ir.model import (
    RuleAssessmentStatus as _RuleAssessmentStatus,
)
from archkeel.ir.profiles import PROFILES
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.ir.trace import trace_valid_violations, validate_evidence_classes

# Retain the published report bindings while their implementation lives below commands.
from .git import git_bytes as git_bytes
from .observe import observation_diagnostics
from .ports import Analyzer, ScanConfig
from .ratchets import call_rows, calls_measured, unknown_positions_by_rule
from .run import inspect_observation
from .runtime import runtime_diagnostic
from .snapshot import resolve_commit as resolve_commit
from .uml import assemble_uml as assemble_uml
from .uml import (
    observe_repository as _observe_repository,
)
from .uml import (
    revoke_dependency_proofs as _revoke_dependency_proofs,
)
from .uml import (
    validated_member_inventory_result as _validated_member_inventory_result,
)
from .uml_evaluation import evaluate_uml as evaluate_uml

VIOLATION_REMEDY = "Change the code or amend the contract with owner approval."


def _baseline_report(
    root: Path,
    baseline: Path,
    model: Observation,
    current_rules: dict[str, RuleAssessment],
) -> tuple[str, tuple[BaselineViolationComparison, ...]]:
    baseline_file = baseline if baseline.is_absolute() else root / baseline
    baseline_file = baseline_file.resolve()
    try:
        baseline_file.relative_to(root.resolve())
        known = parse_validation_baseline(decode_json(baseline_file.read_bytes()))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read baseline {baseline}: {error}") from error
    known_counts: _Counter[ViolationFingerprint] = _Counter(
        {item.fingerprint: item.count for item in known.violations}
    )
    known_roles = {item.fingerprint: item.roles for item in known.violations}
    current = observed_violations(model)
    current_counts: _Counter[ViolationFingerprint] = _Counter(
        {item.fingerprint: item.count for item in current}
    )
    cycle_rules = frozenset(
        record.id
        for record in model.records("declarations") or ()
        if record.kind == "no_component_cycles"
        and any(
            cycle_scope_receipt_covers(item.fingerprint, record.id, model)
            for item in (*known.violations, *current)
            if record.id in item.fingerprint.rules
        )
    )
    scoped_cycles = tuple(
        item
        for item in (*known.violations, *current)
        if item.fingerprint.rules
        and all(
            rule in cycle_rules and cycle_scope_receipt_covers(item.fingerprint, rule, model)
            for rule in item.fingerprint.rules
        )
    )
    known_cycles = tuple(item for item in scoped_cycles if item in known.violations)
    current_cycles = tuple(item for item in scoped_cycles if item in current)
    contracted = cycle_contractions(known_cycles, current_cycles, cycle_rules=cycle_rules)
    comparisons = _baseline_comparisons(
        known_counts,
        current_counts,
        known_roles,
        contracted,
        current_rules,
        model,
    )
    return str(baseline_file.relative_to(root.resolve())), comparisons


def _baseline_comparisons(
    known_counts: _Counter[ViolationFingerprint],
    current_counts: _Counter[ViolationFingerprint],
    known_roles: dict[ViolationFingerprint, tuple[tuple[str, str], ...]],
    contracted: frozenset[ViolationFingerprint],
    current_rules: dict[str, RuleAssessment],
    model: Observation,
) -> tuple[BaselineViolationComparison, ...]:
    return tuple(
        BaselineViolationComparison(
            fingerprint.rules,
            fingerprint.subjects,
            before,
            min(before, after),
            after,
            0 if fingerprint in contracted else max(after - before, 0),
            max(before - after, 0)
            if baseline_fingerprint_covered(
                fingerprint, known_roles.get(fingerprint, ()), model, current_rules
            )
            else 0,
            _baseline_status(
                fingerprint,
                before,
                after,
                contracted,
                known_roles.get(fingerprint, ()),
                model,
                current_rules,
            ),
        )
        for fingerprint in sorted(
            known_counts.keys() | current_counts.keys(),
            key=lambda item: (item.rules, item.subjects),
        )
        for before, after in (
            (known_counts.get(fingerprint, 0), current_counts.get(fingerprint, 0)),
        )
    )


def _baseline_status(
    fingerprint: ViolationFingerprint,
    before: int,
    after: int,
    contracted: frozenset[ViolationFingerprint],
    roles: tuple[tuple[str, str], ...],
    model: Observation,
    current_rules: dict[str, RuleAssessment],
) -> _Literal["known", "new", "reduced", "resolved", "contracted", "unknown"]:
    if after < before and not baseline_fingerprint_covered(
        fingerprint, roles, model, current_rules
    ):
        return "unknown"
    if fingerprint in contracted:
        return "contracted"
    if after > before:
        return "new"
    if after == 0 and before > 0:
        return "resolved"
    if after < before:
        return "reduced"
    return "known"


def unknown_result(command: _Command, subject: str, error: Exception) -> RunResult:
    if isinstance(error, DiagnosticError):
        diagnostic = error.diagnostic
    else:
        diagnostic = Diagnostic(
            _DiagnosticKind.TIMEOUT
            if isinstance(error, subprocess.TimeoutExpired)
            else _DiagnosticKind.PARSE_ERROR,
            subject,
            f"The {command} result cannot be established: {error}",
            "Repair the reported input or execution failure and retry.",
        )
    return RunResult(command, 2, diagnostics=(diagnostic,))


def render_result(result: RunResult) -> bytes:
    return result_bytes(result)


def observe_repository(
    root: Path, config: ScanConfig, analyzer: Analyzer, *, contract_root: Path | None = None
) -> ObservationResult:
    """Retain the published facade signature while observation lives below commands."""
    return _observe_repository(root, config, analyzer, contract_root=contract_root)


def _selected_violations(
    model: Observation, report_filter: ReportFilter
) -> tuple[FilteredViolation, ...]:
    return tuple(
        FilteredViolation(
            record,
            tuple(
                ReportLocation(entry.file, entry.line)
                for entry in model.evidence
                if entry.id in record.evidence_ids
            ),
        )
        for record in select_violations(model, report_filter)
    )


def _selected_calls(model: Observation, report_filter: ReportFilter) -> tuple[CallRow, ...]:
    """AD-100: `--only calls`, narrowed by `--component` to the calls its modules make.

    A profile that does not measure calls has none to list, and an empty list would read as a
    count it never took: refused like an unsupported rule (AD-97).
    """
    if not calls_measured(model):
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE,
                "--only calls",
                f"The {model.analyzer.name} profile does not measure calls, so it has none "
                "to list.",
                "Drop --only calls; only the Python profile lists unresolved calls.",
            )
        )
    require_declared_filter(model, report_filter)
    return tuple(
        row
        for row in call_rows(model)
        if report_filter.component is None or row.component == report_filter.component
    )


def _report_filter(
    only_violations: bool,
    rule: str | None,
    component: str | None,
    only_calls: bool,
    only_architecture: bool = False,
    full_architecture: bool = False,
) -> ReportFilter | None:
    if (
        only_violations
        or only_calls
        or only_architecture
        or full_architecture
        or rule is not None
        or component is not None
    ):
        return ReportFilter(
            only_violations,
            rule,
            component,
            only_calls,
            only_architecture,
            full_architecture,
        )
    return None


def _incomplete_report_result(result: ObservationResult) -> RunResult:
    model = result.observation
    declared = _AssessmentStatus.UNKNOWN
    if (
        model is not None
        and model.runtime is not None
        and runtime_diagnostic(model.runtime) is None
        and not any(
            item.kind
            in {
                _DiagnosticKind.CONTRACT_INVALID,
                _DiagnosticKind.RUNTIME_MISMATCH,
                _DiagnosticKind.INCOMPARABLE_RUNTIME,
            }
            for item in result.diagnostics
        )
    ):
        try:
            if trace_valid_violations(model):
                declared = _AssessmentStatus.FAIL
        except ValueError:
            pass
    return RunResult(
        _Command.REPORT,
        2,
        diagnostics=result.diagnostics,
        coverage=result.coverage,
        declared_rules=declared,
        python_version=model.python_version if model is not None else None,
        rule_assessments=(
            rule_assessments(
                model,
                undecided_by_rule=unknown_positions_by_rule(model),
                complete=False,
            )
            if model is not None
            else None
        ),
    )


def _scope_report_assessments(
    result: RunResult,
    report_filter: ReportFilter | None,
    component_rules: set[str],
) -> RunResult:
    if report_filter is None or result.rule_assessments is None:
        return result
    finding_rules = {
        rule_id for item in result.filtered_violations or () for rule_id in item.record.rule_ids
    }
    if report_filter.rule is not None or report_filter.component is not None:
        selected_rules = (
            {report_filter.rule}
            if report_filter.rule is not None and report_filter.component is None
            else {report_filter.rule} & (finding_rules | component_rules)
            if report_filter.rule is not None
            else finding_rules | component_rules
        )
        assessments = tuple(
            item
            for item in result.rule_assessments
            if item.id in selected_rules
            and (
                not report_filter.only_violations
                or item.status in {_RuleAssessmentStatus.FAIL, _RuleAssessmentStatus.UNKNOWN}
            )
        )
        return replace(result, rule_assessments=assessments)
    if report_filter.only_violations:
        return replace(
            result,
            rule_assessments=tuple(
                item
                for item in result.rule_assessments
                if item.status in {_RuleAssessmentStatus.FAIL, _RuleAssessmentStatus.UNKNOWN}
            ),
        )
    return result


def _component_rule_assessment_ids(
    target: ArchitectureGraph,
    projection: ArchitectureProjection,
    component_ids: tuple[str, ...],
) -> set[str]:
    intents = {item.component_id: item for item in target.component_intents}
    scoped_components = tuple(
        intent
        for intent in target.component_intents
        if any(
            component_id in intents
            and _component_is_within(intents, intent.component_id, component_id)
            for component_id in component_ids
        )
    )
    return {
        rule.assessment.id
        for rule in projection.permission_rules
        if rule.assessment is not None
        and any(
            rule_assessment_applies_to_component(
                rule.assessment,
                rule.parent_id,
                intent.parent_id,
                intent.label,
            )
            for intent in scoped_components
        )
    }


def _component_is_within(
    intents: dict[str, ComponentIntent], component_id: str, ancestor_id: str
) -> bool:
    parent: str | None = component_id
    while parent is not None and parent != ancestor_id:
        parent = intents[parent].parent_id
    return parent == ancestor_id


def _selected_finding_rules(report: ArchitectureReport, finding_ids: set[str]) -> set[str]:
    return {
        rule_id
        for finding in report.findings
        if finding.id in finding_ids
        for rule_id in finding.rule_ids
    }


def _selected_finding_ids(
    report: ArchitectureReport, projection: ArchitectureProjection, component: str | None
) -> set[str]:
    if component is None:
        return {item.id for item in report.findings}
    return {identity for owner in projection.components for identity in owner.finding_ids}


def _architecture_result(
    model: Observation,
    command_result: RunResult,
    report_filter: ReportFilter | None,
    *,
    require_source_graph: bool = False,
) -> RunResult:
    only_violations = report_filter is not None and report_filter.only_violations
    only_architecture = report_filter is not None and report_filter.only_architecture
    component = report_filter.component if report_filter is not None else None
    complete = command_result.observation_complete is _AssessmentStatus.PASS
    findings_available = complete or command_result.declared_rules == "FAIL"
    component_rules: set[str] = set()
    try:
        selected_violations = (
            _selected_violations(model, replace(report_filter, component=None))
            if findings_available and only_violations and report_filter is not None
            else ()
        )
        report = architecture_report(model)
        if require_source_graph and report.unavailable is not None:
            raise ValueError(f"Recorded source graph is invalid: {report.unavailable}")
        projection = architecture_projection(
            model,
            report,
            command_result.rule_assessments or (),
            violation_remedy=VIOLATION_REMEDY,
            component=component if only_architecture or only_violations else None,
            prefer_top_label=only_violations,
        )
        selected_components = (
            projection.components
            if only_architecture or only_violations
            else tuple(
                item
                for item in projection.components
                if component is not None and item.parent_id is None and item.label == component
            )
        )
        if component is not None and selected_components and report.target is not None:
            component_rules = _component_rule_assessment_ids(
                report.target, projection, tuple(item.id for item in selected_components)
            )
        finding_ids = _selected_finding_ids(report, projection, component)
        if only_architecture or only_violations:
            component_rules |= _selected_finding_rules(report, finding_ids)
        command_result = replace(
            command_result,
            report_filter=report_filter,
            architecture_projection=projection,
            filtered_violations=None
            if not findings_available
            else tuple(item for item in selected_violations if item.record.id in finding_ids)
            if only_violations
            else tuple(
                FilteredViolation(
                    record,
                    tuple(
                        ReportLocation(entry.file, entry.line)
                        for entry in model.evidence
                        if entry.id in record.evidence_ids
                    ),
                )
                for record in model.records("violations") or ()
                if record.id in finding_ids
            )
            if only_architecture
            else command_result.filtered_violations,
        )
    except ValueError as error:
        command_result = replace(
            unknown_result(_Command.REPORT, "architecture projection", error),
            coverage=model.coverage,
            python_version=model.python_version,
        )
    return _scope_report_assessments(command_result, report_filter, component_rules)


def _projection_result(result: ObservationResult) -> ObservationResult:
    if any(
        item.kind
        in {
            _DiagnosticKind.CONTRACT_INVALID,
            _DiagnosticKind.RUNTIME_MISMATCH,
            _DiagnosticKind.INCOMPARABLE_RUNTIME,
        }
        for item in result.diagnostics
    ):
        return _revoke_dependency_proofs(result)
    return result


def _report_result(
    result: ObservationResult,
    report_filter: ReportFilter | None,
    *,
    baseline_root: Path | None = None,
    baseline: Path | None = None,
    require_source_graph: bool = False,
) -> RunResult:
    only_calls = report_filter is not None and report_filter.only_calls
    result = _projection_result(result)
    model = result.observation
    if result.diagnostics or model is None:
        command_result = _incomplete_report_result(result)
    else:
        try:
            measurements, declared = inspect_observation(model)
            filtered_violations = (
                _selected_violations(model, report_filter)
                if report_filter is not None
                and not only_calls
                and not report_filter.only_architecture
                and not report_filter.only_violations
                else None
            )
            filtered_calls = (
                _selected_calls(model, report_filter)
                if report_filter is not None and only_calls
                else None
            )
        except ValueError as error:
            command_result = replace(
                unknown_result(_Command.REPORT, "observation", error),
                coverage=model.coverage,
                python_version=model.python_version,
            )
        else:
            counted = violation_counts(model)
            assessments = rule_assessments(
                model, undecided_by_rule=unknown_positions_by_rule(model)
            )
            current_rules = {item.id: item for item in assessments}
            comparisons: tuple[BaselineViolationComparison, ...] | None = None
            baseline_name: str | None = None
            if baseline is not None:
                if baseline_root is None:
                    raise ValueError("a baseline needs a repository root")
                baseline_name, comparisons = _baseline_report(
                    baseline_root, baseline, model, current_rules
                )
            command_result = RunResult(
                _Command.REPORT,
                0,
                observation_complete=_AssessmentStatus.PASS,
                declared_rules=declared,
                expectation_fulfilled=_ExpectationOutcome.NOT_APPLICABLE,
                coverage=model.coverage,
                measurements=measurements,
                python_version=model.python_version,
                agent_decisions=agent_decisions(model),
                open_decisions=open_decisions(model),
                claims=review_claims(model),
                violations_by_rule=counted.by_rule,
                violations_by_component_pair=counted.by_component_pair,
                report_filter=report_filter,
                observation=model
                if report_filter
                and report_filter.only_architecture
                and report_filter.full_architecture
                else None,
                filtered_violations=filtered_violations,
                filtered_calls=filtered_calls,
                rule_assessments=assessments,
                baseline_path=baseline_name,
                baseline_comparisons=comparisons,
            )
    if model is not None:
        command_result = _architecture_result(
            model, command_result, report_filter, require_source_graph=require_source_graph
        )
    return command_result


def run_report(
    root: Path,
    *,
    config: ScanConfig,
    analyzer: Analyzer,
    only_violations: bool = False,
    rule: str | None = None,
    component: str | None = None,
    only_calls: bool = False,
    only_architecture: bool = False,
    full_architecture: bool = False,
    baseline: Path | None = None,
) -> tuple[RunResult, bytes | None]:
    """Observe once; filters narrow report rows without changing verdicts or measurements."""
    report_filter = _report_filter(
        only_violations,
        rule,
        component,
        only_calls,
        only_architecture,
        full_architecture,
    )
    result = _projection_result(observe_repository(root, config, analyzer))
    result = _validated_member_inventory_result(result)
    architecture = (
        canonical_report_bytes(result.observation) if result.observation is not None else None
    )
    return _report_result(
        result, report_filter, baseline_root=root, baseline=baseline
    ), architecture


def run_saved_report(
    path: Path,
    *,
    only_violations: bool = False,
    rule: str | None = None,
    component: str | None = None,
    only_calls: bool = False,
    only_architecture: bool = False,
    full_architecture: bool = False,
) -> RunResult:
    """Query recorded evidence without collecting, evaluating or writing a working tree."""
    report_filter = _report_filter(
        only_violations,
        rule,
        component,
        only_calls,
        only_architecture,
        full_architecture,
    )
    try:
        raw = decode_json(path.read_bytes())
        if not isinstance(raw, dict):
            raise ValueError("architecture.json must be an object")
        model = parse_observation(decode_canonical_model(raw))
        validate_evidence_classes(model)
        _validate_saved_sources(model)
        runtime = runtime_diagnostic(model.runtime) if model.runtime is not None else None
        language = next(
            language
            for language, profile in PROFILES.items()
            if profile.analyzer == model.analyzer.name
        )

        diagnostics = observation_diagnostics(model, runtime, language)
        return _report_result(
            ObservationResult(model, model.coverage, diagnostics),
            report_filter,
            require_source_graph=True,
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        result = unknown_result(_Command.REPORT, str(path), error)
        return replace(
            result,
            diagnostics=tuple(
                replace(item, remedy="Restore a complete recorded architecture.json and retry.")
                for item in result.diagnostics
            ),
        )


def _source_section_name(name: str) -> SourceSectionName | None:
    try:
        return SourceSectionName(name)
    except ValueError:
        return None


def _validate_saved_sources(model: Observation) -> None:
    module_paths: dict[str, str] = {}
    module_packages: dict[str, str] = {}
    for module in model.records("modules") or ():
        name, source_path, package = (
            module.data.get("qualified_name"),
            module.data.get("file"),
            module.data.get("package"),
        )
        if (
            not isinstance(name, str)
            or not isinstance(source_path, str)
            or not isinstance(package, str)
            or name in module_paths
        ):
            raise ValueError("recorded modules need source paths, packages and unique names")
        module_paths[name] = source_path
        module_packages[name] = package
    # Core allowance receipts have trace checks but no collector source payload.
    validate_source_bindings(
        (
            record
            for section in model.sections
            if section.name == "modules"
            or (_source_section_name(section.name) not in (None, SourceSectionName.UNKNOWNS))
            for record in section.records
            if not (
                _source_section_name(section.name) is SourceSectionName.TYPING_SIGNALS
                and record.kind in {"boundary_type_allowance", "type_ignore_allowance"}
                and record.evidence_class == EvidenceClass.FACT
            )
        ),
        module_paths,
        module_packages,
        {item.id: item for item in model.evidence},
        import_ids={item.id for item in model.records("imports") or ()},
        selected_inputs={item.file for item in model.evidence},
        allow_part_evidence=model.analyzer.name == "archkeel-dart-analyzer",
    )
    _validate_saved_selector_receivers(model)


def _saved_annotation_target(
    owner: Record,
    spelling: str,
    imports: tuple[Record, ...],
    declarations: dict[str, list[Record]],
    evidence: dict[str, Evidence],
) -> str | None:
    module = owner.data.get("module")
    if not isinstance(module, str) or not spelling:
        return None
    root, _, suffix = spelling.partition(".")
    imported = [
        record
        for record in imports
        if record.data.get("source_module") == module
        and record.data.get("binding") == root
        and record.data.get("under_type_checking") is False
        and _saved_top_level_import(record, root, evidence)
    ]
    if len(imported) == 1:
        origin = _saved_import_origin(imported[0])
        if origin is None:
            return None
        candidates = (".".join(part for part in (origin, suffix) if part),)
    elif imported:
        return None
    else:
        candidates = (f"{module}.{spelling}",)
    matches: list[str] = []
    for candidate in candidates:
        candidate_declarations: list[Record] = declarations.get(candidate, [])
        if len(candidate_declarations) != 1:
            continue
        declaration: Record = candidate_declarations[0]
        if declaration.kind == "class" and declaration.data.get("source_binding_unique") is True:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _saved_import_origin(record: Record) -> str | None:
    data = record.data
    origin = data.get("origin_definition")
    chain = data.get("reexport_chain")
    candidates = data.get("reexport_candidates")
    if (
        isinstance(origin, str)
        and _saved_qualified_identifier(origin)
        and isinstance(chain, tuple)
        and chain
        and chain[-1] == origin
        and len(set(chain)) == len(chain)
        and all(isinstance(item, str) and _saved_qualified_identifier(item) for item in chain)
        and data.get("source_binding_unique") is True
        and data.get("symbols_known") is True
        and data.get("reexport_candidate") is not True
        and candidates in (None, ())
    ):
        return origin
    return None


def _saved_qualified_identifier(value: str) -> bool:
    return bool(value) and all(part.isidentifier() for part in value.split("."))


def _saved_top_level_import(record: Record, binding: str, evidence: dict[str, Evidence]) -> bool:
    if (
        record.data.get("source_binding_unique") is not True
        or record.data.get("symbols_known") is not True
    ):
        return False
    symbol = record.data.get("symbol")
    for identifier in record.evidence_ids:
        item = evidence.get(identifier)
        if item is None or item.column != 0:
            continue
        try:
            statements = ast.parse(item.excerpt).body
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            continue
        if len(statements) != 1:
            continue
        statement = statements[0]
        if isinstance(statement, ast.ImportFrom):
            if isinstance(symbol, str) and any(
                alias.name == symbol and (alias.asname or alias.name) == binding
                for alias in statement.names
            ):
                return True
        elif isinstance(statement, ast.Import) and symbol is None:
            for alias in statement.names:
                alias_name: str = alias.name
                if (alias.asname or alias_name.partition(".")[0]) == binding:
                    return True
    return False


def _saved_selector_direct(
    binding: CallBinding,
    parameter_name: JsonValue,
    targets: list[Record],
    imports: tuple[Record, ...],
) -> None:
    target: Record | None = targets[0] if len(targets) == 1 else None
    local_class = (
        target is not None
        and target.kind == "class"
        and target.data.get("source_binding_unique") is True
        and set(binding.evidence_ids) <= set(target.evidence_ids)
    )
    imported_class = any(
        item.data.get("symbols_known") is True
        and item.data.get("source_binding_unique") is True
        and _saved_import_origin(item) == binding.target
        and set(item.evidence_ids) <= set(binding.evidence_ids)
        for item in imports
    )
    if parameter_name is not None or not (local_class or imported_class):
        raise ValueError("saved selector class receiver needs its stable declaration")


def _saved_selector_declared(
    selector: Record,
    binding: CallBinding,
    parameter_name: JsonValue,
    declarations: dict[str, list[Record]],
    targets: list[Record],
    imports: tuple[Record, ...],
    evidence: dict[str, Evidence],
) -> None:
    selector_owner_name = selector.data.get("owner")
    parameter_owner_name = selector.data.get("receiver_parameter_owner")
    if not isinstance(parameter_owner_name, str):
        parameter_owner_name = selector_owner_name
    owners = (
        declarations.get(parameter_owner_name, []) if isinstance(parameter_owner_name, str) else []
    )
    selector_owners = (
        declarations.get(selector_owner_name, []) if isinstance(selector_owner_name, str) else []
    )
    owner: Record | None = owners[0] if len(owners) == 1 else None
    selector_owner: Record | None = selector_owners[0] if len(selector_owners) == 1 else None
    target_declaration: Record | None = targets[0] if len(targets) == 1 else None
    parameters = owner.data.get("parameters") if owner is not None else None
    candidates = (
        [
            item
            for item in parameters
            if isinstance(item, RecordData) and item.get("name") == parameter_name
        ]
        if isinstance(parameters, tuple)
        else []
    )
    parameter: RecordData | None = candidates[0] if len(candidates) == 1 else None
    annotation = parameter.get("annotation") if parameter is not None else None
    target = (
        _saved_annotation_target(owner, annotation, imports, declarations, evidence)
        if (owner is not None and isinstance(annotation, str))
        else None
    )
    if (
        owner is None
        or owner.kind not in {"function", "method"}
        or selector_owner is None
        or selector_owner.kind not in {"function", "method"}
        or not isinstance(selector_owner_name, str)
        or not isinstance(parameter_owner_name, str)
        or selector_owner_name != parameter_owner_name
        and not selector_owner_name.startswith(f"{parameter_owner_name}.")
        or len(candidates) != 1
        or target != binding.target
        or target_declaration is None
        or target_declaration.kind != "class"
        or target_declaration.data.get("source_binding_unique") is not True
        or not set(owner.evidence_ids) <= set(binding.evidence_ids)
        or not set(selector_owner.evidence_ids) <= set(binding.evidence_ids)
    ):
        raise ValueError("saved selector receiver is not tied to its declared parameter type")


def _saved_selector_stored(
    binding: CallBinding,
    declarations: dict[str, list[Record]],
    targets: list[Record],
    imports: tuple[Record, ...],
    evidence: dict[str, Evidence],
) -> None:
    proof = binding.proof
    if not isinstance(proof, RecordData):
        raise ValueError("saved stored selector receiver needs its typed proof")
    owner_name, field = proof.get("owner"), proof.get("field")
    parameter, witnesses = proof.get("parameter"), proof.get("witness_evidence_ids")
    owners = declarations.get(owner_name, []) if isinstance(owner_name, str) else []
    initializers = (
        declarations.get(f"{owner_name}.__init__", []) if isinstance(owner_name, str) else []
    )
    owner: Record | None = owners[0] if len(owners) == 1 else None
    initializer: Record | None = initializers[0] if len(initializers) == 1 else None
    target_declaration: Record | None = targets[0] if len(targets) == 1 else None
    writes = initializer.data.get("stored_field_writes") if initializer is not None else None
    witness_ids = witnesses if isinstance(witnesses, tuple) else ()
    linked = (
        [
            item
            for item in writes
            if isinstance(item, RecordData)
            and item.get("field") == field
            and item.get("parameter") == parameter
            and item.get("evidence_id") == (witness_ids[0] if witness_ids else None)
            and len(witness_ids) == 2
            and item.get("annotation_evidence_id") == witness_ids[1]
            and item.get("annotation_target") == binding.target
        ]
        if isinstance(writes, tuple)
        else []
    )
    parameters = initializer.data.get("parameters") if initializer is not None else None
    typed = (
        [
            item
            for item in parameters
            if isinstance(item, RecordData)
            and item.get("name") == parameter
            and isinstance(item.get("annotation"), str)
        ]
        if isinstance(parameters, tuple)
        else []
    )
    typed_parameter: RecordData | None = typed[0] if len(typed) == 1 else None
    annotation = typed_parameter.get("annotation") if typed_parameter is not None else None
    target = (
        _saved_annotation_target(initializer, annotation, imports, declarations, evidence)
        if (initializer is not None and isinstance(annotation, str))
        else None
    )
    ids = binding.evidence_ids
    if (
        proof.get("kind") != "stored_field"
        or proof.get("target") != binding.target
        or owner is None
        or owner.kind != "class"
        or owner.data.get("source_binding_unique") is not True
        or len(initializers) != 1
        or len(linked) != 1
        or len(typed) != 1
        or target != binding.target
        or not isinstance(witnesses, tuple)
        or len(witnesses) != 2
        or not set(witnesses) <= set(ids)
        or target_declaration is None
        or target_declaration.kind != "class"
        or target_declaration.data.get("source_binding_unique") is not True
        or not set(owner.evidence_ids) <= set(ids)
    ):
        raise ValueError("saved stored selector receiver needs its typed initializer link")


def _saved_selector_constructed(
    model: Observation,
    selector: Record,
    binding: CallBinding,
    targets: list[Record],
    evidence: dict[str, Evidence],
) -> None:
    proof = binding.proof
    if not isinstance(proof, RecordData):
        raise ValueError("saved constructed selector receiver needs its allocation proof")
    constructor_id = proof.get("constructor_evidence_id")
    assignment_id, assignment_name = (
        proof.get("assignment_evidence_id"),
        proof.get("assignment_name"),
    )
    constructor_calls, assignment_calls = _saved_selector_construction_calls(
        model, constructor_id, binding.target, assignment_id, assignment_name
    )
    assignment_evidence = evidence.get(assignment_id) if isinstance(assignment_id, str) else None
    selector_evidence = [
        evidence[item]
        for item in selector.evidence_ids
        if item not in binding.evidence_ids and item in evidence
    ]
    if isinstance(constructor_id, str) and constructor_id in selector.evidence_ids:
        constructor_evidence = evidence.get(constructor_id)
        if constructor_evidence is not None and constructor_evidence not in selector_evidence:
            selector_evidence.append(constructor_evidence)
    target_declaration: Record | None = targets[0] if len(targets) == 1 else None
    assignment_call: Record | None = assignment_calls[0][0] if len(assignment_calls) == 1 else None
    if not _saved_selector_construction_is_linked(
        proof,
        binding,
        selector,
        assignment_id,
        assignment_name,
        constructor_calls,
        assignment_evidence,
        selector_evidence,
        target_declaration,
        assignment_call,
    ):
        raise ValueError("saved constructed selector receiver needs its allocation link")


def _saved_selector_construction_calls(
    model: Observation,
    constructor_id: JsonValue,
    target: str,
    assignment_id: JsonValue,
    assignment_name: JsonValue,
) -> tuple[list[Record], list[tuple[Record, RecordData]]]:
    calls = model.records("calls") or ()
    constructor_calls: list[Record] = []
    assignment_calls: list[tuple[Record, RecordData]] = []
    if isinstance(constructor_id, str):
        for candidate in calls:
            if constructor_id not in candidate.evidence_ids:
                continue
            candidate_targets = candidate.data.get("targets")
            candidate_kind: str = candidate.kind
            if (
                candidate_kind.endswith("_call")
                and isinstance(candidate_targets, tuple)
                and target in candidate_targets
            ):
                constructor_calls.append(candidate)
            results = candidate.data.get("result_bindings")
            if isinstance(results, tuple):
                for item in results:
                    evidence_ids = (
                        item.get("evidence_ids") if isinstance(item, RecordData) else None
                    )
                    if (
                        isinstance(assignment_id, str)
                        and isinstance(item, RecordData)
                        and item.get("name") == assignment_name
                        and item.get("target_kind") == "name"
                        and isinstance(evidence_ids, tuple)
                        and assignment_id in evidence_ids
                    ):
                        assignment_calls.append((candidate, item))
    return constructor_calls, assignment_calls


def _saved_selector_construction_is_linked(
    proof: RecordData,
    binding: CallBinding,
    selector: Record,
    assignment_id: JsonValue,
    assignment_name: JsonValue,
    constructor_calls: list[Record],
    assignment_evidence: Evidence | None,
    selector_evidence: list[Evidence],
    target_declaration: Record | None,
    assignment_call: Record | None,
) -> bool:
    ids = binding.evidence_ids
    constructor_id = proof.get("constructor_evidence_id")
    if (
        proof.get("kind") != "construction"
        or proof.get("target") != binding.target
        or target_declaration is None
        or target_declaration.data.get("default_instance_result") is not True
        or not isinstance(constructor_id, str)
        or len(constructor_calls) != 1
        or not selector_evidence
        or assignment_id is not None
        and (
            not isinstance(assignment_name, str)
            or assignment_call is None
            or assignment_call.data.get("source_scope") != selector.data.get("owner")
            or assignment_evidence is None
            or assignment_evidence.line >= max(item.line for item in selector_evidence)
            or assignment_id not in ids
        )
        or assignment_id is None
        and assignment_name is not None
        or not _saved_constructor_target_is_witnessed(
            constructor_calls,
            target_declaration,
            binding,
            assignment_id,
            assignment_call,
        )
    ):
        return False
    return True


def _saved_constructor_target_is_witnessed(
    constructor_calls: list[Record],
    target_declaration: Record,
    binding: CallBinding,
    assignment_id: JsonValue,
    assignment_call: Record | None,
) -> bool:
    declaration_evidence = set(target_declaration.evidence_ids)
    if declaration_evidence <= set(binding.evidence_ids):
        return True
    if len(constructor_calls) != 1:
        return False
    constructor = constructor_calls[0]
    constructor_binding = call_binding(constructor.data.get("call_binding"))
    targets = constructor.data.get("targets")
    target_evidence = constructor.data.get("target_evidence_ids")
    return (
        constructor.kind.endswith("_call")
        and isinstance(targets, tuple)
        and binding.target in targets
        and isinstance(target_evidence, tuple)
        and declaration_evidence <= set(target_evidence)
        and constructor_binding is not None
        and constructor_binding.origin is CallBindingOrigin.CONSTRUCTOR
        and constructor_binding.target == binding.target
        and declaration_evidence <= set(constructor_binding.evidence_ids)
        and (
            assignment_id is None
            and assignment_call is None
            or assignment_id is not None
            and assignment_call is constructor
        )
    )


def _validate_saved_selector_receivers(model: Observation) -> None:
    symbols = model.records("symbols") or ()
    imports = model.records("imports") or ()
    evidence = {item.id: item for item in model.evidence}
    declarations: dict[str, list[Record]] = {}
    for symbol in symbols:
        name = symbol.data.get("qualified_name")
        if symbol.kind in {"class", "function", "method"} and isinstance(name, str):
            named_declarations: list[Record] = declarations.setdefault(name, [])
            named_declarations.append(symbol)
    for selector in model.records("constructs") or ():
        if selector.kind != "construct_selector":
            continue
        receiver = selector.data.get("receiver_type")
        binding = call_binding(selector.data.get("receiver_binding"))
        parameter = selector.data.get("receiver_parameter")
        if receiver is None:
            if binding is not None:
                raise ValueError("unknown selector receiver cannot carry a typed binding")
            continue
        if binding is None or binding.target != receiver:
            raise ValueError("saved selector receiver disagrees with its typed binding")
        if not set(binding.evidence_ids) <= set(selector.evidence_ids) or not set(
            binding.evidence_ids
        ) <= set(evidence):
            raise ValueError("saved selector receiver has dangling source evidence")
        if binding.origin in {
            CallBindingOrigin.DIRECT,
            CallBindingOrigin.DECLARED_RECEIVER,
            CallBindingOrigin.STORED_RECEIVER,
            CallBindingOrigin.CONSTRUCTED_RECEIVER,
        } and not selector_receiver_site_matches(
            selector,
            binding,
            parameter if isinstance(parameter, str) else None,
            declarations,
            evidence,
            model.records("imports") or (),
        ):
            raise ValueError("saved selector proof does not match its source expression")
        targets = declarations.get(binding.target, [])
        if binding.origin is CallBindingOrigin.DIRECT:
            _saved_selector_direct(binding, parameter, targets, imports)
        elif binding.origin is CallBindingOrigin.STORED_RECEIVER:
            _saved_selector_stored(binding, declarations, targets, imports, evidence)
        elif binding.origin is CallBindingOrigin.CONSTRUCTED_RECEIVER:
            _saved_selector_constructed(model, selector, binding, targets, evidence)
        elif binding.origin is CallBindingOrigin.DECLARED_RECEIVER:
            _saved_selector_declared(
                selector, binding, parameter, declarations, targets, imports, evidence
            )
        else:
            raise ValueError("saved selector receiver origin is unsupported")
