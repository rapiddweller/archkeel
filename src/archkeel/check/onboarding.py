# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive a first architecture contract from one observation of the repository."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Final

from archkeel.ir.codec import contract_bytes
from archkeel.ir.decisions import (
    DOCUMENT_PATH,
    identifier,
    open_decision_summary,
    open_decisions,
)
from archkeel.ir.facts import SourceNameVisibility, parse_source_name_visibility
from archkeel.ir.identity import module_identity
from archkeel.ir.model import (
    ArchitectureContract,
    ArchitectureRule,
    ArchitectureRuleKind,
    CompleteAssignmentRule,
    CompleteRequiresRule,
    ComponentOwnership,
    ComponentRole,
    ContractComponent,
    ContractVersion,
    DecisionMaker,
    Diagnostic,
    DiagnosticError,
    DraftedComponentSize,
    FirstLook,
    GraphTopologyLevel,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    Observation,
    OpenDecision,
    Record,
    RequiredComponent,
    RunResult,
    in_scope,
    int_value,
    parse_graph_topology_level,
    text_value,
)
from archkeel.ir.model import (
    AssessmentStatus as _AssessmentStatus,
)
from archkeel.ir.model import (
    Command as _Command,
)
from archkeel.ir.model import DiagnosticKind as _DiagnosticKind
from archkeel.ir.model import (
    ExpectationOutcome as _ExpectationOutcome,
)
from archkeel.ir.profiles import Language
from archkeel.ir.source_records import source_name_visibility as _source_name_visibility
from archkeel.ir.structure import StructureLevel, StructureMetric, scope_metrics

from .ports import Analyzer, FilesToWrite, ScanConfig
from .ratchets import measure_python_ratchets
from .snapshot import SnapshotError
from .uml import observe_repository
from .validation import COMPONENT_GRAPH_MARKER, mermaid_edges, observed_component_edges

CONFIG_PATH: Final = "archkeel.toml"
CONTRACT_PATH: Final = "architecture-contract.json"
# Written by `archkeel guide`; init guards it like the architecture page.
GUIDE_PATH: Final = "docs/architecture/contract-guide.md"
# AD-266: the plain sentence that says the adopted state was observed, not reviewed.
ADOPTED_RATIONALE: Final = "Observed when the contract was drafted; not reviewed."
_REQUIRES_COMPLETE_ID: Final = "REQUIRES-COMPLETE"


def _project_import_name(root: Path) -> str | None:
    """Return pyproject.toml's `[project] name` in wheel file-name form, if one is declared."""
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    project = pyproject.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return re.sub(r"[-_.]+", "_", name).lower() if isinstance(name, str) else None


def detect_source(root: Path) -> tuple[str, str]:
    """Return the scan root and namespace of the only top-level package, or of the one
    package named after the project when there are several (AD-47)."""
    base = root / "src" if (root / "src").is_dir() else root
    packages = sorted(path for path in base.iterdir() if (path / "__init__.py").is_file())
    name = _project_import_name(root)
    chosen = packages if len(packages) == 1 else [p for p in packages if p.name.lower() == name]
    if len(chosen) != 1:
        found = ", ".join(path.relative_to(root).as_posix() for path in packages) or "none"
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.SCOPE_EMPTY,
                str(base),
                "Expected one top-level Python package, or one matching pyproject.toml's "
                f"[project] name ({name or 'missing'}); found {found}.",
                "Pass --source <directory> and --namespace <package> to archkeel init.",
            )
        )
    return chosen[0].relative_to(root).as_posix(), chosen[0].name


def _has_cycle(labels: tuple[str, ...], edges: frozenset[tuple[str, str]]) -> bool:
    targets = {label: {target for source, target in edges if source == label} for label in labels}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(label: str) -> bool:
        if label in visiting:
            return True
        if label in done:
            return False
        visiting.add(label)
        found = any(visit(target) for target in targets[label])
        visiting.discard(label)
        done.add(label)
        return found

    return any(visit(label) for label in labels)


