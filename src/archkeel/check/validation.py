# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture-contract quality against typed observations."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

from archkeel.ir.baseline import KnownViolation, compare_violations, observed_violations
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    amendment_bytes,
    baseline_bytes,
    contract_digest,
    contract_provenance_paths,
    decode_json,
    parse_amendment,
    parse_baseline,
    parse_contract,
)
from archkeel.ir.decisions import (
    agent_decisions,
    open_decisions,
    review_claims,
    violation_counts,
)
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    BoundaryTypesRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ContractComponent,
    ContractDeclarations,
    Diagnostic,
    DiagnosticCode,
    ExternalDependencyScopeRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    Observation,
    RecordData,
    RunResult,
    SiblingIsolationRule,
    SymbolPlacementRule,
    contract_relative_path,
    in_scope,
    text_value,
)
from archkeel.ir.widening import Amendment, baseline_widenings, contract_widenings, verify_amendment

from .git import GitError, read_blob
from .ports import Analyzer, ScanConfig
from .report import observe_repository
from .run import inspect_observation

COMPONENT_GRAPH_MARKER = "<!-- archkeel-component-graph -->"
# AD-57: a second, independent marker for the graph the contract permits, beside the one
# above for the graph the code observes. A page may carry either, both or neither.
TARGET_GRAPH_MARKER = "<!-- archkeel-target-graph -->"
# One noun and two source phrases per marker - the claim reads "differs from X", the remedy
# "regenerate ... from Y" - so graph.count/graph.drift read the same for both markers and a
# diagnostic's subject always names which one it is about. The observed marker keeps AD-46's
# own two phrasings; the target marker, new here, uses one for both.
_GRAPH_MARKERS: tuple[tuple[str, str, str, str], ...] = (
    (COMPONENT_GRAPH_MARKER, "component", "observed imports", "the observed component edges"),
    (
        TARGET_GRAPH_MARKER,
        "target",
        "the edges the contract permits",
        "the edges the contract permits",
    ),
)
_REPEATED_RATIONALE = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)
# A requires entry states a permission, so the prohibition-shaped pattern above can never
# fire on it; its filler equivalent reads "cli depends on render." (AD-32).
_REPEATED_REQUIRES = re.compile(
    r"(?:The )?\S+ (?:depends on|requires|uses|needs) \S+\.", re.IGNORECASE
)
_PLACEHOLDER_RATIONALE = re.compile(r"(?:todo|tbd|placeholder)(?:\b|:)", re.IGNORECASE)
_GRAPH_EDGE = re.compile(r"\s*([a-z_][a-z0-9_]*)\s*-->\s*([a-z_][a-z0-9_]*)\s*")
_MERMAID_FENCE = "```mermaid\n"
_GRAPH_DECLARATION = re.compile(r"\s*(?:graph|flowchart)\b.*")
_GRAPH_COMMENT = re.compile(r"\s*%%.*")


def _diagnostic(
    code: DiagnosticCode, pointer: str, subject: str, claim: str, remedy: str
) -> Diagnostic:
    return Diagnostic("contract_invalid", subject, claim, remedy, pointer, code)


def _package_owners(contract: ArchitectureContract) -> dict[str, str]:
    return {
        package: component.label
        for component in contract.components
        for package in component.packages
    }


def observed_component_edges(
    contract: ArchitectureContract, observation: Observation
) -> frozenset[tuple[str, str]]:
    """Project module imports onto declared component labels."""
    edges: set[tuple[str, str]] = set()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is not None and target is not None and source != target:
            edges.add((source.label, target.label))
    return frozenset(edges)


_DecisionRule = TypeVar("_DecisionRule", ForbiddenDependencyRule, AllowedDependencyRule)


def _decided_pairs(
    contract: ArchitectureContract, rule_type: type[_DecisionRule]
) -> list[tuple[str, str]]:
    """Return the component pairs one rule type decides, keyed by exact package ownership."""
    owners = _package_owners(contract)
    return [
        (owners[rule.source], owners[rule.target])
        for rule in contract.rules
        if isinstance(rule, rule_type) and rule.source in owners and rule.target in owners
    ]


def target_component_edges(contract: ArchitectureContract) -> frozenset[tuple[str, str]]:
    """The component pairs the contract permits, for `<!-- archkeel-target-graph -->` (AD-57).

    A contract states a pair may exist in one of two ways: a `requires` entry, AD-32's
    intentional grant, absence of which `complete_requires` forbids; or an `allowed_dependency`
    rule, AD-15's closed-world grant, where every pair is decided one way or the other. Both
    name a permitted pair, so the target draws their union - one rule, not a branch on which
    system a contract adopted. In practice a contract writes one or the other: a `requires`-based
    contract carries no coarse `allowed_dependency` pair and a pair-decided one carries no
    `requires` entry, so the union reduces to whichever the contract actually wrote, and a
    contract that has adopted neither permits nothing yet - the target graph is then empty.
    """
    requires_edges = {
        (component.label, entry.component)
        for component in contract.components
        for entry in component.requires or ()
    }
    return frozenset(requires_edges) | frozenset(_decided_pairs(contract, AllowedDependencyRule))


def _pair_diagnostics(
    code: DiagnosticCode, pairs: Iterable[tuple[str, str]], claim: str, remedy: str
) -> list[Diagnostic]:
    return [
        _diagnostic(code, "/rules", f"{source} -> {target}", claim, remedy)
        for source, target in pairs
    ]


