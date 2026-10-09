# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from archkeel.ir.baseline import (
    KnownViolation,
    ValidationBaseline,
    compare_violations,
    observed_violations,
    violation_drift_counts,
)
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractInputError,
    ContractVersionError,
    InsideContractTree,
    absent_baseline_digest,
    absent_contract_digest,
    amendment_bytes,
    baseline_bytes,
    baseline_digest,
    contract_digest,
    contract_provenance_paths,
    decode_json,
    load_inside_contract_tree,
    parse_amendment,
    parse_contract,
    parse_validation_baseline,
)
from archkeel.ir.decisions import (
    agent_decisions,
    open_decisions,
    review_claims,
    rule_assessments,
    violation_counts,
)
from archkeel.ir.interfaces import interface_budgets
from archkeel.ir.measurements import (
    MeasurementBudget,
    RatchetError,
    budget_label,
    budget_regressions,
    compare_budgets,
    name_drift,
    selected_budgets,
)
from archkeel.ir.model import (
    ArchitectureContract,
    ContractDeclarations,
    Diagnostic,
    InterfaceBudgetResult,
    NoComponentCyclesRule,
    Observation,
    RunResult,
    UnresolvedCallChange,
    WideningFinding,
    text_value,
)
from archkeel.ir.renames import Renamed, module_layouts, observed_names, renames_since
from archkeel.ir.widening import (
    Amendment,
    WideningChange,
    baseline_widening_changes,
    contract_widening_changes,
    measurement_budget_changes,
    verify_amendment,
)

from ..git import GitError, MissingBlobError, read_blob, tracked_paths, working_tree_paths
from ..ports import Analyzer, FilesToWrite, ScanConfig
from ..ratchets import measure_python_ratchets, unknown_positions_by_rule, unresolved_call_changes
from ..report import observe_repository
from ..run import inspect_observation, observe_revision
from ..snapshot import SnapshotError
from .closed_world import _decided_pairs as _decided_pairs
from .closed_world import _open_decision_diagnostics as _open_decision_diagnostics
from .closed_world import _pair_diagnostics as _pair_diagnostics
from .closed_world import closed_world_diagnostics as closed_world_diagnostics
from .closed_world import observed_component_edges as observed_component_edges
from .closed_world import target_component_edges as target_component_edges
from .diagnostics import _diagnostic as _diagnostic
from .diagnostics import _sorted as _sorted
from .graphs import (
    _GRAPH_EDGE as _GRAPH_EDGE,
)
from .graphs import (
    COMPONENT_GRAPH_MARKER as COMPONENT_GRAPH_MARKER,
)
from .graphs import (
    TARGET_GRAPH_MARKER as TARGET_GRAPH_MARKER,
)
from .graphs import (
    _marked_bodies as _marked_bodies,
)
from .graphs import _marker_diagnostics as _marker_diagnostics
from .graphs import (
    _unwritable_line as _unwritable_line,
)
from .graphs import graph_diagnostics as graph_diagnostics
from .graphs import (
    mermaid_edges as mermaid_edges,
)
from .graphs import (
    rewrite_component_graph as rewrite_component_graph,
)
from .inside import _denied_by_absence as _denied_by_absence
from .inside import _forbidden_targets as _forbidden_targets
from .inside import _import_published_through_ancestors as _import_published_through_ancestors
from .inside import _inside_imports_by_target as _inside_imports_by_target
from .inside import (
    _inside_interface_lifecycle_diagnostics as _inside_interface_lifecycle_diagnostics,
)
from .inside import _inside_parent_policy_diagnostics as _inside_parent_policy_diagnostics
from .inside import _inside_source_domain_diagnostics as _inside_source_domain_diagnostics
from .inside import inside_diagnostics as inside_diagnostics
from .observation import _inside_pointers as _inside_pointers
from .observation import observation_diagnostics as observation_diagnostics
from .public_api import _BUDGET_NOUNS as _BUDGET_NOUNS
from .public_api import _clip_contract as _clip_contract
from .public_api import _compatibility_import_diagnostics as _compatibility_import_diagnostics
from .public_api import _entry_module as _entry_module
from .public_api import _entry_reached_by as _entry_reached_by
from .public_api import _entry_used as _entry_used
from .public_api import _facade_covers_import as _facade_covers_import
from .public_api import _facade_types as _facade_types
from .public_api import _imports_by_target as _imports_by_target
from .public_api import _inherited_facade_candidates as _inherited_facade_candidates
from .public_api import _literal_exports as _literal_exports
from .public_api import _missing_public_entry as _missing_public_entry
from .public_api import _parent_reexport_proven as _parent_reexport_proven
from .public_api import _planned_entry_diagnostics as _planned_entry_diagnostics
from .public_api import _public_api_entry_diagnostics as _public_api_entry_diagnostics
from .public_api import _public_entry_diagnostics as _public_entry_diagnostics
from .public_api import _published_api_types as _published_api_types
from .public_api import _published_parent_components as _published_parent_components
from .public_api import _reexport_owners as _reexport_owners
from .public_api import _resolved_public_entries as _resolved_public_entries
from .public_api import _scanned_modules as _scanned_modules
from .public_api import _scoped_facade_types as _scoped_facade_types
from .public_api import compatibility_diagnostics as compatibility_diagnostics
from .public_api import interface_budget_diagnostics as interface_budget_diagnostics
from .public_api import interface_diagnostics as interface_diagnostics
from .public_api import public_api_diagnostics as public_api_diagnostics
from .rationale import rationale_diagnostics as rationale_diagnostics
from .references import _entry_ownership_diagnostics as _entry_ownership_diagnostics
from .references import _inside_contract_tree as _inside_contract_tree
from .references import _namespace_references as _namespace_references
from .references import _provenance as _provenance
from .references import _public_diagnostics as _public_diagnostics
from .references import reference_diagnostics as reference_diagnostics
from .references import repository_file as repository_file

