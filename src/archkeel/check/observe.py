# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build observations by injecting a source collector into Core evaluation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
)
from archkeel.ir.codec import (
    ContractInputError as _ContractInputError,
)
from archkeel.ir.codec import (
    load_inside_contract_tree as _load_inside_contract_tree,
)
from archkeel.ir.facts import SOURCE_RESOLUTION_GAP_KIND, SourceFacts, UnresolvedTarget
from archkeel.ir.model import (
    ArchitectureContract as _ArchitectureContract,
)
from archkeel.ir.model import (
    Diagnostic,
    DiagnosticKind,
    Observation,
    ObservationResult,
    UmlEligibility,
    stable_id,
)
from archkeel.ir.model import (
    contract_relative_path as _contract_relative_path,
)
from archkeel.ir.profiles import PROFILES, Language
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    DartSettings,
    PythonSettings,
    ResolverSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

from .declarations import ContractError, load_contract
from .observation import assemble_observation
from .ports import SourceCollector
from .runtime import runtime_diagnostic


def _failure(kind: DiagnosticKind, subject: str, claim: str, remedy: str) -> ObservationResult:
    return ObservationResult(None, None, (Diagnostic(kind, subject, claim, remedy),))


def _contract_input_failure(error: _ContractInputError) -> ObservationResult:
    return ObservationResult(
        None,
        None,
        (
            Diagnostic(
                "parse_error",
                error.subject,
                f"The contract declaration is invalid: {error}.",
                "Correct the contract declaration at this location.",
                error.pointer,
            ),
        ),
    )


def _nested_reference_failure(
    root: Path, contract_path: Path, contract: _ArchitectureContract, digest: str
) -> ObservationResult | None:
    repository = root.resolve()
    identity = contract_path.resolve().relative_to(repository).as_posix()

    def read_inside(reference: str) -> tuple[bytes, str]:
        relative = _contract_relative_path(reference)
        if relative is None:
            raise ValueError("unsafe repository path")
        target = (repository / relative).resolve()
        if not target.is_relative_to(repository) or not target.is_file():
            raise ValueError("file is missing or outside the repository")
        return target.read_bytes(), target.relative_to(repository).as_posix()

    tree = _load_inside_contract_tree(
        identity,
        contract,
        digest,
        identity,
        read_inside,
    )
    for issue in tree.issues:
        if issue.input_error is not None:
            error = _ContractInputError(
                f"{issue.pointer}{issue.input_error.pointer}",
                issue.input_error.subject,
                str(issue.input_error),
            )
            return _contract_input_failure(error)
    return None


def _contract_failure(path: Path, contract_root: Path) -> ObservationResult | None:
    try:
        contract, digest = load_contract(path)
    except ContractVersionError as error:
        return _failure(
            "parse_error",
            path.name,
            f"Contract schema {error.actual} cannot be validated as {CONTRACT_SCHEMA_VERSION}.",
            "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
        )
    except _ContractInputError as error:
        return _contract_input_failure(error)
    except ContractError as error:
        return _failure(
            "parse_error",
            path.name,
            f"The architecture contract cannot be decoded: {error}",
            "Correct the contract structure and run report again.",
        )
    return _nested_reference_failure(contract_root, path, contract, digest)


# AD-97: a contract item the profile cannot decide is refused, never read as PASS.
_RULE_FAILURES: Final[dict[str, tuple[DiagnosticKind, str]]] = {
    "rule-without-subjects": (
        "rule_without_subjects",
        "Correct the rule selectors or scan scope.",
    ),
    "rule-unsupported-by-profile": (
        "rule_unsupported_by_profile",
        "Remove the rule or declaration, or run a profile that supports it.",
    ),
}
_SOURCE_NAME: Final[dict[Language, str]] = {
    "python": "Python",
    "dart": "Dart",
    "typescript": "TypeScript",
}
_SOURCE_REMEDY: Final[dict[Language, str]] = {
    "python": "Inspect the reported failure using the declared target runtime; "
    "rerun after resolving its cause.",
    "typescript": "Correct the reported TypeScript configuration or import resolution and retry.",
    "dart": "Correct the reported Dart source syntax, directive, URI, part declaration or "
    "pubspec name; rerun after resolving its cause.",
}


def observation_diagnostics(
    model: Observation, runtime: Diagnostic | None, language: Language
) -> tuple[Diagnostic, ...]:
    """Read completeness from the recorded coverage, runtime and analyzer profile."""
    diagnostics: list[Diagnostic] = []
    for failure in model.coverage.failures:
        rule_failure = _RULE_FAILURES.get(failure.kind)
        if rule_failure is None and runtime is not None:
            diagnostics.append(runtime)
            continue
        kind, remedy = rule_failure or ("parse_error", _SOURCE_REMEDY[language])
        diagnostics.append(
            Diagnostic(
                kind,
                ", ".join(failure.rule_ids or failure.subjects) or failure.id,
                f"Scan completeness cannot be established: {failure.title}",
                remedy,
            )
        )
    if runtime is not None and runtime not in diagnostics:
        diagnostics.append(runtime)
    if model.coverage.files_discovered == 0:
        diagnostics.append(
            Diagnostic(
                "scope_empty",
                ", ".join(model.source.scope) or "scan.roots",
                f"The configured scope contains no observable {_SOURCE_NAME[language]} files.",
                f"Set scan.roots to an existing {_SOURCE_NAME[language]} source directory.",
            )
        )
    if model.coverage.rules is None:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage.rules",
                "Rule applicability coverage is missing.",
                "Reinstall a complete Archkeel distribution.",
            )
        )
    if model.coverage.status == "FAIL" and not diagnostics:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage",
                "The analyzer reported incomplete coverage without a cause.",
                "Inspect the analyzer coverage and repair its inputs.",
            )
        )
    return tuple(diagnostics)


