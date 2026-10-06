# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import subprocess
from collections import Counter as _Counter
from dataclasses import replace
from pathlib import Path
from typing import Literal as _Literal
from typing import get_args

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
from archkeel.ir.facts import SourceSectionName
from archkeel.ir.facts_validation import validate_source_bindings
from archkeel.ir.model import (
    BaselineViolationComparison,
    CallRow,
    Diagnostic,
    DiagnosticError,
    EvidenceClass,
    FilteredViolation,
    Observation,
    ObservationResult,
    ReportFilter,
    ReportLocation,
    RunResult,
)
from archkeel.ir.profiles import PROFILES
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.ir.trace import validate_evidence_classes

from .git import git_bytes
from .observe import observation_diagnostics
from .ports import Analyzer, ScanConfig
from .ratchets import call_rows, calls_measured, unknown_positions_by_rule
from .run import inspect_observation
from .runtime import runtime_diagnostic
from .snapshot import resolve_commit
from .uml import assemble_uml
from .uml_evaluation import evaluate_uml

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


def unknown_result(command: str, subject: str, error: Exception) -> RunResult:
    if isinstance(error, DiagnosticError):
        diagnostic = error.diagnostic
    else:
        diagnostic = Diagnostic(
            "timeout" if isinstance(error, subprocess.TimeoutExpired) else "parse_error",
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
    """Observe the configured working tree through an injected analyzer."""
    result = analyzer(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=resolve_commit(root, "HEAD"),
        dirty=bool(git_bytes(root, "status", "--porcelain", "--untracked-files=all")),
        contract_root=contract_root or root,
        language=config.language,
    )
    return evaluate_uml(assemble_uml(result, contract_root or root, config.contract))


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
                "rule_unsupported_by_profile",
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
    return RunResult(
        "report",
        2,
        diagnostics=result.diagnostics,
        coverage=result.coverage,
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
            and (not report_filter.only_violations or item.status in {"FAIL", "UNKNOWN"})
        )
        return replace(result, rule_assessments=assessments)
    if report_filter.only_violations:
        return replace(
            result,
            rule_assessments=tuple(
                item for item in result.rule_assessments if item.status in {"FAIL", "UNKNOWN"}
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
    complete = command_result.observation_complete == "PASS"
    component_rules: set[str] = set()
    try:
        selected_violations = (
            _selected_violations(model, replace(report_filter, component=None))
            if complete and only_violations and report_filter is not None
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
        finding_ids = (
            {identity for owner in projection.components for identity in owner.finding_ids}
            if component is not None
            else {item.id for item in report.findings}
        )
        if only_architecture or only_violations:
            component_rules |= _selected_finding_rules(report, finding_ids)
        command_result = replace(
            command_result,
            report_filter=report_filter,
            architecture_projection=projection,
            filtered_violations=None
            if not complete
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
            unknown_result("report", "architecture projection", error),
            coverage=model.coverage,
            python_version=model.python_version,
        )
    return _scope_report_assessments(command_result, report_filter, component_rules)


def _report_result(
    result: ObservationResult,
    report_filter: ReportFilter | None,
    *,
    baseline_root: Path | None = None,
    baseline: Path | None = None,
    require_source_graph: bool = False,
) -> RunResult:
    only_calls = report_filter is not None and report_filter.only_calls
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
                unknown_result("report", "observation", error),
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
                "report",
                0,
                observation_complete="PASS",
                declared_rules=declared,
                expectation_fulfilled="n/a",
                coverage=model.coverage,
                measurements=measurements,
                python_version=model.python_version,
                agent_decisions=agent_decisions(model),
                open_decisions=open_decisions(model),
                claims=review_claims(model),
                violations_by_rule=counted.by_rule,
                violations_by_component_pair=counted.by_component_pair,
                report_filter=report_filter,
                filtered_violations=filtered_violations,
                filtered_calls=filtered_calls,
                rule_assessments=assessments,
                baseline_path=baseline_name,
                baseline_comparisons=comparisons,
            )
    if model is not None:
        command_result = _architecture_result(
            model,
            command_result,
            report_filter,
            require_source_graph=require_source_graph,
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
    result = observe_repository(root, config, analyzer)
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
        result = unknown_result("report", str(path), error)
        return replace(
            result,
            diagnostics=tuple(
                replace(item, remedy="Restore a complete recorded architecture.json and retry.")
                for item in result.diagnostics
            ),
        )


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
            or (section.name in get_args(SourceSectionName) and section.name != "unknowns")
            for record in section.records
            if not (
                section.name == "typing_signals"
                and record.kind in {"boundary_type_allowance", "type_ignore_allowance"}
                and record.evidence_class == EvidenceClass.FACT
            )
        ),
        module_paths,
        module_packages,
        {item.id: item for item in model.evidence},
        import_ids={item.id for item in model.records("imports") or ()},
    )