# AD-106: the last failure of a refused --write-baseline, after every other line of the run.
_WRITE_REFUSED = (
    "--write-baseline refused: writing would accept the new or increased debt above; fix the "
    "code, or add --accept-new once an architect has decided to accept it"
)


def _name_budget_targets(declarations: ContractDeclarations) -> dict[str, int]:
    """Each declared facade and pair budget's `max_names`, by its baseline label (AD-99)."""
    return {
        **{
            budget_label("facade_names", item.subject): item.max_names
            for item in declarations.facade_budgets or ()
        },
        **{
            budget_label("coupling_names", item.subject): item.max_names
            for item in declarations.coupling_budgets or ()
        },
    }


def _name_budget(item: InterfaceBudgetResult) -> MeasurementBudget:
    """The accepted-name ratchet one measured budget writes to the baseline (AD-99)."""
    return MeasurementBudget(item.budget, item.count, item.subject, item.names)


def _compared_budgets(
    results: tuple[InterfaceBudgetResult, ...], accepted: tuple[MeasurementBudget, ...]
) -> tuple[InterfaceBudgetResult, ...]:
    """Each result with the names it adds to and drops from the baseline's accepted set."""
    held = {budget.label: budget for budget in accepted}
    compared = []
    for item in results:
        observed = _name_budget(item)
        before = held.get(observed.label)
        if before is None:
            compared.append(item)
            continue
        new, removed = name_drift(before, observed)
        compared.append(replace(item, new_names=new, removed_names=removed))
    return tuple(compared)


def invalid_result(subject: str, error: Exception, pointer: str = "") -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "contract.invalid",
                pointer,
                subject,
                f"The architecture contract cannot be validated: {error}",
                "Correct the input and run archkeel validate again.",
            ),
        ),
    )


def _repository_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation,
    write_graph: bool,
    report_violations: bool,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
    inside_tree: InsideContractTree | None = None,
) -> tuple[list[Diagnostic], tuple[tuple[str, str], ...]]:
    """Every diagnostic a complete observation adds, once the contract's references hold.

    AD-46/AD-57: `write_graph` rewrites both marked graphs first, so the diagnostics judge the
    pages as they will be written, and every rewritten page comes back with its path.
    """
    # The page is written back as UTF-8, so it is read as UTF-8 whatever the locale says.
    documents = tuple(
        (path, (root / path).read_text(encoding="utf-8"))
        for path in contract_provenance_paths(contract)
    )
    edits = (
        rewrite_component_graph(
            documents,
            observed_component_edges(contract, observation),
            target_component_edges(contract),
        )
        if write_graph
        else ()
    )
    if edits:
        written = dict(edits)
        documents = tuple((path, written.get(path, text)) for path, text in documents)
    return [
        *reference_diagnostics(root, config, contract, observation),
        *observation_diagnostics(
            contract,
            observation,
            documents,
            report_violations=report_violations,
            resolved_public_entries=resolved_public_entries,
            inside_tree=inside_tree,
            contract_path=config.contract,
        ),
        *inside_diagnostics(root, contract, config, inside_tree, observation),
    ], edits


def _observed_result(
    observation: Observation,
    diagnostics: list[Diagnostic],
    failures: tuple[str, ...] = (),
    *,
    baseline_new: int | None = None,
    baseline_resolved: int | None = None,
    interface_budgets: tuple[InterfaceBudgetResult, ...] | None = None,
    widenings: tuple[WideningFinding, ...] | None = None,
    amendment_status: Literal["valid", "stale"] | None = None,
) -> RunResult:
    """The validate result once a complete observation has produced its diagnostics.

    AD-52: baseline findings arrive as `failures` and exit 1. Diagnostics reject
    validation at exit 2 without discarding successfully inspected evidence.
    """
    try:
        measurements, declared = inspect_observation(observation)
    except ValueError as error:
        diagnostics.append(
            _diagnostic(
                "observation.incomplete",
                "",
                "observation",
                f"The observation is incomplete: {error}",
                "Repair the analyzer evidence and retry.",
            )
        )
        measurements = None
        declared = "UNKNOWN"
    decisions = open_decisions(observation)
    counts = agent_decisions(observation)
    # AD-51: a rejected run is where the breakdown is read, so it carries it too.
    counted = violation_counts(observation)
    return RunResult(
        "validate",
        2 if diagnostics else 1 if failures else 0,
        observation_complete="PASS" if measurements is not None else "UNKNOWN",
        declared_rules=declared,
        expectation_fulfilled="n/a" if measurements is not None else "UNKNOWN",
        diagnostics=_sorted(diagnostics),
        coverage=observation.coverage,
        python_version=observation.python_version,
        measurements=measurements,
        failures=failures,
        widenings=widenings,
        amendment_status=amendment_status,
        baseline_new=baseline_new,
        baseline_resolved=baseline_resolved,
        open_decisions=decisions,
        agent_decisions=counts,
        claims=review_claims(observation) if measurements is not None else None,
        rule_assessments=(
            rule_assessments(observation, undecided_by_rule=unknown_positions_by_rule(observation))
            if measurements is not None
            else None
        ),
        violations_by_rule=counted.by_rule,
        violations_by_component_pair=counted.by_component_pair,
        interface_budgets=interface_budgets,
    )