def interface_entries(
    module: str,
    used_names: set[str],
    whole_module: bool,
    all_exports: bool,
    public_names: set[str],
) -> list[str]:
    """Propose the AD-9 `public` entries a module's cross-component uses would need."""
    names = {
        name
        for name in used_names
        if _source_name_visibility(name) is SourceNameVisibility.PUBLIC_NAME
    }
    if whole_module or all_exports or (bool(public_names) and 2 * len(names) >= len(public_names)):
        return [module]
    return sorted(f"{module}:{name}" for name in names)


def module_all_exports(modules: Iterable[Record]) -> dict[str, bool]:
    """Map each module's qualified name to whether it declares a non-empty `__all__`."""
    return {
        name: bool(module.data.get("all_exports"))
        for module in modules
        if isinstance((name := module.data.get("qualified_name")), str)
    }


def public_top_level_names(symbols: Iterable[Record]) -> dict[str, set[str]]:
    """Group each module's public, non-underscore top-level class and function names."""
    names: dict[str, set[str]] = {}
    for symbol in symbols:
        module = symbol.data.get("module")
        name = symbol.data.get("name")
        if (
            symbol.data.get("parent") is None
            and not symbol.data.get("definition_contexts")
            and parse_source_name_visibility(symbol.data.get("visibility"))
            is SourceNameVisibility.PUBLIC_NAME
            and isinstance(module, str)
            and isinstance(name, str)
        ):
            names.setdefault(module, set()).add(name)
    return names


def _crossing_targets(
    observation: Observation, contract: ArchitectureContract
) -> dict[str, tuple[str, bool, set[str]]]:
    """Group cross-component imports by the target module they actually cross (AD-9)."""
    targets: dict[str, tuple[str, bool, set[str]]] = {}
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is None or target is None or source.label == target.label:
            continue
        label, whole_module, names = targets.get(target_module, (target.label, False, set()))
        symbol = record.data.get("symbol")
        if symbol in (None, "*"):
            whole_module = True
        elif isinstance(symbol, str):
            names = names | {symbol}
        targets[target_module] = (label, whole_module, names)
    return targets


def _drafted_public(
    observation: Observation, contract: ArchitectureContract
) -> dict[str, tuple[str, ...]]:
    """Propose each component's AD-9 `public` entries from its inbound crossing imports."""
    targets = _crossing_targets(observation, contract)
    all_exports = module_all_exports(observation.records("modules") or ())
    public_names = public_top_level_names(observation.records("symbols") or ())
    proposals: dict[str, set[str]] = {}
    for module, (label, whole_module, names) in targets.items():
        entries = interface_entries(
            module,
            names,
            whole_module,
            all_exports.get(module, False),
            public_names.get(module, set()),
        )
        proposals.setdefault(label, set()).update(entries)
    return {label: tuple(sorted(entries)) for label, entries in proposals.items()}


def _typescript_components(
    observation: Observation, namespace: str, roots: tuple[str, ...]
) -> tuple[dict[str, str], tuple[ContractComponent, ...]]:
    groups: dict[PurePosixPath, list[str]] = {}
    directories: set[PurePosixPath] = set()
    for record in observation.records("modules") or ():
        name, file = record.data.get("qualified_name"), record.data.get("file")
        if not isinstance(name, str) or not isinstance(file, str):
            raise ValueError("TypeScript modules require a qualified name and source file")
        path = PurePosixPath(file)
        source = next((PurePosixPath(root) for root in roots if path.is_relative_to(root)), None)
        if source is None:
            raise ValueError(f"TypeScript source is outside configured roots: {file}")
        relative = path.relative_to(source)
        group = source / relative.parts[0] if relative.parts else source
        groups.setdefault(group, []).append(name)
        if group != path:
            directories.add(group)
    labels: dict[str, str] = {}
    components: list[ContractComponent] = []
    for group, names in sorted(groups.items()):
        selector = module_identity(namespace, group.as_posix())
        # Mermaid identifiers are lowercase; preserve case and path distinctions by escaping.
        label = re.sub(
            "[A-Z]",
            lambda match: f"_x{ord(match[0]):x}_",
            selector.removeprefix(namespace + ".").replace(".", "_x2f_"),
        )
        labels.update((name, label) for name in names)
        directory = group in directories
        components.append(
            ContractComponent(
                f"COMP-{identifier(label)}",
                label,
                ComponentRole.COMPONENT,
                (selector,) if directory else (),
                (),
                (),
                (DOCUMENT_PATH,),
                namespace=selector if directory else None,
                exact_modules=None if directory else tuple(sorted(names)),
            )
        )
    return labels, tuple(components)


