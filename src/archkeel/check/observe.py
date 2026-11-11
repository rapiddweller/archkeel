# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build observations by injecting a source collector into Core evaluation."""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
)
from archkeel.ir.codec import (
    ContractInputError as _ContractInputError,
)
from archkeel.ir.collection_features import required_resolution_features
from archkeel.ir.facts import (
    RULE_FAMILY_NOT_COLLECTED_KIND,
    SOURCE_RESOLUTION_GAP_KIND,
    SourceFacts,
)
from archkeel.ir.facts import ResolutionRole as _ResolutionRole
from archkeel.ir.import_gaps import derived_unresolved_imports
from archkeel.ir.member_inventory import member_inventory_proof
from archkeel.ir.model import (
    Diagnostic,
    DiagnosticKind,
    Observation,
    ObservationResult,
    UmlEligibility,
    Verdict,
    stable_id,
)
from archkeel.ir.phases import Phase, PhaseClock, measured
from archkeel.ir.profiles import PROFILES, TEST_SCOPE_LANGUAGES, Language, is_test_source
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    PythonSettings,
    ResolverSettings,
    SnapshotInput,
    SourceScope,
    collection_request,
    fixed_settings,
)
from archkeel.ir.store_seam import close_store, keep_store_for

from .contract_tree import ContractInput, contract_input
from .declarations import ContractError, load_contract
from .gap_diagnostics import gap_diagnostic
from .observation import assemble_observation
from .pair_gaps import drop_allowed_pair_gaps
from .ports import ProducerKind, SourceCollector
from .runtime import runtime_diagnostic


def _failure(kind: DiagnosticKind, subject: str, claim: str, remedy: str) -> ObservationResult:
    close_store()  # AD-346: a failed observation keeps no store of an earlier collection.
    return ObservationResult(None, None, (Diagnostic(kind, subject, claim, remedy),))


def _contract_input_failure(error: _ContractInputError) -> ObservationResult:
    return ObservationResult(
        None,
        None,
        (
            Diagnostic(
                DiagnosticKind.PARSE_ERROR,
                error.subject,
                f"The contract declaration is invalid: {error}.",
                "Correct the contract declaration at this location.",
                error.pointer,
            ),
        ),
    )


def _contract_tree(path: Path, contract_root: Path) -> ObservationResult | ContractInput:
    try:
        contract, digest = load_contract(path)
    except ContractVersionError as error:
        return _failure(
            DiagnosticKind.PARSE_ERROR,
            path.name,
            f"Contract schema {error.actual} cannot be validated as {CONTRACT_SCHEMA_VERSION}.",
            "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
        )
    except _ContractInputError as error:
        return _contract_input_failure(error)
    except ContractError as error:
        return _failure(
            DiagnosticKind.PARSE_ERROR,
            path.name,
            f"The architecture contract cannot be decoded: {error}",
            "Correct the contract structure and run report again.",
        )
    loaded = contract_input(contract_root, path, contract, digest)
    for issue in loaded.tree.issues:
        if issue.input_error is not None:
            nested = _ContractInputError(
                f"{issue.pointer}{issue.input_error.pointer}",
                issue.input_error.subject,
                str(issue.input_error),
            )
            return _contract_input_failure(nested)
    return loaded


# AD-97: a contract item the profile cannot decide is refused, never read as PASS.
_RULE_FAILURES: Final[dict[str, tuple[DiagnosticKind, str]]] = {
    "rule-without-subjects": (
        DiagnosticKind.RULE_WITHOUT_SUBJECTS,
        "Correct the rule selectors or scan scope.",
    ),
    "rule-unsupported-by-profile": (
        DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE,
        "Remove the rule or declaration, or run a profile that supports it.",
    ),
    RULE_FAMILY_NOT_COLLECTED_KIND: (
        DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE,
        "Collect the facts under this contract, or use a collector that declares the family.",
    ),
}
_INSTALLED: Final = frozenset({"__pycache__", "node_modules"})
_SOURCE_NAME: Final[dict[Language, str]] = {
    Language.PYTHON: "Python",
    Language.DART: "Dart",
    Language.TYPESCRIPT: "TypeScript",
    Language.RUST: "Rust",
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
        kind, remedy = rule_failure or gap_diagnostic(failure, language)
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
                DiagnosticKind.SCOPE_EMPTY,
                ", ".join(model.source.scope) or "scan.roots",
                f"The configured scope contains no observable {_SOURCE_NAME[language]} files.",
                f"Set scan.roots to an existing {_SOURCE_NAME[language]} source directory.",
            )
        )
    if model.coverage.rules is None:
        diagnostics.append(
            Diagnostic(
                DiagnosticKind.PARSE_ERROR,
                "coverage.rules",
                "Rule applicability coverage is missing.",
                "Reinstall a complete Archkeel distribution.",
            )
        )
    if model.coverage.status == Verdict.FAIL and not diagnostics:
        diagnostics.append(
            Diagnostic(
                DiagnosticKind.PARSE_ERROR,
                "coverage",
                "The analyzer reported incomplete coverage without a cause.",
                "Inspect the analyzer coverage and repair its inputs.",
            )
        )
    if model.producer_kind not in (
        ProducerKind.PYTHON,
        ProducerKind.BUNDLED,
        ProducerKind.PINNED,
    ):
        diagnostics.append(_untrusted_producer_diagnostic(model.producer_kind))
    return tuple(diagnostics)