_UNCOMPARED = "the --against revision's calls could not be compared, so no call site is named"
_ONE_SIDED = (
    "added calls in files only the working tree holds (git-ignored, inside a submodule, or "
    "export-ignore at the --against revision) are not named"
)
_NOTHING_DIFFERS = (
    "no unresolved call differs from the --against revision; the accepted value does not match "
    "that revision's code"
)


def _unresolved_calls_since(
    root: Path, config: ScanConfig, analyzer: Analyzer, against: str, observation: Observation
) -> tuple[tuple[UnresolvedCallChange, ...] | None, str | None]:
    """AD-100: the unresolved calls whose count differs from the code at `against`, and why
    any of them goes unnamed.

    None when that revision's source cannot be observed completely: the sites explain a
    finding, they never decide one. The revision is scanned under its own contract, the way
    `check` scans its accepted commit, so a rule naming a module only the new code has cannot
    leave the old scan without subjects, and a removed call names the component it had then.
    """
    try:
        observed = observe_revision(analyzer, root, against, config, declared_at=against)
        if observed.diagnostics or observed.observation is None:
            return None, _UNCOMPARED
        changes = unresolved_call_changes(observed.observation, observation)
        one_sided = _one_sided_paths(root, config, observed.observation, changes)
    except (GitError, SnapshotError, RatchetError):
        return None, _UNCOMPARED
    named = tuple(
        item for item in changes if item.change == "removed" or item.path not in one_sided
    )
    if len(named) < len(changes):
        return named, _ONE_SIDED
    return named, None if named else _NOTHING_DIFFERS


def _one_sided_paths(
    root: Path,
    config: ScanConfig,
    before: Observation,
    changes: tuple[UnresolvedCallChange, ...],
) -> frozenset[str]:
    """AD-100: the added rows' files only the working-tree side can hold.

    The working tree is read from disk, the revision from its `git archive` snapshot. A file the
    snapshot holds is on both sides and always compared, and so is a removed row's. Of the rest,
    a file outside Git's view of the working tree (ignored, or inside a submodule) is never
    archived, and one the revision tracks was left out by its own `export-ignore`.
    """
    archived = {text_value(record.data.get("file")) for record in before.records("modules") or ()}
    added = frozenset(item.path for item in changes if item.change == "added") - archived
    if not added:
        return frozenset()
    tracked = tracked_paths(root, before.source.git_head, config.roots)
    visible = working_tree_paths(root, config.roots)
    return frozenset(path for path in added if path not in visible or path in tracked)


def _calls_unresolved(budgets: tuple[MeasurementBudget, ...]) -> int | None:
    return next((item.value for item in budgets if item.name == "calls_unresolved"), None)


_BASELINE_WRITE = (
    "Correct the baseline, or write it with archkeel validate --baseline <path> --write-baseline."
)
# AD-106: a write reads an existing file first, so advising one for an unreadable file loops.
_BASELINE_CORRECT = (
    "Correct the baseline file by hand; a write reads it first and stops on the same error."
)
# AD-103: a path outside the root is refused before any read or write.
_BASELINE_INSIDE_ROOT = "Pass a --baseline path inside --root, relative to it or absolute."


def _baseline_invalid(path: Path, error: Exception, remedy: str) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "baseline.invalid",
                "",
                str(path),
                f"The validation baseline cannot be read: {error}",
                remedy,
            ),
        ),
    )


def _budget_baseline_missing() -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "baseline.invalid",
                "/declarations/measurement_budgets",
                "measurement_budgets",
                "The contract selects measurement budgets but --baseline was not supplied.",
                "Run validate with --baseline <path>; add --write-baseline to record the "
                "current values.",
            ),
        ),
    )


def _against_invalid(against: str, error: Exception) -> RunResult:
    pointer = error.pointer if isinstance(error, ContractInputError) else ""
    subject = error.subject if isinstance(error, ContractInputError) else against
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "against.invalid",
                pointer,
                subject,
                f"The compared revision cannot be read: {error}",
                "Supply a Git revision this repository can resolve, with a valid contract at "
                "its configured path.",
            ),
        ),
    )


def _amendment_invalid(path: Path, error: Exception) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "amendment.invalid",
                "",
                str(path),
                f"The contract-widening amendment cannot be read: {error}",
                "Correct the amendment, or write it with archkeel validate --against <ref> "
                "--amendment <path> --write-amendment --decided-by <who> --rationale <why>.",
            ),
        ),
    )