def _partial_uml_source_is_eligible(
    facts: SourceFacts, model: Observation, runtime: Diagnostic | None
) -> bool:
    gaps = facts.coverage.gaps
    selected = set(facts.coverage.selected_files)
    selected_inputs = {item.path for item in facts.inputs if item.role == "selected"}
    if (
        not gaps
        or facts.coverage.full_scope
        or any(item.kind != SOURCE_RESOLUTION_GAP_KIND for item in gaps)
        or not selected
        or selected_inputs != selected
        or facts.coverage.files_read != len(selected)
        or facts.coverage.files_parsed != len(selected)
        or model.coverage.files_discovered != len(selected)
        or model.coverage.files_read != len(selected)
        or model.coverage.files_parsed != len(selected)
        or model.coverage.status != "FAIL"
        or model.coverage.rules != "PASS"
        or model.runtime is None
        or runtime is not None
    ):
        return False

    failures = {item.id: item for item in model.coverage.failures}
    source_gap_ids = {item.id for item in gaps}
    if any(failures.get(item.id) != item for item in gaps):
        return False
    derived_ids = {
        stable_id("UNKNOWN-IMPORT", item.import_id)
        for item in facts.imports
        if isinstance(item, UnresolvedTarget)
    }
    if set(failures) != source_gap_ids | derived_ids:
        return False
    return all(failures[identity].kind == SOURCE_RESOLUTION_GAP_KIND for identity in derived_ids)


def _observe(
    collector: SourceCollector,
    tsconfig: str,
    source_root: Path,
    *,
    roots: tuple[str, ...],
    namespace: str,
    contract: str,
    git_head: str,
    dirty: bool,
    contract_root: Path,
    language: Language = "python",
) -> ObservationResult:
    source_root = source_root.resolve()
    contract_root = contract_root.resolve()
    suffix = PROFILES[language].source_suffix
    try:
        contract_file = contract_root / contract
        if failure := _contract_failure(contract_file, contract_root):
            return failure
        for root in roots:
            directory = source_root / root
            file_root = language == "typescript" and directory.is_file()
            if not directory.is_dir() and not file_root:
                return _failure(
                    "scope_empty",
                    root,
                    "The scan root does not exist.",
                    "Correct scan.roots in archkeel.toml.",
                )
            paths = (directory,) if file_root else directory.rglob(f"*{suffix}")
            for path in paths:
                if not path.resolve().is_relative_to(source_root):
                    return _failure(
                        "parse_error",
                        str(path),
                        "Source path escapes repository.",
                        "Remove the source symlink or correct the scan scope.",
                    )
        resolver: ResolverSettings = (
            PythonSettings()
            if language == "python"
            else DartSettings()
            if language == "dart"
            else TypeScriptSettings(tsconfig)
        )
        request = CollectionRequest(
            SnapshotInput(str(source_root), git_head, dirty),
            SourceScope(roots, namespace),
            resolver,
        )
        facts = collector.collect(request)
        if isinstance(facts, CollectionError):
            kind: DiagnosticKind = (
                "timeout"
                if facts.kind == "timeout"
                else "missing_tool"
                if facts.kind == "missing_tool"
                else "parse_error"
            )
            return _failure(
                kind,
                facts.subject,
                facts.message,
                "Repair the configured collector or its source inputs and retry.",
            )
        model, _ = assemble_observation(
            facts,
            contract_root=contract_root,
            contract_path=contract_file,
            roots=roots,
            namespace=namespace,
            language=language,
        )
        runtime = runtime_diagnostic(model.runtime) if model.runtime is not None else None
        diagnostics = observation_diagnostics(model, runtime, language)
        eligibility = (
            UmlEligibility.VALIDATED_PARTIAL_SOURCE
            if _partial_uml_source_is_eligible(facts, model, runtime)
            else UmlEligibility.BLOCKED
        )
        return ObservationResult(
            model,
            model.coverage,
            diagnostics,
            eligibility,
            diagnostics if eligibility == UmlEligibility.VALIDATED_PARTIAL_SOURCE else (),
        )
    except OSError as error:
        return _failure(
            "parse_error",
            str(source_root),
            str(error),
            "Repair the source or contract inputs and retry.",
        )
    except (ValueError, TypeError, KeyError) as error:
        return _failure(
            "parse_error",
            "source collection",
            str(error),
            "Repair the collector output to match the source facts protocol.",
        )


@dataclass(frozen=True, slots=True)
class Observer:
    collector: SourceCollector
    tsconfig: str = "tsconfig.json"

    def __call__(
        self,
        source_root: Path,
        *,
        roots: tuple[str, ...],
        namespace: str,
        contract: str,
        git_head: str,
        dirty: bool,
        contract_root: Path,
        language: Language = "python",
    ) -> ObservationResult:
        return _observe(
            self.collector,
            self.tsconfig,
            source_root,
            roots=roots,
            namespace=namespace,
            contract=contract,
            git_head=git_head,
            dirty=dirty,
            contract_root=contract_root,
            language=language,
        )
