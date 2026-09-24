# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compose immutable inputs, host evidence and architecture checks."""

from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.ir.codec import canonical_report_bytes, declaration_paths, decode_json, parse_lock
from archkeel.ir.digest import package_digest
from archkeel.ir.host_records import parse_records
from archkeel.ir.lock import LOCK_PATH, AcceptedLock, LockError, verify_observation
from archkeel.ir.measurements import Measurements, RatchetError
from archkeel.ir.model import (
    CheckProvenance,
    Diagnostic,
    DiagnosticError,
    Observation,
    ObservationResult,
    RuleVerdict,
    RunResult,
    UnresolvedCallChange,
)
from archkeel.ir.trace import trace_valid_violations, validate_evidence_classes

from .delta import build_architecture_delta
from .expectation import (
    ArchitectureExpectation,
    evaluate_expectation,
    parse_expectation,
    sha256_bytes,
)
from .git import (
    GitError,
    changed_paths,
    check_git_order,
    parents,
    read_blob,
    relative_path,
    remote_tip,
)
from .ordering import check_order
from .ports import Analyzer, Host, ScanConfig
from .ratchets import measure_python_ratchets, unresolved_call_changes
from .snapshot import SnapshotError, materialize_git_snapshot


def inspect_observation(model: Observation) -> tuple[Measurements, RuleVerdict]:
    validate_evidence_classes(model)
    measurements = measure_python_ratchets(model)
    violations = trace_valid_violations(model)
    if len(violations) != len(model.records("violations") or ()):
        raise ValueError("violation records lack a complete rule/fact/source trace")
    if violations:
        return measurements, "FAIL"
    # AD-92: one count decides both the verdict and the scalar a budget can pin.
    if measurements.scalars.unknown_positions:
        return measurements, "UNKNOWN"
    return measurements, "PASS"


def materialize_declarations(
    root: Path, commit: str, config: ScanConfig, destination: Path
) -> None:
    payload = read_blob(root, commit, config.contract)
    paths = declaration_paths(payload, config.contract)
    for path in sorted(paths):
        target = destination / relative_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_blob(root, commit, path))


def _authenticate_inputs(
    root: Path,
    *,
    config: ScanConfig,
    baseline: str,
    expectation_commit: str,
    head: str,
    expected_path: str,
    expected_digest: str,
    accepted_branch: str,
) -> tuple[AcceptedLock, bytes, ArchitectureExpectation]:
    """Authenticate the accepted lock, contract inputs and signed expectation."""
    if baseline != remote_tip(root, accepted_branch):
        raise GitError("baseline is not the current accepted origin branch tip")
    try:
        lock_bytes = read_blob(root, baseline, LOCK_PATH)
    except (GitError, SnapshotError) as error:
        raise LockError(f"cannot load accepted lock: {error}") from error
    lock = parse_lock(lock_bytes)
    if parents(root, baseline) != [lock.accepted_commit] or changed_paths(
        root, lock.accepted_commit, baseline
    ) != {LOCK_PATH}:
        raise LockError("baseline must be a lock-only commit immediately after accepted code")
    if lock.config_digest != config.digest or lock.checker_digest != package_digest():
        raise LockError("accepted configuration or checker package differs")
    expected_bytes = read_blob(root, expectation_commit, expected_path)
    if sha256_bytes(expected_bytes) != expected_digest:
        raise DiagnosticError(
            Diagnostic(
                "parse_error",
                expected_path,
                "Expectation digest mismatch; the declaration cannot be authenticated.",
                "Supply the published expectation and its correct digest.",
            )
        )
    expectation = parse_expectation(decode_json(expected_bytes))
    if (
        expectation.accepted_digest != sha256_bytes(lock_bytes)
        or expectation.baseline_commit != baseline
    ):
        raise LockError("expectation does not bind the accepted lock and baseline")
    for path in (LOCK_PATH, config.contract):
        if read_blob(root, baseline, path) != read_blob(root, head, path):
            raise LockError(f"candidate changed accepted policy input: {path}")
    return lock, lock_bytes, expectation


def observe_revision(
    analyzer: Analyzer,
    root: Path,
    revision: str,
    config: ScanConfig,
    *,
    declared_at: str,
) -> ObservationResult:
    """Observe one commit's scoped Python files under the declarations `declared_at` holds.

    `check` observes the accepted commit and the candidate under the lock commit's
    declarations; `validate --against` observes a revision under its own (AD-100).
    """
    with TemporaryDirectory(prefix="archkeel-declarations-") as temporary:
        declarations = Path(temporary)
        materialize_declarations(root, declared_at, config, declarations)
        with materialize_git_snapshot(root, revision, roots=config.roots) as snapshot:
            return analyzer(
                snapshot.root,
                roots=config.roots,
                namespace=config.namespace,
                contract=config.contract,
                git_head=snapshot.git_head,
                dirty=False,
                contract_root=declarations,
                language=config.language,
            )