def _parse_contract_or_invalid(root: Path, config: ScanConfig) -> ArchitectureContract | RunResult:
    """The parsed contract, or the exit-2 result naming why it could not be read."""
    try:
        return parse_contract(decode_json((root / config.contract).read_bytes()))
    except ContractVersionError as error:
        return RunResult(
            "validate",
            2,
            diagnostics=(
                _diagnostic(
                    "contract.schema_version",
                    "/schema_version",
                    config.contract,
                    f"Contract schema {error.actual} cannot be validated as "
                    f"{CONTRACT_SCHEMA_VERSION}.",
                    "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
                ),
            ),
        )
    except ContractInputError as error:
        return invalid_result(error.subject, error, error.pointer)
    except (OSError, ValueError) as error:
        return invalid_result(config.contract, error)


def _observed_or_invalid(
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
    contract: ArchitectureContract,
) -> Observation | RunResult:
    """The complete observation, or the exit-2 result naming what analyzer evidence is missing."""
    observed = observe_repository(root, config, analyzer)
    observation = observed.observation
    if observed.diagnostics or observation is None:
        if observation is not None and any(
            item.kind == "inside_contract_incomplete"
            for item in observation.records("unknowns") or ()
        ):
            extra, _ = _repository_diagnostics(
                root,
                config,
                contract,
                observation,
                write_graph=False,
                report_violations=True,
            )
            diagnostics = [
                *(replace(item, pointer=item.pointer or "") for item in observed.diagnostics),
                *extra,
            ]
            return RunResult(
                "validate",
                2,
                diagnostics=tuple(dict.fromkeys(diagnostics)),
                coverage=observed.coverage,
                python_version=observation.python_version,
            )
        return RunResult(
            "validate",
            2,
            diagnostics=tuple(
                replace(item, pointer=item.pointer or "") for item in observed.diagnostics
            ),
            coverage=observed.coverage,
        )
    return observation


@dataclass(frozen=True, slots=True)
class _Introduced:
    """AD-104: the `--against` revision holds no contract at `path`, its repository path."""

    path: str


@dataclass(frozen=True, slots=True)
class _AgainstContext:
    """Everything `--against` and `--amendment` resolve to, threaded through one run (AD-61)."""

    against: str | None
    contract: ArchitectureContract | _Introduced | None
    # None: nothing at `against` to compare the baseline with (AD-104).
    baseline: tuple[KnownViolation, ...] | None
    budgets: tuple[MeasurementBudget, ...]
    amendment: Path | None
    write_amendment: bool
    parsed_amendment: Amendment | None
    decided_by: str | None
    rationale: str | None
    config: ScanConfig | None
    tree_digest: str | None = None
    baseline_digest: str | None = None


def _revision_contract_tree(root: Path, revision: str, path: str) -> InsideContractTree:
    """Resolve one revision's root and explicit inside declarations from Git blobs."""
    contract = parse_contract(decode_json(read_blob(root, revision, path)))

    def read_inside(reference: str) -> tuple[bytes, str]:
        try:
            return read_blob(root, revision, reference), reference
        except GitError as error:
            raise ValueError(str(error)) from error

    tree = load_inside_contract_tree(
        path,
        contract,
        contract_digest(contract),
        path,
        read_inside,
    )
    if tree.issues:
        issue = next(
            (candidate for candidate in tree.issues if candidate.input_error is not None),
            tree.issues[0],
        )
        if issue.input_error is not None:
            raise ContractInputError(
                f"{issue.pointer}{issue.input_error.pointer}",
                issue.input_error.subject,
                str(issue.input_error),
            )
        raise ValueError(f"inside {issue.path!r}: {issue.reason}")
    return tree


def _resolve_against_context(
    root: Path,
    config: ScanConfig,
    against: str | None,
    baseline: Path | None,
    amendment: Path | None,
    write_amendment: bool,
    decided_by: str | None,
    rationale: str | None,
    against_config: ScanConfig | None,
) -> tuple[_AgainstContext, RunResult | None]:
    """Resolve revision inputs without treating absent measurement budgets as zero."""
    empty = _AgainstContext(
        against,
        None,
        (),
        (),
        amendment,
        write_amendment,
        None,
        decided_by,
        rationale,
        against_config,
    )
    if against is None:
        return empty, None
    parsed_amendment, amendment_error = _resolve_amendment(amendment, write_amendment)
    against_contract_path = (
        against_config.contract if against_config is not None else config.contract
    )
    try:
        tree = _revision_contract_tree(root, against, against_contract_path)
        against_contract: ArchitectureContract | _Introduced = tree.comparison_contract
        before_tree_digest: str | None = tree.comparison_digest
    except MissingBlobError as error:
        against_contract = _Introduced(error.path)
        before_tree_digest = None
    except (GitError, ValueError) as error:
        return empty, _against_invalid(against, error)
    try:
        against_baseline, against_budgets, missing_budgets, before_baseline_digest = (
            _against_baseline_state(root, against, baseline, against_contract)
        )
    except (GitError, ValueError) as error:
        return empty, _against_invalid(against, error)
    if missing_budgets:
        missing = ", ".join(missing_budgets)
        return empty, _against_invalid(
            against,
            ValueError(f"measurement budget values are missing for: {missing}"),
        )
    context = _AgainstContext(
        against,
        against_contract,
        against_baseline,
        against_budgets,
        amendment,
        write_amendment,
        parsed_amendment,
        decided_by,
        rationale,
        against_config,
        before_tree_digest,
        before_baseline_digest,
    )
    return context, amendment_error