def _open_decision_diagnostics(observation: Observation) -> list[Diagnostic]:
    return [
        _diagnostic(
            "decision.open",
            "/rules",
            f"{decision.source} -> {decision.target}",
            f"{decision.import_sites} import site(s) use this pair, and no rule decides it."
            if decision.observed
            else "No import uses this pair today, and no rule decides it.",
            "Allow or forbid the pair: add an allowed_dependency or forbidden_dependency rule "
            "with a rationale.",
        )
        for decision in open_decisions(observation)
    ]


def closed_world_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require each ordered component pair to be a decision, and each decision unique (AD-15)."""
    observed = observed_component_edges(contract, observation)
    forbidden_items = _decided_pairs(contract, ForbiddenDependencyRule)
    allowed_items = _decided_pairs(contract, AllowedDependencyRule)
    forbidden = set(forbidden_items)
    allowed = set(allowed_items)
    diagnostics = _open_decision_diagnostics(observation)
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.observed_forbidden",
            sorted(observed & forbidden),
            "An observed component dependency is also forbidden.",
            "Remove the dependency or correct the forbidden_dependency rule.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(forbidden_items).items() if count > 1),
            "The component pair has duplicate forbidden_dependency rules.",
            "Keep one forbidden_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(allowed_items).items() if count > 1),
            "The component pair has duplicate allowed_dependency rules.",
            "Keep one allowed_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "decision.conflict",
            sorted(allowed & forbidden),
            "The component pair has both an allowed_dependency and a forbidden_dependency rule.",
            "Keep only one decision for this ordered component pair.",
        )
    )
    return tuple(diagnostics)


def _scanned_modules(observation: Observation) -> frozenset[str]:
    """Every module the scan actually read, by qualified name (shared with reference checks)."""
    return frozenset(
        module_name
        for record in observation.records("modules") or ()
        if isinstance((module_name := record.data.get("qualified_name")), str)
    )


def _entry_module(entry: str) -> str:
    return entry.partition(":")[0]


def _entry_used(entry: str, records: list[RecordData]) -> bool:
    """Match one public entry's usage the way `_interface_allows` walks reexport_chain.

    Deliberately looser than the analyzer's runtime check: no `__all__` gate and no
    underscore rejection, since a public entry naming a private or unexported name is
    a rule violation already reported elsewhere, not an unused-entry drift signal.
    """
    module, colon, name = entry.partition(":")
    for data in records:
        chain = data.get("reexport_chain")
        chain_items = chain if isinstance(chain, tuple) else ()
        if colon:
            if any(item == f"{module}.{name}" for item in chain_items if isinstance(item, str)):
                return True
            continue
        if data.get("target_module") == module:
            return True
        for item in chain_items:
            if isinstance(item, str) and item.rpartition(".")[0] == module:
                return True
    return False


def _imports_by_target(
    contract: ArchitectureContract, observation: Observation
) -> dict[str, list[RecordData]]:
    imports_by_target: dict[str, list[RecordData]] = {}
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is None or target is None or source == target:
            continue
        imports_by_target.setdefault(target.label, []).append(record.data)
    return imports_by_target


def _public_entry_diagnostics(
    index: int, component: ContractComponent, records: list[RecordData], modules: frozenset[str]
) -> list[Diagnostic]:
    """Split an unused `public` entry by whether its module was ever scanned (AD-56).

    A module the scan never saw does not exist yet, `interface.missing`, whether that is a typo
    or a facade a refactoring has not built; one the scan saw but nothing imports is
    `interface.unused`, same as before. A `pkg.module:Name` entry is judged by its module alone:
    `symbols` records only classes and functions, so absence from it would misreport a constant
    or type alias as missing. A used entry is checked against neither, exactly as before.
    """
    diagnostics = []
    for item, entry in enumerate(component.public or ()):
        if _entry_used(entry, records):
            continue
        if _entry_module(entry) not in modules:
            diagnostics.append(
                _diagnostic(
                    "interface.missing",
                    f"/components/{index}/public/{item}",
                    entry,
                    "The public entry's module has not been scanned; it does not exist yet.",
                    "Build the module, correct a typo, or move the entry to planned "
                    "until it exists.",
                )
            )
        else:
            diagnostics.append(
                _diagnostic(
                    "interface.unused",
                    f"/components/{index}/public/{item}",
                    entry,
                    "No cross-component import reaches this public entry.",
                    "Remove the entry or confirm another component should use it.",
                )
            )
    return diagnostics


def _planned_entry_diagnostics(
    index: int, component: ContractComponent, modules: frozenset[str]
) -> list[Diagnostic]:
    """Flag a `planned` entry whose module the scan now sees: the marker is stale (AD-56).

    A planned module the scan never saw is target work, not a finding. Needs no declared
    `public` of its own: an architect may name a facade before the component has any live
    interface to pair it with.
    """
    return [
        _diagnostic(
            "interface.planned_built",
            f"/components/{index}/planned/{item}",
            entry,
            "The planned entry's module has been scanned; it is no longer planned.",
            "Move the entry to public and drop it from planned.",
        )
        for item, entry in enumerate(component.planned or ())
        if _entry_module(entry) in modules
    ]


def interface_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require a declared interface for inbound imports and usage for declared entries."""
    if not any(isinstance(rule, InterfaceBoundaryRule) for rule in contract.rules):
        return ()
    imports_by_target = _imports_by_target(contract, observation)
    modules = _scanned_modules(observation)
    diagnostics = []
    for index, component in enumerate(contract.components):
        records = imports_by_target.get(component.label, [])
        if component.public is None:
            if records:
                diagnostics.append(
                    _diagnostic(
                        "interface.undeclared",
                        f"/components/{index}",
                        component.label,
                        "The component receives cross-component imports but declares "
                        "no public interface.",
                        "Declare the used modules or names in public.",
                    )
                )
        else:
            diagnostics.extend(_public_entry_diagnostics(index, component, records, modules))
        diagnostics.extend(_planned_entry_diagnostics(index, component, modules))
    return tuple(diagnostics)