def _untrusted_producer_diagnostic(kind: ProducerKind | None) -> Diagnostic:
    """AD-344: an external collector, or a scan with no recorded producer, gives no PASS."""
    if kind is None:
        return Diagnostic(
            DiagnosticKind.INCOMPLETE_SCAN,
            "producer_kind",
            "The saved scan does not record its producer (producer not recorded). "
            "A rule cannot be proven without it.",
            "Run the scan again with this version of ArchKeel and save the result.",
        )
    return Diagnostic(
        DiagnosticKind.INCOMPLETE_SCAN,
        "scan.collector_argv",
        f"The scan used a configured collector (producer: {kind}). "
        "An external collector cannot prove a rule.",
        "Use the bundled collector, or pin the external collector by digest.",
    )


def _partial_uml_source_is_eligible(
    facts: SourceFacts, model: Observation, runtime: Diagnostic | None
) -> bool:
    gaps = facts.coverage.gaps
    selected = set(facts.coverage.selected_files)
    selected_inputs = {item.path for item in facts.inputs if item.role == _ResolutionRole.SELECTED}
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
        or model.coverage.status != Verdict.FAIL
        or model.coverage.rules != Verdict.PASS
        or model.runtime is None
        or runtime is not None
    ):
        return False

    failures = {item.id: item for item in model.coverage.failures}
    source_gap_ids = {item.id for item in gaps}
    if any(failures.get(item.id) != item for item in gaps):
        return False
    derived_ids = {
        stable_id("UNKNOWN-IMPORT", import_id) for import_id in derived_unresolved_imports(facts)
    }
    if set(failures) != source_gap_ids | derived_ids:
        return False
    return all(failures[identity].kind == SOURCE_RESOLUTION_GAP_KIND for identity in derived_ids)