def _against_baseline_state(
    root: Path,
    against: str,
    baseline: Path | None,
    contract: ArchitectureContract | _Introduced,
) -> tuple[
    tuple[KnownViolation, ...] | None,
    tuple[MeasurementBudget, ...],
    list[str],
    str | None,
]:
    # Without the contract every entry of a baseline the revision lacks too would repeat the
    # introduction, so that baseline is not compared rather than read as no known debt.
    violations: tuple[KnownViolation, ...] | None = (
        None if isinstance(contract, _Introduced) else ()
    )
    budgets: tuple[MeasurementBudget, ...] = ()
    baseline_at = _baseline_at(root, baseline)
    prior = None if baseline_at is None else _prior_baseline(root, against, baseline_at)
    if prior is not None:
        violations, budgets = prior.violations, prior.budgets
    declarations = contract.declarations if isinstance(contract, ArchitectureContract) else None
    declared: set[str] = set()
    for item in (declarations or ContractDeclarations()).measurement_budgets:
        declared.add(item.name)
    known: set[str] = set()
    for budget in budgets:
        known.add(budget.label)
    missing = sorted(declared - known)
    if baseline_at is None:
        digest = None
    elif prior is None:
        digest = absent_baseline_digest(baseline_at)
    else:
        digest = baseline_digest(prior.violations, prior.budgets)
    return violations, budgets, missing, digest


def _prior_baseline(root: Path, against: str, path: str) -> ValidationBaseline | None:
    """The baseline `against` holds at `path`, or None where it holds none; one it holds but
    cannot hand over raises GitError or ValueError."""
    try:
        payload = read_blob(root, against, path)
    except MissingBlobError:
        return None
    return parse_validation_baseline(decode_json(payload))


def _resolve_amendment(
    amendment: Path | None, write_amendment: bool
) -> tuple[Amendment | None, RunResult | None]:
    if amendment is None or write_amendment:
        return None, None
    try:
        return parse_amendment(decode_json(amendment.read_bytes())), None
    except (OSError, ValueError) as error:
        return None, _amendment_invalid(amendment, error)


def _before_digest(
    contract: ArchitectureContract | _Introduced, tree_digest: str | None = None
) -> str:
    """The digest an amendment binds for the `--against` side (AD-61, AD-104)."""
    if isinstance(contract, _Introduced):
        return absent_contract_digest(contract.path)
    return tree_digest or contract_digest(contract)


def _cycle_rule_ids(contract: ArchitectureContract) -> frozenset[str]:
    """The rules whose violation subjects are one SCC's members, so a subset contracts (AD-98)."""
    return frozenset(rule.id for rule in contract.rules if isinstance(rule, NoComponentCyclesRule))


def _rename_since(
    ctx: _AgainstContext,
    contract: ArchitectureContract,
    observation: Observation,
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
) -> Renamed | None:
    """AD-105: the compared revision under a rename supported by both physical layouts."""
    if (
        ctx.against is None
        or not isinstance(ctx.contract, ArchitectureContract)
        or ctx.config is None
    ):
        return None
    if ctx.contract.components == contract.components:
        return None
    historical_config = ctx.config
    current_layouts = module_layouts(observation)
    historical_layouts = current_layouts
    historical_scanned = False
    if historical_config.language != config.language:
        return None
    if config.language == "python":
        try:
            historical = observe_revision(
                analyzer, root, ctx.against, historical_config, declared_at=ctx.against
            )
        except (GitError, OSError, SnapshotError, ValueError):
            return None
        if historical.diagnostics or historical.observation is None:
            return None
        historical_layouts = module_layouts(historical.observation)
        historical_scanned = True
    elif historical_config.roots != config.roots:
        return None
    layouts = current_layouts | historical_layouts
    recognised = renames_since(
        ctx.contract,
        contract,
        violations=ctx.baseline or (),
        budgets=ctx.budgets,
        observed=observed_names(observation),
        layouts=layouts,
    )
    historical_renames = renames_since(
        ctx.contract,
        contract,
        violations=ctx.baseline or (),
        budgets=ctx.budgets,
        observed=observed_names(observation),
        layouts=historical_layouts,
    )
    return next(
        (
            item
            for item in recognised
            if not historical_scanned
            or any(previous.prefixes == item.prefixes for previous in historical_renames)
            if not any(_left_behind(root, directory) for directory in item.directories)
        ),
        None,
    )


def _left_behind(root: Path, directory: str) -> bool:
    """AD-105: whether a file lies at or below `directory`, or beside it as `directory.*`, where
    an old prefix's code lived: scanned under a new name or not, it is code left behind. A file
    in `__pycache__` is none, since Python loads one only beside its source."""
    base: Path = root / directory
    parent: Path = base.parent
    files = [base, *base.rglob("*"), *parent.glob(f"{base.name}.*")]
    return any(_code_file(root, path) for path in files)


def _code_file(root: Path, path: Path) -> bool:
    relative: Path = path.relative_to(root)
    return path.is_file() and "__pycache__" not in relative.parts