def rationale_diagnostics(contract: ArchitectureContract) -> tuple[Diagnostic, ...]:
    """Reject placeholder rationales and rationales that only repeat the rule."""
    diagnostics = []
    for index, rule in enumerate(contract.rules):
        rationale = rule.rationale.strip()
        code: DiagnosticCode
        if _REPEATED_RATIONALE.fullmatch(rationale):
            code = "rationale.repeated"
            claim = "The rationale repeats the forbidden dependency without explaining why."
        elif _PLACEHOLDER_RATIONALE.match(rationale):
            code = "rationale.placeholder"
            claim = "The rationale is a placeholder."
        else:
            continue
        diagnostics.append(
            _diagnostic(
                code,
                f"/rules/{index}/rationale",
                rule.id,
                claim,
                "Explain the architectural reason for this dependency boundary.",
            )
        )
    for index, component in enumerate(contract.components):
        for position, entry in enumerate(component.requires or ()):
            rationale = entry.rationale.strip()
            entry_code: DiagnosticCode
            if _REPEATED_REQUIRES.fullmatch(rationale):
                entry_code = "rationale.repeated"
                claim = "The rationale repeats the requires entry without explaining why."
            elif _PLACEHOLDER_RATIONALE.match(rationale):
                entry_code = "rationale.placeholder"
                claim = "The rationale is a placeholder."
            else:
                continue
            diagnostics.append(
                _diagnostic(
                    entry_code,
                    f"/components/{index}/requires/{position}/rationale",
                    f"{component.label} -> {entry.component}",
                    claim,
                    "Explain the architectural reason for this dependency boundary.",
                )
            )
    return tuple(diagnostics)


def _marked_bodies(content: str, marker: str) -> list[tuple[int, int]]:
    """Start and end of each Mermaid body that follows `marker`, before the next one.

    AD-57: the marker is a parameter, not a hardcoded constant, so `graph_diagnostics` and
    `rewrite_component_graph` read `COMPONENT_GRAPH_MARKER` and `TARGET_GRAPH_MARKER` through
    the one reader and can never disagree about where either marker's block starts and ends.
    """
    spans: list[tuple[int, int]] = []
    position = content.find(marker)
    while position != -1:
        following = content.find(marker, position + len(marker))
        limit = len(content) if following == -1 else following
        fence = content.find(_MERMAID_FENCE, position, limit)
        if fence != -1:
            start = fence + len(_MERMAID_FENCE)
            end = content.find("```", start, limit)
            spans.append((start, limit if end == -1 else end))
        position = following
    return spans


def _unwritable_line(body: str) -> str | None:
    """The first line of a marked block that is not a declaration, a `%%` comment or an edge.

    AD-46: a subgraph, a labeled edge or a style can depend on where an edge sits, so a rewrite
    that reorders the edges could change what the graph says; such a block is left to a human.
    """
    return next(
        (
            line.strip()
            for line in body.splitlines()
            if line.strip()
            and not _GRAPH_EDGE.fullmatch(line)
            and not _GRAPH_DECLARATION.fullmatch(line)
            and not _GRAPH_COMMENT.fullmatch(line)
        ),
        None,
    )


def mermaid_edges(edges: frozenset[tuple[str, str]]) -> str:
    """One sorted Mermaid line per component edge: what `init` and `--write-graph` write."""
    return "".join(f"    {source} --> {target}\n" for source, target in sorted(edges))