def _observation_result(
    facts: SourceFacts,
    model: Observation,
    diagnostics: tuple[Diagnostic, ...],
    eligibility: UmlEligibility,
) -> ObservationResult:
    if (
        eligibility == UmlEligibility.VALIDATED_PARTIAL_SOURCE
        and "inner-uml-v1" in facts.capabilities.resolution_features
    ):
        proof = member_inventory_proof(model, facts.inputs)
        if proof is not None:
            model = replace(
                model,
                sections=tuple(
                    replace(section, records=(*section.records, proof))
                    if section.name == "scope_observations"
                    else section
                    for section in model.sections
                ),
            )
    return ObservationResult(
        model,
        model.coverage,
        diagnostics,
        eligibility,
        diagnostics if eligibility == UmlEligibility.VALIDATED_PARTIAL_SOURCE else (),
    )


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
    language: Language = Language.PYTHON,
    bundler: bool = False,
    exclude_test_sources: bool = False,
    excluded_tests: list[tuple[str, tuple[str, ...]]] | None = None,
    clock: PhaseClock | None = None,
    producer: ProducerKind,
) -> ObservationResult:
    source_root = source_root.resolve()
    contract_root = contract_root.resolve()
    suffix = PROFILES[language].source_suffix
    try:
        contract_file = contract_root / contract
        loaded = _contract_tree(contract_file, contract_root)
        if isinstance(loaded, ObservationResult):
            close_store()
            return loaded
        found: set[str] = set()
        listed: set[str] = set()
        for root in roots:
            directory = source_root / root
            file_root = language == Language.TYPESCRIPT and directory.is_file()
            if not directory.is_dir() and not file_root:
                return _failure(
                    DiagnosticKind.SCOPE_EMPTY,
                    root,
                    "The scan root does not exist.",
                    "Correct scan.roots in archkeel.toml.",
                )
            paths = (directory,) if file_root else directory.rglob(f"*{suffix}")
            for path in paths:
                relative = path.relative_to(source_root).as_posix()
                if is_test_source(relative, language) and not _INSTALLED.intersection(path.parts):
                    found.add(relative)
                if _collector_lists(relative) and path.is_file():
                    listed.add(relative)
                if not path.resolve().is_relative_to(source_root):
                    return _failure(
                        DiagnosticKind.PARSE_ERROR,
                        str(path),
                        "Source path escapes repository.",
                        "Remove the source symlink or correct the scan scope.",
                    )
        if exclude_test_sources and excluded_tests is not None and language != Language.RUST:
            # The files of this one listing are the files the collector reads (AD-313).
            if all(sha != git_head for sha, _ in excluded_tests):
                excluded_tests.append((git_head, tuple(sorted(found))))
        resolver: ResolverSettings = fixed_settings(language, tsconfig, bundler) or PythonSettings(
            features=tuple(
                sorted(required_resolution_features(loaded.tree.root, loaded.tree.mounts))
            )
        )
        if exclude_test_sources and language not in TEST_SCOPE_LANGUAGES:
            return _failure(
                DiagnosticKind.SCOPE_EMPTY,
                "scan.exclude_test_sources",
                f"The {language} collector has no test-source rule.",
                "Remove scan.exclude_test_sources for this language.",
            )
        request = collection_request(
            SnapshotInput(str(source_root), git_head, dirty),
            SourceScope(roots, namespace, exclude_test_sources),
            resolver,
        )
        facts = collector.collect(request)
        # AD-346: the observation uses the store only if the store holds these facts.
        if isinstance(facts, CollectionError):
            close_store()
        else:
            keep_store_for(facts)
        if isinstance(facts, CollectionError):
            kind: DiagnosticKind = (
                DiagnosticKind.TIMEOUT
                if facts.kind == CollectionErrorKind.TIMEOUT
                else DiagnosticKind.MISSING_TOOL
                if facts.kind == CollectionErrorKind.MISSING_TOOL
                else DiagnosticKind.PARSE_ERROR
            )
            return _failure(
                kind,
                facts.subject,
                facts.message,
                "Repair the configured collector or its source inputs and retry.",
            )
        if exclude_test_sources and excluded_tests is not None and language == Language.RUST:
            # The Rust collector owns its test rule: the test files are the regular files with a
            # UTF-8 name that it listed and did not select (the others it drops as gaps).
            if all(sha != git_head for sha, _ in excluded_tests):
                left_out = sorted(listed - set(facts.coverage.selected_files))
                excluded_tests.append((git_head, tuple(left_out)))
        facts = drop_allowed_pair_gaps(facts, loaded.contract, has_insides=bool(loaded.tree.mounts))
        with measured(clock, Phase.ASSEMBLE):
            model, _ = assemble_observation(
                facts,
                contract_root=contract_root,
                contract_path=contract_file,
                roots=roots,
                namespace=namespace,
                language=language,
                loaded=loaded,
                producer=producer,
            )
        runtime = runtime_diagnostic(model.runtime) if model.runtime is not None else None
        diagnostics = observation_diagnostics(model, runtime, language)
        eligibility = (
            UmlEligibility.VALIDATED_PARTIAL_SOURCE
            if producer is not ProducerKind.EXTERNAL
            and _partial_uml_source_is_eligible(facts, model, runtime)
            else UmlEligibility.BLOCKED
        )
        return _observation_result(facts, model, diagnostics, eligibility)
    except OSError as error:
        return _failure(
            DiagnosticKind.PARSE_ERROR,
            str(source_root),
            str(error),
            "Repair the source or contract inputs and retry.",
        )
    except (ValueError, TypeError, KeyError) as error:
        return _failure(
            DiagnosticKind.PARSE_ERROR,
            "source collection",
            str(error),
            "Repair the collector output to match the source facts protocol.",
        )


def _collector_lists(relative: str) -> bool:
    """The Rust collector lists no `target` or hidden directory and no name that is not UTF-8."""
    if re.search(r"(?:^|/)(?:target|\.[^/]*)/", relative):
        return False
    try:
        relative.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Observer:
    collector: SourceCollector
    tsconfig: str = "tsconfig.json"
    bundler: bool = False
    clock: PhaseClock | None = None
    exclude_test_sources: bool = False
    # Required: the host says who made the facts. Only observer_for derives it from the launch.
    producer: ProducerKind = field(kw_only=True)

    # AD-313: the test files of each observed revision, by git head; the first scan of a head wins.
    excluded_tests: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def excluded_for(self, head: str | None = None) -> tuple[str, ...]:
        """The test files of the scan of `head` (a short sha is fine), or of the first scan."""
        return next(
            (found for sha, found in self.excluded_tests if head is None or sha.startswith(head)),
            (),
        )

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
        language: Language = Language.PYTHON,
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
            bundler=self.bundler,
            exclude_test_sources=self.exclude_test_sources,
            excluded_tests=self.excluded_tests,
            clock=self.clock,
            producer=self.producer,
        )