def _widening_failures(
    ctx: _AgainstContext,
    contract: ArchitectureContract,
    rename: Renamed | None,
    baseline: Path | None,
    after_baseline: tuple[KnownViolation, ...],
    after_budgets: tuple[MeasurementBudget, ...],
    cycle_rules: frozenset[str],
    after_digest: str,
    after_policy_digest: str | None,
    *,
    amendment_written: bool,
) -> tuple[tuple[str, ...], tuple[WideningFinding, ...], Literal["valid", "stale"] | None]:
    """Every unamended widening from `ctx.contract` to `contract` (AD-61, #11).

    A recognised rename is applied to the old side first (AD-105), so only what it does not
    explain is compared, and a widening beside it is still reported.
    """
    if ctx.against is None or ctx.contract is None:
        return (), (), None
    violations, budgets = ctx.baseline, ctx.budgets
    if isinstance(ctx.contract, _Introduced):
        # AD-104: nothing at the revision to compare, so the whole contract is one widening, and
        # no rename applies to it (AD-105).
        findings = [
            WideningChange(
                f"contract {ctx.contract.path}",
                "presence",
                f"contract introduced: {ctx.contract.path} does not exist at {ctx.against}",
            )
        ]
        targets: dict[str, int] = {}
    else:
        before = ctx.contract
        if rename is not None:
            before, budgets = rename.contract, rename.budgets
            violations = None if violations is None else rename.violations
        findings = list(contract_widening_changes(before, contract))
        targets = _name_budget_targets(before.declarations or ContractDeclarations())
    if baseline is not None and violations is not None:
        findings += baseline_widening_changes(violations, after_baseline, cycle_rules=cycle_rules)
        findings += measurement_budget_changes(budgets, after_budgets, targets)
    amended = amendment_written or (
        ctx.parsed_amendment is not None
        and verify_amendment(
            ctx.parsed_amendment,
            before_digest=_before_digest(ctx.contract, ctx.tree_digest),
            after_digest=after_digest,
            before_baseline_digest=ctx.baseline_digest,
            after_baseline_digest=after_policy_digest,
        )
    )
    coded_findings = tuple(
        dict.fromkeys(WideningFinding("ir.widening", item.subject, item.field) for item in findings)
    )
    if ctx.parsed_amendment is not None and not amended:
        messages = tuple(item.message for item in findings)
        return (
            messages or ("amendment does not bind this contract and baseline comparison",),
            coded_findings,
            "stale",
        )
    status: Literal["valid", "stale"] | None = None
    if ctx.parsed_amendment is not None and amended:
        status = "valid"
    if findings and not amended:
        return tuple(item.message for item in findings), coded_findings, status
    empty_messages: tuple[str, ...] = ()
    empty_findings: tuple[WideningFinding, ...] = ()
    return empty_messages, empty_findings, status