def draft_contract(
    observation: Observation,
    namespace: str,
    *,
    roots: tuple[str, ...] = (),
    language: Language = Language.PYTHON,
) -> tuple[ArchitectureContract, frozenset[tuple[str, str]], tuple[StructureMetric, ...]]:
    """Propose components, structural rules and each draft's measured size.

    AD-15: `init` never decides whether a component pair may depend on another, observed or
    not. `run_init` derives those open decisions separately, from these drafted components.
    AD-38: sizes come from `scope_metrics`, the same aggregation `structure_metrics` uses for
    a declared component, applied here to the draft grouping before any component exists.
    """
    if language == Language.TYPESCRIPT:
        module_labels, draft_components = _typescript_components(observation, namespace, roots)
    else:
        depth = len(namespace.split("."))
        module_labels = {
            name: name.split(".")[depth]
            for record in observation.records("modules") or ()
            if isinstance((name := record.data.get("qualified_name")), str)
            and name != namespace
            and in_scope(name, namespace)
        }
        labels = tuple(sorted(set(module_labels.values())))
        draft_components = tuple(
            ContractComponent(
                f"COMP-{identifier(label)}",
                label,
                ComponentRole.COMPONENT,
                (f"{namespace}.{label}",),
                (),
                (),
                (DOCUMENT_PATH,),
            )
            for label in labels
        )
    labels = tuple(component.label for component in draft_components)
    scaffold = ArchitectureContract(ContractVersion.V2_1, draft_components, ())
    edges = observed_component_edges(scaffold, observation)
    sizes = scope_metrics(observation, StructureLevel.COMPONENT, module_labels)
    public = _drafted_public(observation, scaffold)
    # A drafted public list is the agent's interface decision, marked the way its rules are
    # (AD-50), so `agent_decisions` counts it and the architect sees what is still owed.
    components = tuple(
        replace(component, public=entries, decided_by=DecisionMaker.AGENT)
        if (entries := public.get(component.label)) is not None
        else component
        for component in draft_components
    )
    rules: list[ArchitectureRule] = [
        CompleteAssignmentRule(
            "ASSIGNMENT-COMPLETE",
            ArchitectureRuleKind.COMPLETE_ASSIGNMENT,
            namespace,
            "TODO: explain why every module needs exactly one owning component.",
            (DOCUMENT_PATH,),
            DecisionMaker.AGENT,
        )
    ]
    if not _has_cycle(labels, edges):
        rules.append(
            NoComponentCyclesRule(
                "COMPONENT-NO-CYCLES",
                ArchitectureRuleKind.NO_COMPONENT_CYCLES,
                "TODO: explain why components must stay acyclic.",
                (DOCUMENT_PATH,),
                DecisionMaker.AGENT,
            )
        )
    if public:
        rules.append(
            InterfaceBoundaryRule(
                "INTERFACE-BOUNDARY",
                ArchitectureRuleKind.INTERFACE_BOUNDARY,
                "TODO: explain why cross-component imports must use declared interfaces.",
                (DOCUMENT_PATH,),
                DecisionMaker.AGENT,
            )
        )
    return ArchitectureContract(ContractVersion.V2_1, components, tuple(rules)), edges, sizes