def rewrite_component_graph(
    documents: tuple[tuple[str, str], ...],
    observed_edges: frozenset[tuple[str, str]],
    target_edges: frozenset[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Every marked graph's document with its edges replaced; empty if nothing is written.

    AD-46/AD-57: the two markers are rewritten independently, each only when the documents
    carry exactly one block for it; a marker absent everywhere is left alone, the way a page
    may carry either, both or neither, and one repeated is as ambiguous to rewrite as before -
    `graph.count` says so and this writes nothing for it either. The declaration and `%%`
    comments stay ahead of the edges, so a page's own `flowchart LR` survives, and a block
    without a declaration gets `init`'s; a block with any other line is not rewritten at all.
    Both markers may sit in the same document, which then comes back once with both edits.
    """
    edited: dict[str, str] = {}
    for marker, edges in (
        (COMPONENT_GRAPH_MARKER, observed_edges),
        (TARGET_GRAPH_MARKER, target_edges),
    ):
        current = {path: edited.get(path, content) for path, content in documents}
        blocks = [
            (path, span)
            for path, content in current.items()
            for span in _marked_bodies(content, marker)
        ]
        if len(blocks) != 1:
            continue
        path, (start, end) = blocks[0]
        content = current[path]
        body = content[start:end]
        if _unwritable_line(body) is not None:
            continue
        kept = [
            line for line in body.splitlines() if line.strip() and not _GRAPH_EDGE.fullmatch(line)
        ]
        if not any(_GRAPH_DECLARATION.fullmatch(line) for line in kept):
            kept.insert(0, "graph TD")
        written = (
            content[:start]
            + "".join(f"{line}\n" for line in kept)
            + mermaid_edges(edges)
            + content[end:]
        )
        if written != content:
            edited[path] = written
    return tuple(edited.items())


def _marker_diagnostics(
    marker: str,
    noun: str,
    claim_source: str,
    remedy_source: str,
    edges: frozenset[tuple[str, str]],
    documents: tuple[tuple[str, str], ...],
    *,
    required: bool,
) -> tuple[Diagnostic, ...]:
    """One marker's graph.count/graph.drift findings; the subject always names the marker.

    AD-57: `required` is false for the target marker, so a page that draws none is silent -
    the target is optional, the way a page may carry either, both or neither - while the
    observed marker keeps AD-12's original rule, always exactly one.
    """
    graphs = [
        (path, content[start:end])
        for path, content in documents
        for start, end in _marked_bodies(content, marker)
    ]
    if not graphs and not required:
        return ()
    if len(graphs) != 1:
        return (
            _diagnostic(
                "graph.count",
                "/components",
                f"architecture {noun} graph",
                f"Expected one marked Mermaid {noun} graph, found {len(graphs)}.",
                f"Keep one graph after the archkeel-{noun}-graph marker in contract provenance.",
            ),
        )
    path, body = graphs[0]
    declared = frozenset(
        (match.group(1), match.group(2))
        for line in body.splitlines()
        if (match := _GRAPH_EDGE.fullmatch(line))
    )
    if declared == edges:
        return ()
    missing = ", ".join(f"{a}->{b}" for a, b in sorted(edges - declared)) or "none"
    extra = ", ".join(f"{a}->{b}" for a, b in sorted(declared - edges)) or "none"
    unwritable = _unwritable_line(body)
    return (
        _diagnostic(
            "graph.drift",
            "/components",
            f"{path} ({noun} graph)",
            f"The marked {noun} graph differs from {claim_source}; "
            f"missing: {missing}; extra: {extra}.",
            "Run archkeel validate --write-graph to regenerate the marked Mermaid graph "
            f"from {remedy_source}."
            if unwritable is None
            else f"Edit the marked graph's edges by hand: it holds `{unwritable}`, structure "
            "archkeel validate --write-graph does not rewrite.",
        ),
    )


def graph_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
) -> tuple[Diagnostic, ...]:
    """Require the observed marker always, and the target marker whenever a page draws one.

    AD-57: `<!-- archkeel-target-graph -->` is compared against `target_component_edges`, the
    pairs the contract permits, beside `<!-- archkeel-component-graph -->`'s unchanged
    comparison against observed imports; the two are independent, so one may drift while the
    other passes, and each diagnostic's subject names its own marker.
    """
    observed_marker, observed_noun, observed_claim, observed_remedy = _GRAPH_MARKERS[0]
    target_marker, target_noun, target_claim, target_remedy = _GRAPH_MARKERS[1]
    return (
        *_marker_diagnostics(
            observed_marker,
            observed_noun,
            observed_claim,
            observed_remedy,
            observed_component_edges(contract, observation),
            documents,
            required=True,
        ),
        *_marker_diagnostics(
            target_marker,
            target_noun,
            target_claim,
            target_remedy,
            target_component_edges(contract),
            documents,
            required=False,
        ),
    )


def _sorted(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.pointer or "", item.subject, item.unknown_claim, item.remedy),
        )
    )


def _provenance(contract: ArchitectureContract) -> tuple[tuple[str, tuple[str, ...]], ...]:
    declarations = contract.declarations or ContractDeclarations()
    return (
        *(
            (f"/components/{index}/provenance", item.provenance)
            for index, item in enumerate(contract.components)
        ),
        *(
            (f"/rules/{index}/provenance", item.provenance)
            for index, item in enumerate(contract.rules)
        ),
        *(
            (f"/declarations/capabilities/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.capabilities)
        ),
        *(
            (f"/declarations/review_scopes/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.review_scopes)
        ),
        *(
            (f"/declarations/public_commands/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.public_commands)
        ),
        *(
            (f"/declarations/paths/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.paths)
        ),
        *(
            (f"/declarations/spot_owners/{index}/provenance", item.provenance)
            for index, item in enumerate(declarations.spot_owners)
        ),
        ("/declarations/public_api_provenance", declarations.public_api_provenance),
        ("/declarations/context_roots_provenance", declarations.context_roots_provenance),
    )


def _namespace_references(contract: ArchitectureContract) -> list[tuple[str, str]]:
    """Collect every contract-declared name that must resolve inside the scan namespace."""
    declarations = contract.declarations or ContractDeclarations()
    names: list[tuple[str, str]] = []
    for index, component in enumerate(contract.components):
        names.extend(
            (f"/components/{index}/packages/{item}", value)
            for item, value in enumerate(component.packages)
        )
        if component.public is not None:
            names.extend(
                (f"/components/{index}/public/{item}", value.split(":", 1)[0])
                for item, value in enumerate(component.public)
            )
        if component.planned is not None:
            names.extend(
                (f"/components/{index}/planned/{item}", value.split(":", 1)[0])
                for item, value in enumerate(component.planned)
            )
        names.extend(
            (f"/components/{index}/requires/{position}/through/{item}", value)
            for position, entry in enumerate(component.requires or ())
            for item, value in enumerate(entry.through)
        )
    for index, rule in enumerate(contract.rules):
        if isinstance(
            rule,
            ForbiddenDependencyRule
            | AllowedDependencyRule
            | ForbiddenConstructRule
            | CompleteAssignmentRule
            | CompleteExternalScopeRule
            | SymbolPlacementRule
            | BoundaryTypesRule,
        ):
            names.append((f"/rules/{index}/source", rule.source))
        if isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule):
            names.append((f"/rules/{index}/target", rule.target))
        if isinstance(rule, SiblingIsolationRule):
            names.extend(
                (f"/rules/{index}/members/{item}", value) for item, value in enumerate(rule.members)
            )
        if isinstance(
            rule,
            ForbiddenDependencyRule
            | ExternalDependencyScopeRule
            | SymbolPlacementRule
            | BoundaryTypesRule,
        ):
            names.extend(
                (f"/rules/{index}/allowed_sources/{item}", value)
                for item, value in enumerate(rule.allowed_sources)
            )
        if isinstance(rule, ExternalDependencyScopeRule | SymbolPlacementRule | BoundaryTypesRule):
            names.extend(
                (f"/rules/{index}/exact_sources/{item}", value)
                for item, value in enumerate(rule.exact_sources)
            )
    names.extend(
        (f"/declarations/public_api/{index}", value)
        for index, value in enumerate(declarations.public_api)
    )
    names.extend(
        (f"/declarations/context_roots/{index}", value)
        for index, value in enumerate(declarations.context_roots)
    )
    for index, scope in enumerate(declarations.review_scopes):
        names.extend(
            (f"/declarations/review_scopes/{index}/subjects/{item}", value)
            for item, value in enumerate(scope.subjects)
        )
    names.extend(
        (f"/declarations/spot_owners/{index}/owner", owner.owner)
        for index, owner in enumerate(declarations.spot_owners)
    )
    return names


def _entry_ownership_diagnostics(
    contract: ArchitectureContract, component: ContractComponent, index: int, field: str
) -> list[Diagnostic]:
    """Require each entry of one `public` or `planned` list to be owned, never underscore-named."""
    entries = component.public if field == "public" else component.planned
    diagnostics = []
    for item, entry in enumerate(entries or ()):
        module, _, name = entry.partition(":")
        pointer = f"/components/{index}/{field}/{item}"
        if contract.component_for(module) is not component:
            diagnostics.append(
                _diagnostic(
                    "reference.public_owner",
                    pointer,
                    entry,
                    "The public entry's module is not owned by this component.",
                    "Move the entry to its owning component or correct the module.",
                )
            )
        if name.startswith("_"):
            diagnostics.append(
                _diagnostic(
                    "reference.public_underscore",
                    pointer,
                    entry,
                    "Underscore names are never public.",
                    "Remove the entry or expose a non-underscore name.",
                )
            )
    return diagnostics


def _public_diagnostics(contract: ArchitectureContract) -> list[Diagnostic]:
    """Require each public and planned entry to be owned by its component, never underscore.

    A planned entry names something the component will own once built, so it is held to the
    same ownership and underscore checks as `public` (AD-56); reusing them here means a typo
    in a planned facade name is caught the same way a typo in a live one already is.
    """
    diagnostics = []
    for index, component in enumerate(contract.components):
        diagnostics.extend(_entry_ownership_diagnostics(contract, component, index, "public"))
        diagnostics.extend(_entry_ownership_diagnostics(contract, component, index, "planned"))
    return diagnostics


def repository_file(repository: Path, value: str) -> Path | None:
    """Resolve a contract-declared repository path, or None when it is unsafe or missing.

    Every path a contract names is attacker-adjacent input: it may escape the repository
    with `..`, with an absolute path or with a Windows separator. That judgement now lives in
    `ir` so the analyzer applies the same one without importing `check` (AD-34); what stays
    here is the filesystem check, which `ir` may not perform (AD-17).
    """
    relative = contract_relative_path(value)
    if relative is None:
        return None
    target = (repository / relative).resolve()
    if not target.is_relative_to(repository) or not target.is_file():
        return None
    return target


def reference_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate repository-dependent namespace, package and provenance references."""
    names = _namespace_references(contract)
    diagnostics = [
        _diagnostic(
            "reference.namespace",
            pointer,
            value,
            f"The reference is outside namespace {config.namespace}.",
            "Use a qualified name inside the configured namespace.",
        )
        for pointer, value in names
        if not in_scope(value, config.namespace)
    ]
    diagnostics.extend(_public_diagnostics(contract))
    repository = root.resolve()
    for pointer, values in _provenance(contract):
        for index, value in enumerate(values):
            if repository_file(repository, value) is None:
                diagnostics.append(
                    _diagnostic(
                        "reference.provenance",
                        f"{pointer}/{index}",
                        value,
                        "The provenance file is missing or outside the repository.",
                        "Reference an existing repository-relative evidence file.",
                    )
                )
    if observation is not None:
        modules = _scanned_modules(observation)
        for component_index, component in enumerate(contract.components):
            for package_index, package in enumerate(component.packages):
                if not any(in_scope(module, package) for module in modules):
                    diagnostics.append(
                        _diagnostic(
                            "reference.package_unscanned",
                            f"/components/{component_index}/packages/{package_index}",
                            package,
                            "The component package has no scanned Python module.",
                            "Correct the package or include it in scan.roots.",
                        )
                    )
    return _sorted(diagnostics)


def _inside_pointers(contract: ArchitectureContract, observation: Observation) -> dict[str, str]:
    """Pointer per record an inside declares: the component whose `inside` names it (AD-36).

    Such a rule is in no `rules` array of this contract, so a reader sent to `/rules/<n>` would
    be shown an unrelated decision; the component is where the level, and its contract, begin.
    """
    positions = {
        component.label: index
        for index, component in enumerate(contract.components)
        if component.inside is not None
    }
    return {
        record.id: f"/components/{positions[parent]}/inside"
        for record in observation.records("declarations") or ()
        if (parent := text_value(record.data.get("parent_id"))) in positions
    }


def observation_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
    *,
    report_violations: bool = True,
) -> tuple[Diagnostic, ...]:
    """Validate rules, closed-world coverage and architecture documentation.

    AD-52: a run carrying a baseline answers the violations there instead, so it asks for no
    `rule.violated` diagnostic here; every other finding is unchanged and still exits 2.
    """
    rule_index = {rule.id: index for index, rule in enumerate(contract.rules)}
    inside_pointers = _inside_pointers(contract, observation)
    diagnostics = [
        *closed_world_diagnostics(contract, observation),
        *interface_diagnostics(contract, observation),
        *rationale_diagnostics(contract),
        *graph_diagnostics(contract, observation, documents),
    ]
    reported = (observation.records("violations") or ()) if report_violations else ()
    for record in reported:
        rule_id = record.rule_ids[0] if record.rule_ids else record.id
        index = rule_index.get(rule_id)
        diagnostics.append(
            _diagnostic(
                "rule.violated",
                f"/rules/{index}" if index is not None else inside_pointers.get(rule_id, ""),
                rule_id,
                f"The observed code violates the declared rule: {record.title}",
                "Change the code or amend the contract with owner approval.",
            )
        )
    return _sorted(diagnostics)


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


def _inside_public(inner: ArchitectureContract) -> frozenset[str]:
    """The inside's public surface: what its own components offer, taken together."""
    return frozenset(entry for item in inner.components for entry in (item.public or ()))


def _forbidden_targets(
    contract: ArchitectureContract, packages: tuple[str, ...]
) -> list[tuple[str, str]]:
    """Each rule id and target the level above forbids a component, by any of its packages.

    The id travels with the target because the diagnostic exists to point at a decision, and
    a reader cannot find the decision from the target alone.
    """
    return [
        (rule.id, rule.target)
        for rule in contract.rules
        if isinstance(rule, ForbiddenDependencyRule)
        and any(in_scope(rule.source, package) for package in packages)
    ]


def _denied_by_absence(
    contract: ArchitectureContract, label: str, required: frozenset[str], target: str
) -> str | None:
    """The `complete_requires` rule refusing an edge the component never asked for (AD-32).

    Absence decides only where such a rule is in force, and only for a target another
    component owns: a target inside the component itself is no component edge at all, and one
    no component owns belongs to the external scope rules instead. Without this, a level whose
    pairs are decided by absence - which is how this repository decides them - would let its
    inside grant anything, because there is no `forbidden_dependency` left to contradict.
    """
    rule = next((item for item in contract.rules if isinstance(item, CompleteRequiresRule)), None)
    if rule is None:
        return None
    owner = contract.component_for(target)
    if owner is None or owner.label == label or owner.label in required:
        return None
    return rule.id


def inside_diagnostics(root: Path, contract: ArchitectureContract) -> tuple[Diagnostic, ...]:
    """AD-20: hold a component and the contract describing its inside to each other.

    Two checks, and only two: the levels must agree on the component's public surface, and
    the inside must not grant itself what the level above denies the component. Grants are
    read from the inside's `allowed_dependency` rules; an `external_dependency_scope` there
    is not yet compared, which stays a blind spot.
    """
    repository = root.resolve()
    diagnostics: list[Diagnostic] = []
    for index, component in enumerate(contract.components):
        if component.inside is None:
            continue
        pointer = f"/components/{index}/inside"
        target = repository_file(repository, component.inside)
        if target is None:
            diagnostics.append(
                _diagnostic(
                    "contract.invalid",
                    pointer,
                    component.inside,
                    "The contract describing this inside is missing or outside the repository.",
                    "Reference an existing repository-relative contract, or drop `inside`.",
                )
            )
            continue
        try:
            inner = parse_contract(decode_json(target.read_bytes()))
        except (OSError, ValueError, ContractVersionError) as error:
            diagnostics.append(
                _diagnostic(
                    "contract.invalid",
                    pointer,
                    component.inside,
                    f"The contract describing this inside cannot be read: {error}",
                    "Repair the inside contract so `validate` accepts it on its own.",
                )
            )
            continue
        declared = frozenset(component.public or ())
        inside = _inside_public(inner)
        if declared != inside:
            diagnostics.append(
                _diagnostic(
                    "inside.public_mismatch",
                    pointer,
                    component.label,
                    f"The level above declares {sorted(declared)} public for this component "
                    f"while its inside declares {sorted(inside)}.",
                    "Declare one public surface and repeat it in both contracts.",
                )
            )
        denied = _forbidden_targets(contract, component.packages)
        required = frozenset(entry.component for entry in component.requires or ())
        for rule in inner.rules:
            if not isinstance(rule, AllowedDependencyRule):
                continue
            blocked = [rule_id for rule_id, value in denied if in_scope(rule.target, value)]
            absent = _denied_by_absence(contract, component.label, required, rule.target)
            if absent is not None:
                blocked.append(absent)
            if blocked:
                diagnostics.append(
                    _diagnostic(
                        "inside.forbidden_import",
                        pointer,
                        f"{component.label} -> {rule.target}",
                        f"The inside allows {rule.target}, which {', '.join(sorted(blocked))} "
                        f"forbids {component.label} at the level above.",
                        "Remove the grant inside, or decide the pair differently above.",
                    )
                )
    return _sorted(diagnostics)


def _repository_diagnostics(
    root: Path,
    config: ScanConfig,
    contract: ArchitectureContract,
    observation: Observation,
    write_graph: bool,
    report_violations: bool,
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
            contract, observation, documents, report_violations=report_violations
        ),
        *inside_diagnostics(root, contract),
    ], edits