def _same_destination(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def _artifact_files(
    *,
    root: Path,
    write_baseline: bool,
    baseline: Path | None,
    violations: tuple[KnownViolation, ...],
    budgets: tuple[MeasurementBudget, ...],
    against: _AgainstContext,
    edits: tuple[tuple[str, str], ...],
    exit_code: int,
    current_digest: str,
    after_baseline_digest: str | None,
    refused: bool,
) -> tuple[dict[str, bytes], str | None, bool]:
    """Every file this run writes, and the last one written, as the result's `artifact`.

    AD-46/AD-57: every rewritten graph page is written before the diagnostics judge it,
    whatever they say; a baseline or an amendment records what a run could judge, so exit 2
    writes neither.
    """
    files: dict[str, bytes] = {}
    artifact: str | None = None
    amendment_written = False
    if write_baseline and baseline is not None and exit_code != 2:
        artifact = str(baseline)
        files[artifact] = baseline_bytes(violations, budgets)
    if (
        against.write_amendment
        and not refused
        and against.contract is not None
        and against.amendment is not None
        and exit_code != 2
    ):
        artifact = str(against.amendment)
        files[artifact] = amendment_bytes(
            Amendment(
                _before_digest(against.contract, against.tree_digest),
                current_digest,
                against.decided_by or "",
                against.rationale or "",
                against.baseline_digest,
                after_baseline_digest,
            )
        )
        amendment_written = True
    for page, written in edits:
        artifact = page
        files[page] = written.encode()
        page_path: Path = root / page
        if against.amendment is not None and _same_destination(page_path, against.amendment):
            amendment_written = False
    return files, artifact, amendment_written


def _baseline_at(root: Path, baseline: Path | None) -> str | None:
    """`--baseline`'s repository-relative path, or None without one; `_root_path` keeps it
    under `root`, and any other path raises instead of leaving `--against` unchecked (AD-103)."""
    if baseline is None:
        return None
    return baseline.resolve().relative_to(root.resolve()).as_posix()


def _root_path(root: Path, path: Path) -> Path:
    """`path` as validate reads and writes it: relative to `root`, or absolute, and resolved,
    symlinks included, inside `root` (AD-103).

    A relative `path` that, read from a working directory outside `root`, leads into it repeats
    the root's own prefix (`--root mobile --baseline mobile/b.json`). While nothing exists at
    the root-relative path, it is refused: never read or written one directory too deep.
    """
    repository: Path = root.resolve()
    named: Path = repository / path
    target: Path = named.resolve()
    if repository not in target.parents:
        raise ValueError(f"{path} resolves to {target}, outside the root {repository}")
    # The working directory is already resolved, so it compares with `repository` directly.
    cwd: Path = Path.cwd()
    from_cwd: Path = path.resolve()
    if (
        not target.exists()
        and from_cwd != target
        and repository in from_cwd.parents
        and repository not in (cwd, *cwd.parents)
    ):
        raise ValueError(
            f"{path} is relative to --root {repository}: it names {target}, which does not "
            f"exist, not {from_cwd}; pass {from_cwd.relative_to(repository).as_posix()}"
        )
    return target


def run_validate(
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
    *,
    write_graph: bool = False,
    baseline: Path | None = None,
    write_baseline: bool = False,
    accept_new: bool = False,
    against: str | None = None,
    against_config: ScanConfig | None = None,
    amendment: Path | None = None,
    write_amendment: bool = False,
    decided_by: str | None = None,
    rationale: str | None = None,
) -> tuple[RunResult, FilesToWrite]:
    """Validate contract structure, repository references and observed architecture.

    AD-46/AD-57: with `write_graph`, every rewritten graph page comes back for the caller to
    write, the way `run_init` returns its files.

    AD-52/AD-77: with `baseline`, the violations that file already states are known debt, and
    only the difference is reported - as `failures` with exit 1. A missing baseline may be
    created with `write_baseline`; an existing one is compared before it is rewritten. New or
    increased fingerprints refuse that rewrite unless `accept_new` is explicit, and the refused
    run's last failure names `--accept-new` (AD-106). Resolved-only drift may rewrite the file
    and shrinks the debt.

    AD-89: `declarations.measurement_budgets` selects deterministic scalar measurements whose
    accepted values share that baseline. A rise is new debt; a fall must rewrite the baseline.

    AD-61 (#11): with `against`, the contract at that Git revision - and, when `baseline` is
    also given, the baseline file there too - is compared with the one being validated;
    every widening (ir.widening.contract_widenings, ir.widening.baseline_widenings) is a
    `failures` entry with exit 1 unless `amendment` binds exactly this before/after pair.
    `write_amendment` writes that binding instead of checking it.

    AD-103: `baseline` and `amendment` are relative to `root`, like the contract, or absolute;
    either way one that resolves outside `root` is refused, so no write can land outside it.

    AD-105: a component package moved since `against` proposes a rename. One that keeps every
    relation between the old names, leaves no scanned module under an old prefix and renames the
    old contract into one that still parses is applied to the old side before comparing and
    named in `renames`.
    """
    if baseline is not None:
        try:
            baseline = _root_path(root, baseline)
        except ValueError as error:
            return _baseline_invalid(root / baseline, error, _BASELINE_INSIDE_ROOT), FilesToWrite()
    if amendment is not None:
        try:
            amendment = _root_path(root, amendment)
        except ValueError as error:
            return _amendment_invalid(root / amendment, error), FilesToWrite()
    known: tuple[KnownViolation, ...] = ()
    known_budgets: tuple[MeasurementBudget, ...] = ()
    baseline_exists = baseline is not None and baseline.exists()
    if baseline is not None and (not write_baseline or baseline_exists):
        try:
            parsed_baseline = parse_validation_baseline(decode_json(baseline.read_bytes()))
            known = parsed_baseline.violations
            known_budgets = parsed_baseline.budgets
        except (OSError, ValueError) as error:
            remedy = _BASELINE_CORRECT if baseline_exists else _BASELINE_WRITE
            return _baseline_invalid(baseline, error, remedy), FilesToWrite()
    parsed_contract = _parse_contract_or_invalid(root, config)
    if isinstance(parsed_contract, RunResult):
        return parsed_contract, FilesToWrite()
    contract = parsed_contract
    inside_tree = _inside_contract_tree(root, config.contract, contract)
    comparison_contract = contract if inside_tree is None else inside_tree.comparison_contract
    current_tree_digest = (
        contract_digest(contract) if inside_tree is None else inside_tree.comparison_digest
    )
    declarations = contract.declarations or ContractDeclarations()
    declared_budgets = tuple(item.name for item in declarations.measurement_budgets)
    if declared_budgets and baseline is None:
        return _budget_baseline_missing(), FilesToWrite()
    declared_labels = {*declared_budgets, *_name_budget_targets(declarations)}
    missing_budget_names = sorted(declared_labels - {item.label for item in known_budgets})
    if baseline is not None and baseline_exists and missing_budget_names and not write_baseline:
        missing = ", ".join(missing_budget_names)
        return _baseline_invalid(
            baseline,
            ValueError(f"measurement budget values are missing for: {missing}"),
            _BASELINE_WRITE,
        ), FilesToWrite()
    against_ctx, against_error = _resolve_against_context(
        root,
        config,
        against,
        baseline,
        amendment,
        write_amendment,
        decided_by,
        rationale,
        against_config,
    )
    if against_error is not None:
        return against_error, FilesToWrite()
    references = reference_diagnostics(root, config, contract)
    if references:
        return RunResult("validate", 2, diagnostics=references), FilesToWrite()
    observed = _observed_or_invalid(root, config, analyzer, contract)
    if isinstance(observed, RunResult):
        return observed, FilesToWrite()
    observation = observed
    violations = observed_violations(observation) if baseline is not None else ()
    resolved_public_entries = frozenset(
        _resolved_public_entries(contract, known, violations, observation)
    )
    diagnostics, edits = _repository_diagnostics(
        root,
        config,
        contract,
        observation,
        write_graph,
        baseline is None,
        resolved_public_entries,
        inside_tree,
    )
    if (
        write_amendment
        and baseline is not None
        and amendment is not None
        and _same_destination(baseline, amendment)
    ):
        diagnostics = [
            *diagnostics,
            _diagnostic(
                "amendment.invalid",
                "",
                str(amendment),
                "The amendment destination is also the baseline file.",
                "Choose separate baseline and amendment paths.",
            ),
        ]
    try:
        observed_budgets = selected_budgets(measure_python_ratchets(observation), declared_budgets)
    except RatchetError as error:
        diagnostics.append(
            _diagnostic(
                "observation.incomplete",
                "",
                "measurement_budgets",
                f"The measurement budgets cannot be decided: {error}",
                "Repair the analyzer evidence and retry.",
            )
        )
        observed_budgets = ()
    budget_results = interface_budgets(declarations, observation)
    budget_diagnostics = interface_budget_diagnostics(
        budget_results, report_exceeded=baseline is None
    )
    observed_budgets = (
        *observed_budgets,
        *(_name_budget(item) for item in budget_results if not item.uncounted),
    )
    if baseline_exists:
        budget_results = _compared_budgets(budget_results, known_budgets)
    cycle_rules = _cycle_rule_ids(comparison_contract)
    baseline_new, baseline_resolved = (
        violation_drift_counts(known, violations, cycle_rules=cycle_rules)
        if baseline_exists
        else (0, 0)
    )
    budget_new = budget_regressions(known_budgets, observed_budgets) if baseline_exists else 0
    refused = (
        write_baseline and baseline_exists and bool(baseline_new or budget_new) and not accept_new
    )
    comparison = (
        compare_violations(known, violations, cycle_rules=cycle_rules, refused=refused)
        if baseline_exists
        else ()
    )
    budget_comparison = (
        compare_budgets(
            known_budgets, observed_budgets, against=against is not None, refused=refused
        )
        if baseline_exists
        else ()
    )
    baseline_failures = (*comparison, *budget_comparison) if not write_baseline or refused else ()
    interface_narrowings = tuple(
        f"resolved public entry: {entry} is no longer reached; remove it from {component}.public"
        for component, entry in sorted(resolved_public_entries)
    )
    rename = _rename_since(against_ctx, contract, observation, root, config, analyzer)
    after_policy_digest = None
    if baseline is not None:
        if write_baseline and not refused:
            after_policy_digest = baseline_digest(violations, observed_budgets)
        else:
            after_policy_digest = baseline_digest(known, known_budgets)
    result = _observed_result(
        observation,
        [*diagnostics, *budget_diagnostics],
        baseline_new=baseline_new if baseline is not None else None,
        baseline_resolved=baseline_resolved if baseline is not None else None,
        interface_budgets=budget_results or None,
    )
    # Diagnostics decide artifact eligibility; widening failures can only change exit 0 to 1.
    files, artifact, amendment_written = _artifact_files(
        root=root,
        write_baseline=write_baseline and not refused,
        baseline=baseline,
        violations=violations,
        budgets=observed_budgets,
        against=against_ctx,
        edits=edits,
        exit_code=result.exit_code,
        current_digest=current_tree_digest,
        after_baseline_digest=after_policy_digest,
        refused=refused,
    )
    widening_failures, widening_findings, amendment_status = _widening_failures(
        against_ctx,
        comparison_contract,
        rename,
        baseline,
        violations if write_baseline and not refused else known,
        observed_budgets if write_baseline and not refused else known_budgets,
        cycle_rules,
        current_tree_digest,
        after_policy_digest,
        amendment_written=amendment_written,
    )
    failures = (
        *baseline_failures,
        *interface_narrowings,
        *widening_failures,
        *((_WRITE_REFUSED,) if refused else ()),
    )
    result = replace(
        result,
        exit_code=2 if result.exit_code == 2 else 1 if failures else 0,
        failures=failures,
        widenings=widening_findings if against is not None else None,
        amendment_status=amendment_status,
    )
    if against is not None:
        result = replace(result, renames=rename.prefixes if rename is not None else ())
    # AD-100: a failing run whose calls_unresolved value moved from an accepted one names the
    # call sites against the other revision's code; only such a run pays for the second scan.
    # A revision without the contract has no declarations to observe that code under (AD-104).
    observed_calls = _calls_unresolved(observed_budgets)
    accepted_calls = {_calls_unresolved(known_budgets), _calls_unresolved(against_ctx.budgets)}
    if (
        against is not None
        and isinstance(against_ctx.contract, ArchitectureContract)
        and result.exit_code == 1
        and observed_calls is not None
        and accepted_calls != {observed_calls}
    ):
        changes, note = _unresolved_calls_since(root, config, analyzer, against, observation)
        result = replace(result, unresolved_call_changes=changes, unresolved_call_note=note)
    return (result if artifact is None else replace(result, artifact=artifact)), FilesToWrite(files)