def architecture_document(
    namespace: str,
    contract: ArchitectureContract,
    edges: frozenset[tuple[str, str]],
    sizes: tuple[StructureMetric, ...],
    *,
    namespace_file: str | None = None,
) -> str:
    """Write the provenance page whose marked graph validate compares with observed imports.

    AD-38: the Modules and Inner edges columns name each draft's size, so the architect sees
    where a per-child draft hides a large sub-package before deciding whether to consolidate.

    No `<!-- archkeel-target-graph -->` marker is written here (AD-57): `init` drafts no
    dependency rule and no `requires` entry, so there is no permitted-edge set yet to draw -
    that decision is the architect's, and `init` proposes, it never decides (AD-15).
    """
    by_label = {metric.scope: metric for metric in sizes}
    exact_claims = any(component.exact_modules for component in contract.components)
    rows = "\n".join(
        f"| `{component.label}` | `{_ownership_label(component)}` "
        f"| {by_label[component.label].modules} "
        f"| {by_label[component.label].inner_edges} | TODO: describe the responsibility. |"
        for component in contract.components
    )
    return (
        f"# {namespace} architecture\n\n"
        "Generated by `archkeel init` from observed imports. Replace every TODO with the\n"
        "owner's intent, then run `archkeel validate`.\n\n"
        + (
            "| Component | Ownership selector | Modules | Inner edges | Responsibility |\n"
            if exact_claims
            else "| Component | Package | Modules | Inner edges | Responsibility |\n"
        )
        + "|---|---|---|---|---|\n"
        + f"{rows}\n\n"
        + (
            f"Review namespace module `{namespace}` (`{namespace_file}`). If it contains any\n"
            "statement, assign it to one existing component using "
            f'`exact_modules: ["{namespace}"]`.\n'
            "Only an AST-empty Python `__init__.py` is exempt from boundary ownership proof.\n\n"
            if namespace_file is not None
            else ""
        )
        + f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n{mermaid_edges(edges)}```\n"
    )


def _ownership_label(component: ContractComponent) -> str:
    if not component.exact_modules:
        return (component.packages or ("",))[0]
    packages = ", ".join(component.packages)
    exact = ", ".join(component.exact_modules)
    if packages and exact:
        return f"{packages}; exact: {exact}"
    return packages or exact


def _drafted_ownership(contract: ArchitectureContract) -> tuple[ComponentOwnership, ...]:
    return tuple(
        (item.label, item.packages, item.exact_modules or ()) for item in contract.components
    )


def _draft_sizes(sizes: tuple[StructureMetric, ...]) -> tuple[DraftedComponentSize, ...]:
    return tuple(DraftedComponentSize(item.scope, item.modules, item.inner_edges) for item in sizes)


def first_look(
    observation: Observation,
    draft_sizes: tuple[DraftedComponentSize, ...],
    unknown_positions: int,
) -> FirstLook:
    """AD-266: count what the observation already holds; no threshold decides any line.

    Fan-in is the count the `modules` records carry; the report's hub rule adds a threshold
    that would print "none" for a project whose most-imported module has three importers.
    """
    cycles = [
        record
        for record in observation.records("cycles") or ()
        if parse_graph_topology_level(record.data.get("level")) is GraphTopologyLevel.MODULE
    ]
    importers = sorted(
        (
            (int_value(record.data.get("fan_in")), text_value(record.data.get("qualified_name")))
            for record in observation.records("modules") or ()
        ),
        key=lambda item: (-item[0], item[1]),
    )
    most_importers, most_imported = importers[0] if importers else (0, "")
    largest_modules = max((item.modules for item in draft_sizes), default=0)
    leaders = sorted(item.label for item in draft_sizes if item.modules == largest_modules)
    coverage = observation.coverage
    return FirstLook(
        files_parsed=coverage.files_parsed,
        files_discovered=coverage.files_discovered,
        call_resolution_percent=coverage.call_resolution_percent,
        module_cycles=len(cycles),
        largest_module_cycle=max((len(record.subjects) for record in cycles), default=0),
        most_imported_module=most_imported if most_importers else None,
        most_importers=most_importers,
        largest_component=leaders[0] if leaders else None,
        largest_component_ties=len(leaders),
        largest_component_modules=largest_modules,
        unknown_positions=unknown_positions,
    )


def _observed_ports(
    observation: Observation, contract: ArchitectureContract
) -> dict[tuple[str, str], tuple[str, ...]]:
    """The `through` ports each observed ordered crossing needs: the name imported, else the module.

    A module port matches the module and its descendants, so a whole-module import needs the
    module and a named import needs `module:name`, the narrowest port the grammar allows.
    """
    ports: dict[tuple[str, str], tuple[str, ...]] = {}
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is None or target is None or source.label == target.label:
            continue
        symbol = record.data.get("symbol")
        named = isinstance(symbol, str) and symbol != "*"
        pair = (source.label, target.label)
        port = f"{target_module}:{symbol}" if named else target_module
        ports[pair] = tuple(sorted({*ports.get(pair, ()), port}))
    return ports


def _adopt_contract(
    contract: ArchitectureContract, observation: Observation
) -> ArchitectureContract:
    """AD-266: record every observed crossing as an agent `requires` entry, then forbid the rest.

    An observed crossing is recorded as observed, not reviewed. `complete_requires` makes every
    other ordered pair forbidden; without it the pairs stay open and `validate` exits 2. The
    drafted structural rules carry TODO rationales that validate rejects, so they take the same
    adopted sentence.
    """
    ports = _observed_ports(observation, contract)
    sources = {source for source, _ in ports}
    components = tuple(
        replace(
            component,
            requires=tuple(
                RequiredComponent(target, ADOPTED_RATIONALE, through, DecisionMaker.AGENT)
                for (source, target), through in sorted(ports.items())
                if source == component.label
            ),
        )
        if component.label in sources
        else component
        for component in contract.components
    )
    rules = (
        *(replace(rule, rationale=ADOPTED_RATIONALE) for rule in contract.rules),
        CompleteRequiresRule(
            _REQUIRES_COMPLETE_ID,
            ArchitectureRuleKind.COMPLETE_REQUIRES,
            ADOPTED_RATIONALE,
            (DOCUMENT_PATH,),
            DecisionMaker.AGENT,
        ),
    )
    return replace(contract, components=components, rules=rules)


def run_init(
    root: Path,
    *,
    source: str | tuple[str, ...] | None,
    namespace: str | None,
    force: bool,
    full: bool = False,
    adopt_baseline: str | None = None,
    analyzer: Analyzer,
    language: Language = Language.PYTHON,
    tsconfig: str | None = None,
    collector_argv: tuple[str, ...] | None = None,
    collector_output_limit_bytes: int | None = None,
    collector_timeout_seconds: int | None = None,
) -> tuple[RunResult, FilesToWrite]:
    """Observe the repository and return the onboarding files without writing them."""
    if language == Language.TYPESCRIPT and (not source or not namespace or not tsconfig):
        raise ValueError("TypeScript init requires --source, --namespace and --tsconfig")
    if language != Language.TYPESCRIPT and tsconfig is not None:
        raise ValueError("--tsconfig requires --language typescript")
    if source is None or namespace is None:
        if source is not None or namespace is not None:
            raise ValueError("pass both --source and --namespace, or neither")
        if language == Language.DART:
            # Detection reads Python package markers; a Dart package names its own root.
            raise DiagnosticError(
                Diagnostic(
                    _DiagnosticKind.SCOPE_EMPTY,
                    str(root),
                    "A Dart package's source directory and name are not detected yet.",
                    "Pass --source lib and --namespace <pubspec name> to archkeel init.",
                )
            )
        source, namespace = detect_source(root)
    # AD-266: an adoption also replaces the baseline it writes, so that file is guarded too.
    guarded = (
        CONFIG_PATH,
        CONTRACT_PATH,
        DOCUMENT_PATH,
        GUIDE_PATH,
        *((adopt_baseline,) if adopt_baseline is not None else ()),
    )
    existing = [path for path in guarded if (root / path).exists()]
    if existing and not force:
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.EXISTING_FILES,
                ", ".join(existing),
                "Onboarding would replace files that already exist.",
                "Rerun archkeel init with --force to replace them.",
            )
        )
    roots = (source,) if isinstance(source, str) else source
    config = ScanConfig(
        roots,
        namespace,
        CONTRACT_PATH,
        "",
        language,
        tsconfig,
        collector_argv,
        collector_output_limit_bytes=collector_output_limit_bytes,
        collector_timeout_seconds=collector_timeout_seconds,
    )
    with TemporaryDirectory(prefix="archkeel-init-") as temporary:
        scaffold = Path(temporary)
        (scaffold / CONTRACT_PATH).write_bytes(
            contract_bytes(ArchitectureContract(ContractVersion.V2_1, (), ()))
        )
        try:
            observed = observe_repository(root, config, analyzer, contract_root=scaffold)
        except SnapshotError as error:
            raise DiagnosticError(
                Diagnostic(
                    _DiagnosticKind.PARSE_ERROR,
                    str(root),
                    f"Initialization requires a resolvable Git HEAD: {error}",
                    "Use an existing Git repository with a resolvable HEAD; for a new repository, "
                    "run git init and create a commit, then retry archkeel init.",
                )
            ) from error
    if observed.diagnostics or observed.observation is None:
        return RunResult(
            _Command.INIT, 2, diagnostics=observed.diagnostics, coverage=observed.coverage
        ), FilesToWrite()
    contract, edges, sizes = draft_contract(
        observed.observation, namespace, roots=roots, language=language
    )
    namespace_file = next(
        (
            file
            for record in observed.observation.records("modules") or ()
            if language == Language.PYTHON
            and record.data.get("qualified_name") == namespace
            and isinstance((file := record.data.get("file")), str)
        ),
        None,
    )
    # Absent means Python, so a Python draft keeps the exact config bytes it always had.
    language_line = "" if language == Language.PYTHON else f"language = {json.dumps(language)}\n"
    tsconfig_line = "" if tsconfig is None else f"tsconfig = {json.dumps(tsconfig)}\n"
    collector_line = (
        "" if collector_argv is None else f"collector_argv = {json.dumps(collector_argv)}\n"
    )
    output_limit_line = (
        ""
        if collector_output_limit_bytes is None
        else f"collector_output_limit_bytes = {collector_output_limit_bytes}\n"
    )
    timeout_line = (
        ""
        if collector_timeout_seconds is None
        else f"collector_timeout_seconds = {collector_timeout_seconds}\n"
    )
    written = (
        _adopt_contract(contract, observed.observation) if adopt_baseline is not None else contract
    )
    files = {
        CONFIG_PATH: (
            f"[scan]\nroots = {json.dumps(roots)}\nnamespace = {json.dumps(namespace)}\n"
            f"contract = {json.dumps(CONTRACT_PATH)}\n"
            f"{language_line}{tsconfig_line}{collector_line}{output_limit_line}{timeout_line}"
        ).encode(),
        CONTRACT_PATH: contract_bytes(written),
        DOCUMENT_PATH: architecture_document(
            namespace, contract, edges, sizes, namespace_file=namespace_file
        ).encode(),
    }
    # AD-15: init has no dependency rule, so count every undecided pair while showing
    # only observed crossings unless the caller explicitly asks for the full list.
    ownership = _drafted_ownership(contract)
    measurements = measure_python_ratchets(observed.observation)
    drafted = _draft_sizes(sizes)
    if adopt_baseline is not None:
        # Every observed crossing is decided by the adoption and every other pair is forbidden.
        decisions: tuple[OpenDecision, ...] = ()
        decision_count = 0
        decisions_complete = True
    elif full:
        decisions = open_decisions(observed.observation, ownership)
        decision_count = len(decisions)
        decisions_complete = True
    else:
        decisions, decision_count = open_decision_summary(observed.observation, ownership)
        decisions_complete = len(decisions) == decision_count
    result = RunResult(
        _Command.INIT,
        0,
        observation_complete=_AssessmentStatus.PASS,
        expectation_fulfilled=_ExpectationOutcome.NOT_APPLICABLE,
        coverage=observed.coverage,
        python_version=observed.observation.python_version,
        artifact=CONTRACT_PATH,
        open_decisions=decisions,
        open_decision_count=decision_count,
        open_decisions_complete=decisions_complete,
        draft_sizes=drafted,
        measurements=measurements,
        first_look=first_look(
            observed.observation, drafted, measurements.scalars.unknown_positions
        ),
    )
    return result, FilesToWrite(tuple(files.items()))