def _observed_result(
    observation: Observation, diagnostics: list[Diagnostic], failures: tuple[str, ...] = ()
) -> RunResult:
    """The validate result once a complete observation has produced its diagnostics.

    AD-52: a baseline's own findings arrive as `failures` and exit 1, which keeps a
    diagnostic and exit 2 meaning what they always meant - nothing could be judged.
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
        declared = "FAIL"
    decisions = open_decisions(observation)
    counts = agent_decisions(observation)
    # AD-51: a rejected run is where the breakdown is read, so it carries it too.
    counted = violation_counts(observation)
    if diagnostics:
        return RunResult(
            "validate",
            2,
            diagnostics=_sorted(diagnostics),
            coverage=observation.coverage,
            python_version=observation.python_version,
            open_decisions=decisions,
            agent_decisions=counts,
            violations_by_rule=counted.by_rule,
            violations_by_component_pair=counted.by_component_pair,
        )
    return RunResult(
        "validate",
        1 if failures else 0,
        observation_complete="PASS",
        declared_rules=declared,
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
        python_version=observation.python_version,
        measurements=measurements,
        failures=failures,
        open_decisions=decisions,
        agent_decisions=counts,
        claims=review_claims(observation),
        violations_by_rule=counted.by_rule,
        violations_by_component_pair=counted.by_component_pair,
    )


def _baseline_invalid(path: Path, error: Exception) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "baseline.invalid",
                "",
                str(path),
                f"The known-violation baseline cannot be read: {error}",
                "Correct the baseline, or write it with archkeel validate --baseline "
                "<path> --write-baseline.",
            ),
        ),
    )


def _against_invalid(against: str, error: Exception) -> RunResult:
    return RunResult(
        "validate",
        2,
        diagnostics=(
            _diagnostic(
                "against.invalid",
                "",
                against,
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
    except (OSError, ValueError) as error:
        return invalid_result(config.contract, error)


def _observed_or_invalid(
    root: Path, config: ScanConfig, analyzer: Analyzer
) -> Observation | RunResult:
    """The complete observation, or the exit-2 result naming what analyzer evidence is missing."""
    observed = observe_repository(root, config, analyzer)
    observation = observed.observation
    if observed.diagnostics or observation is None:
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
class _AgainstContext:
    """Everything `--against` and `--amendment` resolve to, threaded through one run (AD-61)."""

    against: str | None
    contract: ArchitectureContract | None
    baseline: tuple[KnownViolation, ...]
    amendment: Path | None
    write_amendment: bool
    parsed_amendment: Amendment | None
    decided_by: str | None
    rationale: str | None


def _resolve_against_context(
    root: Path,
    config: ScanConfig,
    against: str | None,
    baseline: Path | None,
    amendment: Path | None,
    write_amendment: bool,
    decided_by: str | None,
    rationale: str | None,
) -> tuple[_AgainstContext, RunResult | None]:
    """The contract and baseline `--against` names, and `--amendment`'s record.

    A missing baseline blob at that revision is not an error: the revision itself is already
    known good once its contract parses, so a `GitError` reading the baseline path there means
    only that the file did not exist yet, read as no prior baseline entries.
    """
    empty = _AgainstContext(
        against, None, (), amendment, write_amendment, None, decided_by, rationale
    )
    if against is None:
        return empty, None
    try:
        against_contract = parse_contract(decode_json(read_blob(root, against, config.contract)))
    except (GitError, ValueError) as error:
        return empty, _against_invalid(against, error)
    against_baseline: tuple[KnownViolation, ...] = ()
    baseline_at = _baseline_at(root, baseline)
    if baseline_at is not None:
        try:
            against_baseline_bytes: bytes | None = read_blob(root, against, baseline_at)
        except GitError:
            against_baseline_bytes = None
        if against_baseline_bytes is not None:
            try:
                against_baseline = parse_baseline(decode_json(against_baseline_bytes))
            except ValueError as error:
                return empty, _against_invalid(against, error)
    parsed_amendment, amendment_error = _resolve_amendment(amendment, write_amendment)
    context = _AgainstContext(
        against,
        against_contract,
        against_baseline,
        amendment,
        write_amendment,
        parsed_amendment,
        decided_by,
        rationale,
    )
    return context, amendment_error


def _resolve_amendment(
    amendment: Path | None, write_amendment: bool
) -> tuple[Amendment | None, RunResult | None]:
    if amendment is None or write_amendment:
        return None, None
    try:
        return parse_amendment(decode_json(amendment.read_bytes())), None
    except (OSError, ValueError) as error:
        return None, _amendment_invalid(amendment, error)


def _widening_failures(
    ctx: _AgainstContext,
    contract: ArchitectureContract,
    baseline: Path | None,
    after_baseline: tuple[KnownViolation, ...],
) -> tuple[str, ...]:
    """Every unamended widening from `ctx.contract` to `contract` (AD-61, #11)."""
    if ctx.against is None or ctx.contract is None:
        return ()
    findings = list(contract_widenings(ctx.contract, contract))
    if baseline is not None:
        findings += list(baseline_widenings(ctx.baseline, after_baseline))
    amended = ctx.write_amendment or (
        ctx.parsed_amendment is not None
        and verify_amendment(
            ctx.parsed_amendment,
            before_digest=contract_digest(ctx.contract),
            after_digest=contract_digest(contract),
        )
    )
    return tuple(findings) if findings and not amended else ()


def _artifact_files(
    *,
    write_baseline: bool,
    baseline: Path | None,
    violations: tuple[KnownViolation, ...],
    against: _AgainstContext,
    contract: ArchitectureContract,
    edits: tuple[tuple[str, str], ...],
    exit_code: int,
) -> tuple[dict[str, bytes], str | None]:
    """Every file this run writes, and the last one written, as the result's `artifact`.

    AD-46/AD-57: every rewritten graph page is written before the diagnostics judge it,
    whatever they say; a baseline or an amendment records what a run could judge, so exit 2
    writes neither.
    """
    files: dict[str, bytes] = {}
    artifact: str | None = None
    if write_baseline and baseline is not None and exit_code != 2:
        artifact = str(baseline)
        files[artifact] = baseline_bytes(violations)
    if (
        against.write_amendment
        and against.contract is not None
        and against.amendment is not None
        and exit_code != 2
    ):
        artifact = str(against.amendment)
        files[artifact] = amendment_bytes(
            Amendment(
                contract_digest(against.contract),
                contract_digest(contract),
                against.decided_by or "",
                against.rationale or "",
            )
        )
    for page, written in edits:
        artifact = page
        files[page] = written.encode()
    return files, artifact


def _baseline_at(root: Path, baseline: Path | None) -> str | None:
    """`--baseline`'s repository-relative path, or None when it names no path under `root`.

    A baseline outside the repository has no Git history to compare `--against` with, so its
    widening is simply not checked.
    """
    if baseline is None:
        return None
    try:
        return baseline.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def run_validate(
    root: Path,
    config: ScanConfig,
    analyzer: Analyzer,
    *,
    write_graph: bool = False,
    baseline: Path | None = None,
    write_baseline: bool = False,
    against: str | None = None,
    amendment: Path | None = None,
    write_amendment: bool = False,
    decided_by: str | None = None,
    rationale: str | None = None,
) -> tuple[RunResult, dict[str, bytes]]:
    """Validate contract structure, repository references and observed architecture.

    AD-46/AD-57: with `write_graph`, every rewritten graph page comes back for the caller to
    write, the way `run_init` returns its files.

    AD-52: with `baseline`, the violations that file already states are known debt, and only
    the difference is reported - as `failures` with exit 1. `write_baseline` writes today's
    violations to that same path instead of comparing them.

    AD-61 (#11): with `against`, the contract at that Git revision - and, when `baseline` is
    also given, the baseline file there too - is compared with the one being validated;
    every widening (ir.widening.contract_widenings, ir.widening.baseline_widenings) is a
    `failures` entry with exit 1 unless `amendment` binds exactly this before/after pair.
    `write_amendment` writes that binding instead of checking it.
    """
    known: tuple[KnownViolation, ...] = ()
    if baseline is not None and not write_baseline:
        try:
            known = parse_baseline(decode_json(baseline.read_bytes()))
        except (OSError, ValueError) as error:
            return _baseline_invalid(baseline, error), {}
    parsed_contract = _parse_contract_or_invalid(root, config)
    if isinstance(parsed_contract, RunResult):
        return parsed_contract, {}
    contract = parsed_contract
    against_ctx, against_error = _resolve_against_context(
        root, config, against, baseline, amendment, write_amendment, decided_by, rationale
    )
    if against_error is not None:
        return against_error, {}
    references = reference_diagnostics(root, config, contract)
    if references:
        return RunResult("validate", 2, diagnostics=references), {}
    observed = _observed_or_invalid(root, config, analyzer)
    if isinstance(observed, RunResult):
        return observed, {}
    observation = observed
    diagnostics, edits = _repository_diagnostics(
        root, config, contract, observation, write_graph, baseline is None
    )
    violations = observed_violations(observation) if baseline is not None else ()
    baseline_failures = (
        () if write_baseline or baseline is None else compare_violations(known, violations)
    )
    widening_failures = _widening_failures(
        against_ctx, contract, baseline, violations if write_baseline else known
    )
    result = _observed_result(observation, diagnostics, (*baseline_failures, *widening_failures))
    files, artifact = _artifact_files(
        write_baseline=write_baseline,
        baseline=baseline,
        violations=violations,
        against=against_ctx,
        contract=contract,
        edits=edits,
        exit_code=result.exit_code,
    )
    return (result if artifact is None else replace(result, artifact=artifact)), files