def _incomplete(result: ObservationResult) -> RunResult:
    """Build the shared exit-2 result for a snapshot that failed to observe."""
    observation = result.observation
    return RunResult(
        "check",
        2,
        diagnostics=result.diagnostics,
        coverage=result.coverage,
        observation=observation,
        python_version=observation.python_version if observation is not None else None,
    )


def _measurement_incomplete(observation: Observation, error: RatchetError) -> RunResult:
    return RunResult(
        "check",
        2,
        diagnostics=(
            Diagnostic(
                "contract_invalid",
                "measurement_budgets",
                f"The measurement budgets cannot be decided: {error}",
                "Repair the analyzer evidence and retry.",
                "",
                "observation.incomplete",
            ),
        ),
        coverage=observation.coverage,
        observation=observation,
        python_version=observation.python_version,
    )


def run_check(
    root: Path,
    *,
    config: ScanConfig,
    baseline: str,
    expectation_commit: str,
    head: str,
    expected_path: str,
    expected_digest: str,
    branch: str,
    accepted_branch: str,
    host_records_path: Path | None,
    environ: Mapping[str, str],
    host: Host,
    analyzer: Analyzer,
) -> RunResult:
    lock, lock_bytes, expectation = _authenticate_inputs(
        root,
        config=config,
        baseline=baseline,
        expectation_commit=expectation_commit,
        head=head,
        expected_path=expected_path,
        expected_digest=expected_digest,
        accepted_branch=accepted_branch,
    )

    git_failures = check_git_order(
        root,
        baseline=baseline,
        expectation=expectation_commit,
        head=head,
        expected_path=expected_path,
        branch=branch,
    )
    host_records = (
        parse_records(decode_json(host_records_path.read_bytes()))
        if host_records_path is not None
        else host(root, expectation_sha=expectation_commit, candidate_sha=head, environ=environ)
    )
    ordering_failures = check_order(
        host_records, expectation_sha=expectation_commit, candidate_sha=head
    )
    accepted_result = observe_revision(
        analyzer, root, lock.accepted_commit, config, declared_at=baseline
    )
    accepted = accepted_result.observation
    if accepted_result.diagnostics or accepted is None:
        return _incomplete(accepted_result)
    try:
        accepted_measurements = measure_python_ratchets(accepted)
    except RatchetError as error:
        return _measurement_incomplete(accepted, error)
    verify_observation(
        lock,
        observation_digest=sha256_bytes(canonical_report_bytes(accepted)),
        measurements=accepted_measurements,
    )
    candidate_result = observe_revision(analyzer, root, head, config, declared_at=baseline)
    candidate = candidate_result.observation
    if candidate_result.diagnostics or candidate is None:
        return _incomplete(candidate_result)
    try:
        inspect_observation(accepted)
        measurements, declared = inspect_observation(candidate)
    except RatchetError as error:
        return _measurement_incomplete(candidate, error)
    # AD-100: the sites explain a regression and never decide one, so call records that do not
    # add up leave them unnamed instead of leaving the whole check unchecked.
    call_changes: tuple[UnresolvedCallChange, ...] | None
    call_note = None
    try:
        call_changes = unresolved_call_changes(accepted, candidate)
    except RatchetError:
        call_changes = None
        call_note = (
            "the call records do not add up to the coverage counts, so no call site is named"
        )
    delta = build_architecture_delta(
        accepted,
        candidate,
        baseline_digest=sha256_bytes(canonical_report_bytes(accepted)),
        head_digest=sha256_bytes(canonical_report_bytes(candidate)),
        checker_digest=package_digest(),
    )
    result = evaluate_expectation(delta, expectation)
    failures = sorted([*git_failures, *ordering_failures, *result.failures])
    return RunResult(
        "check",
        1 if failures or declared == "FAIL" else 0,
        observation_complete="PASS",
        declared_rules=declared,
        expectation_fulfilled="FAIL" if failures else "PASS",
        git_predicate="FAIL" if git_failures else "PASS",
        host_source="supplied_records" if host_records_path is not None else "gitlab_mr_versions",
        host_order="FAIL" if ordering_failures else "PASS",
        coverage=candidate.coverage,
        python_version=candidate.python_version,
        measurements=measurements,
        failures=tuple(failures),
        delta=delta,
        provenance=CheckProvenance(
            baseline, expectation_commit, head, sha256_bytes(lock_bytes), expected_digest
        ),
        unresolved_call_changes=call_changes,
        unresolved_call_note=call_note,
    )
