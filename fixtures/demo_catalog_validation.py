# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11/AD-12 validate diagnostic rows: coded contract_invalid findings and uncoded kinds."""

from __future__ import annotations

from archkeel.check.validation import COMPONENT_GRAPH_MARKER, TARGET_GRAPH_MARKER
from fixtures.demo_catalog_support import (
    CLEAN_SHOP_MD,
    HEADER,
    Variant,
    contract_component_field_appended,
    contract_component_field_set,
    contract_declarations_field_appended,
    contract_rule_field,
    contract_rule_provenance_appended,
    contract_rule_replaced,
    contract_top_field,
    contract_with_rule,
    contract_without_component_field_and_rule,
    contract_without_top_field,
    inside_contract,
)

# A contract edit AD-46 was written for: a component renamed after the page was drawn.
_RENDER_RENAMED = contract_component_field_set("render", "label", "view")
_PAGE_WITH_SUBGRAPH = CLEAN_SHOP_MD.replace(
    "    cli --> app\n    cli --> render\n",
    "    subgraph composition\n    cli --> app\n    cli --> render\n    end\n",
)

# AD-57: a pair the closed world already decided forbidden, swapped to allowed - the pair no
# code observes, so only the target-permitted set grows; the observed graph is untouched.
_CLI_ALLOWS_MODEL = contract_rule_replaced(
    "DEP-CLI-NO-MODEL",
    {
        "id": "DEP-CLI-ALLOWS-MODEL",
        "kind": "allowed_dependency",
        "source": "shop.cli",
        "target": "shop.model",
        "rationale": "The composition root may construct a default order directly, ahead of "
        "the use case that will call it; nothing does yet.",
        "provenance": ["docs/architecture/shop.md"],
        "decided_by": "architect",
    },
)


def _target_block_with_subgraph(page: str) -> str:
    """`page` with only its target graph's `cli` edges grouped in a `subgraph` (AD-57).

    Slicing on the two markers, rather than `.replace`, keeps the edit inside the target
    block alone: in the clean sample the target and observed graphs draw the same edges, so a
    blind text replace would wrap both.
    """
    before, marker, rest = page.partition(TARGET_GRAPH_MARKER)
    block, tail_marker, after = rest.partition(COMPONENT_GRAPH_MARKER)
    wrapped = block.replace(
        "    cli --> app\n    cli --> render\n",
        "    subgraph composition\n    cli --> app\n    cli --> render\n    end\n",
    )
    return before + marker + wrapped + tail_marker + after


_TARGET_PAGE_WITH_SUBGRAPH = _target_block_with_subgraph(CLEAN_SHOP_MD)

_VALIDATION_CODED_ROWS: tuple[Variant, ...] = (
    Variant(
        id="validation-interface-undeclared",
        section="validation",
        item="interface.undeclared",
        summary="Removing COMP-APP's public declaration leaves its existing inbound import "
        "from shop.cli undeclared; APP-TYPES-NOT-DICT is removed with it, since a boundary_types "
        "rule scoped to a component with no declared public has nothing to inspect and would "
        "otherwise report rule_without_subjects first (AD-63, issue #56).",
        files={
            "architecture-contract.json": contract_without_component_field_and_rule(
                "app", "public", "APP-TYPES-NOT-DICT"
            )
        },
        expected_violations=(),
        expected_codes=("interface.undeclared",),
    ),
    Variant(
        id="validation-interface-unused",
        section="validation",
        item="interface.unused",
        summary="Declaring shop.model.entities:Discount as public adds an entry no "
        "cross-component import reaches.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "model", "public", "shop.model.entities:Discount"
            )
        },
        expected_violations=(),
        expected_codes=("interface.unused",),
    ),
    Variant(
        id="validation-interface-missing",
        section="validation",
        item="interface.missing",
        summary="Declaring shop.app.future:NotBuiltYet as public names a module the scan "
        "never saw; unlike interface.unused, no cross-component import could ever reach it.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "app", "public", "shop.app.future:NotBuiltYet"
            )
        },
        expected_violations=(),
        expected_codes=("interface.missing",),
    ),
    Variant(
        id="validation-api-surface-missing",
        section="validation",
        item="api_surface.missing",
        summary="Declaring shop.app.future:NotBuiltYet in declarations.public_api names a "
        "module the scan never saw; unlike a component's public list, public_api names a "
        "consumer outside the package, so there is no cross-component import that could ever "
        "make an unused twin possible (AD-66, issue #58).",
        files={
            "architecture-contract.json": contract_declarations_field_appended(
                "public_api", "shop.app.future:NotBuiltYet"
            )
        },
        expected_violations=(),
        expected_codes=("api_surface.missing",),
    ),
    Variant(
        id="validation-api-surface-not-exported",
        section="validation",
        item="api_surface.missing:not_in_all",
        summary="Declaring shop.model.entities:NotExported in declarations.public_api names a "
        "module the scan saw whose own __all__ does not list it; the module proves the promise "
        "absent, not merely unproven (AD-71).",
        files={
            "architecture-contract.json": contract_declarations_field_appended(
                "public_api", "shop.model.entities:NotExported"
            )
        },
        expected_violations=(),
        expected_codes=("api_surface.missing",),
    ),
    Variant(
        id="validation-interface-planned-not-built",
        section="validation",
        item="interface.planned_built:not yet built",
        summary="The same not-yet-existing entry, moved from public to planned, is target work "
        "and produces no diagnostic (AD-56): the refactoring has not reached it yet.",
        files={
            "architecture-contract.json": contract_component_field_set(
                "app", "planned", ["shop.app.future:NotBuiltYet"]
            )
        },
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="validation-interface-planned-built",
        section="validation",
        item="interface.planned_built:stale marker",
        summary="Marking shop.app.maintenance as planned when the scan already sees that "
        "module is a stale marker (AD-56): the refactoring caught up and the contract did not.",
        files={
            "architecture-contract.json": contract_component_field_set(
                "app", "planned", ["shop.app.maintenance"]
            )
        },
        expected_violations=(),
        expected_codes=("interface.planned_built",),
    ),
    Variant(
        id="validation-agent-decisions-attributed",
        section="validation",
        item="agent_decisions:agent-attributed",
        summary="COMP-RENDER's decided_by is set to agent instead of architect: the same "
        "declared public list, attributed differently. No rule reads decided_by, so nothing "
        "fails; agent_decisions alone moves from [0, 46] to [1, 46] (AD-50).",
        files={
            "architecture-contract.json": contract_component_field_set(
                "render", "decided_by", "agent"
            )
        },
        expected_violations=(),
        expected_codes=(),
    ),
    Variant(
        id="validation-rationale-placeholder",
        section="validation",
        item="rationale.placeholder",
        summary="DEP-MODEL-NO-STORE's rationale is replaced with a placeholder.",
        files={
            "architecture-contract.json": contract_rule_field(
                "DEP-MODEL-NO-STORE", rationale="TODO: fill this in later."
            )
        },
        expected_violations=(),
        expected_codes=("rationale.placeholder",),
    ),
    Variant(
        id="validation-rationale-repeated",
        section="validation",
        item="rationale.repeated",
        summary="DEP-MODEL-NO-CLI's rationale only restates the forbidden dependency.",
        files={
            "architecture-contract.json": contract_rule_field(
                "DEP-MODEL-NO-CLI", rationale="shop.model does not depend on shop.cli."
            )
        },
        expected_violations=(),
        expected_codes=("rationale.repeated",),
    ),
    Variant(
        id="validation-graph-count",
        section="validation",
        item="graph.count",
        summary="Removing the marked Mermaid graph from docs/architecture/shop.md leaves zero "
        "marked graphs, so neither --write-graph nor a reader can tell which graph is meant. "
        "graph.drift has the two rows below.",
        files={"docs/architecture/shop.md": CLEAN_SHOP_MD.split(COMPONENT_GRAPH_MARKER, 1)[0]},
        expected_violations=(),
        expected_codes=("graph.count",),
    ),
    Variant(
        id="validation-graph-drift-write-graph",
        section="validation",
        item="graph.drift:write-graph",
        summary="A contract edit renames COMP-RENDER's label to view, and both marked graphs in "
        "docs/architecture/shop.md still draw render: the observed graph, and the target graph "
        "it agrees with today (AD-57). The remedy names archkeel validate --write-graph, which "
        "rewrites both graphs' edges; validate then passes (AD-46).",
        files={"architecture-contract.json": _RENDER_RENAMED},
        expected_violations=(),
        expected_codes=("graph.drift", "graph.drift"),
    ),
    Variant(
        id="validation-graph-drift-subgraph",
        section="validation",
        item="graph.drift:subgraph",
        summary="The same rename, on a page whose two marked graphs both group cli's edges in a "
        "subgraph. Rewritten edges could leave it, so --write-graph writes nothing for either "
        "block, and each remedy names `subgraph composition` and asks for a hand edit (AD-46).",
        files={
            "architecture-contract.json": _RENDER_RENAMED,
            "docs/architecture/shop.md": _PAGE_WITH_SUBGRAPH,
        },
        expected_violations=(),
        expected_codes=("graph.drift", "graph.drift"),
    ),
    Variant(
        id="validation-target-graph-drift-write-graph",
        section="validation",
        item="graph.drift:target-write-graph",
        summary="A contract edit allows cli to depend on model, a pair the code has never used. "
        "The observed graph still matches; only the target graph is stale, and its subject names "
        "the target marker, not the observed one. --write-graph regenerates that block alone "
        "(AD-57).",
        files={"architecture-contract.json": _CLI_ALLOWS_MODEL},
        expected_violations=(),
        expected_codes=("graph.drift",),
    ),
    Variant(
        id="validation-target-graph-drift-subgraph",
        section="validation",
        item="graph.drift:target-subgraph",
        summary="The same allowance, on a page whose target graph alone groups cli's edges in a "
        "subgraph; the observed graph is untouched. --write-graph writes nothing for the target "
        "block, and the remedy names `subgraph composition` and asks for a hand edit, the rule "
        "AD-46 gave the observed graph applied to the target one (AD-57).",
        files={
            "architecture-contract.json": _CLI_ALLOWS_MODEL,
            "docs/architecture/shop.md": _TARGET_PAGE_WITH_SUBGRAPH,
        },
        expected_violations=(),
        expected_codes=("graph.drift",),
    ),
    Variant(
        id="validation-reference-namespace",
        section="validation",
        item="reference.namespace",
        summary="COMP-MODEL gains a package outside the configured shop namespace.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "model", "packages", "other.namespace"
            )
        },
        expected_violations=(),
        expected_codes=("reference.namespace",),
    ),
    Variant(
        id="validation-reference-public-owner",
        section="validation",
        item="reference.public_owner",
        summary="COMP-MODEL declares a public entry from shop.store.repository, a module it "
        "does not own.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "model", "public", "shop.store.repository:OrderRepository"
            )
        },
        expected_violations=(),
        expected_codes=("reference.public_owner",),
    ),
    Variant(
        id="validation-reference-public-underscore",
        section="validation",
        item="reference.public_underscore",
        summary="COMP-MODEL declares a public entry naming an underscore symbol.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "model", "public", "shop.model.entities:_Hidden"
            )
        },
        expected_violations=(),
        expected_codes=("reference.public_underscore",),
    ),
    Variant(
        id="validation-reference-provenance",
        section="validation",
        item="reference.provenance",
        summary="DEP-MODEL-NO-STORE cites a provenance file that does not exist.",
        files={
            "architecture-contract.json": contract_rule_provenance_appended(
                "DEP-MODEL-NO-STORE", "docs/architecture/missing.md"
            )
        },
        expected_violations=(),
        expected_codes=("reference.provenance",),
    ),
    Variant(
        id="validation-reference-package-unscanned",
        section="validation",
        item="reference.package_unscanned",
        summary="COMP-MODEL gains an in-namespace package with no scanned module.",
        files={
            "architecture-contract.json": contract_component_field_appended(
                "model", "packages", "shop.model.reports"
            )
        },
        expected_violations=(),
        expected_codes=("reference.package_unscanned",),
    ),
    Variant(
        id="validation-contract-schema-version",
        section="validation",
        item="contract.schema_version",
        summary="The contract declares schema_version 1.1.0, which validate cannot parse.",
        files={"architecture-contract.json": contract_top_field("schema_version", "1.1.0")},
        expected_violations=(),
        expected_codes=("contract.schema_version",),
    ),
    Variant(
        id="validation-contract-invalid",
        section="validation",
        item="contract.invalid",
        summary="The contract is missing its required rules array entirely.",
        files={"architecture-contract.json": contract_without_top_field("rules")},
        expected_violations=(),
        expected_codes=("contract.invalid",),
    ),
    Variant(
        id="validation-observation-incomplete",
        section="validation",
        item="observation.incomplete",
        summary="observation.incomplete requires inspect_observation to raise on a malformed "
        "synthetic observation; a real repository scan never produces one.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_trace.py",
    ),
    Variant(
        id="validation-baseline-invalid",
        section="validation",
        item="baseline.invalid",
        summary="baseline.invalid needs a --baseline file that cannot be read, and every row "
        "here runs validate on the sample without one (AD-52); the baseline tests supply "
        "a missing file and a malformed one instead.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_baseline.py",
    ),
    Variant(
        id="validation-against-invalid",
        section="validation",
        item="against.invalid",
        summary="against.invalid needs a --against revision this repository cannot resolve, "
        "or whose contract cannot be read; every row here runs validate on the sample without "
        "--against (AD-61, #11). The widening tests supply an unresolvable revision instead.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_widening.py",
    ),
    Variant(
        id="validation-amendment-invalid",
        section="validation",
        item="amendment.invalid",
        summary="amendment.invalid needs a --amendment file that cannot be read (AD-61, #11); "
        "the widening tests supply a missing file and a malformed one instead.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_widening.py",
    ),
    Variant(
        id="validation-inside-public-mismatch",
        section="validation",
        item="inside.public_mismatch",
        summary="The contract COMP-STORE names for its inside is replaced by one whose single "
        "sub-component offers a different public surface than the level above declares for "
        "store (AD-20).",
        files={
            "shop/store/architecture-contract.json": inside_contract(
                ["shop.store.repository:Ledger"]
            ),
        },
        expected_violations=(),
        expected_codes=("inside.public_mismatch",),
    ),
    Variant(
        id="validation-inside-forbidden-import",
        section="validation",
        item="inside.forbidden_import",
        summary="The replacement inside contract repeats store's public surface exactly, so only "
        "the second AD-20 check fires: the inside allows shop.render, which DEP-STORE-NO-RENDER "
        "forbids.",
        files={
            "shop/store/architecture-contract.json": inside_contract(
                [
                    "shop.store.repository:OrderRepository",
                    "shop.store.sqlite:vacuum",
                    "shop.store.sqlite:Connection",
                ],
                "shop.render",
            ),
        },
        expected_violations=(),
        expected_codes=("inside.forbidden_import",),
    ),
    Variant(
        id="validation-inside-contract-missing",
        section="validation",
        item="contract.invalid:inside",
        summary="The contract COMP-STORE names for its inside is deleted. The observation "
        "carries the level or none of it, so report stays silent and validate alone answers, "
        "with contract.invalid at /components/1/inside (AD-20).",
        files={"shop/store/architecture-contract.json": None},
        expected_violations=(),
        expected_codes=("contract.invalid",),
    ),
)

# AD-72: shop.app.orders declares no __all__, so neither it nor the scan's own symbols can
# settle a promised name the module never defines. That is a limit of what the scan can prove,
# not a proven defect (AD-67's own boundary for dynamic_call_limit/context_alias_limit), so
# validate reports it as an analyzer-side `unknowns` record, never as a diagnostic of any kind
# (coded or not) and never gates the exit code -- unlike the two rows above, where the module or
# its own __all__ does prove the promise broken.
_VALIDATION_API_SURFACE_UNKNOWN = Variant(
    id="validation-api-surface-unknown",
    section="validation",
    item="api_surface_unknown",
    summary="shop.app.orders:TypoThatIsNotReal names a module the scan saw that declares no "
    "__all__; the scan's own symbols do not record that name either, so the promise is neither "
    "proven kept nor proven broken. The analyzer records this as an `unknowns` entry, not a "
    "diagnostic of any kind, so validate neither gates nor passes it silently.",
    files={
        "architecture-contract.json": contract_declarations_field_appended(
            "public_api", "shop.app.orders:TypoThatIsNotReal"
        )
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=(("api_surface_limit", "shop.app.orders:TypoThatIsNotReal"),),
)
# AD-12 follow-up: the analyzer always folds a rule-without-subjects unknown into
# coverage.failures too, so validate returns the analyzer's own uncoded rule_without_subjects
# diagnostic kind before observation_diagnostics could ever attach a code. That dead branch and
# the unreachable "rule.without_subjects" DiagnosticCode were removed; this row now demonstrates
# the real, uncoded kind instead.
_VALIDATION_RULE_WITHOUT_SUBJECTS = Variant(
    id="validation-rule-without-subjects",
    section="validation",
    item="rule_without_subjects",
    summary="A forbidden_construct rule's source, shop.nonexistent, matches no scanned "
    "module; the analyzer reports the uncoded rule_without_subjects diagnostic kind.",
    files={
        "architecture-contract.json": contract_with_rule(
            {
                "id": "CONSTRUCT-NO-SUBJECTS",
                "kind": "forbidden_construct",
                "source": "shop.nonexistent",
                "constructs": ["assert"],
                "rationale": "A rule whose source matches no scanned module, for the "
                "architecture demo's rule_without_subjects coverage.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        )
    },
    expected_violations=(),
    expected_codes=(),
    expected_kinds=("rule_without_subjects",),
)
_VALIDATION_PARSE_ERROR = Variant(
    id="validation-parse-error",
    section="validation",
    item="parse_error",
    summary="shop/model/broken_syntax.py has invalid syntax; the analyzer reports an uncoded "
    "parse_error diagnostic before any contract check runs.",
    files={
        "shop/model/broken_syntax.py": HEADER
        + ('"""Deliberately invalid syntax for the architecture demo."""\n\ndef broken(\n')
    },
    expected_violations=(),
    expected_codes=(),
    expected_kinds=("parse_error",),
)
_SHOP_PY_FILES = (
    "shop/app/maintenance.py",
    "shop/app/orders.py",
    "shop/cli/main.py",
    "shop/model/entities.py",
    "shop/render/text.py",
    "shop/store/__init__.py",
    "shop/store/backend/__init__.py",
    "shop/store/backend/files.py",
    "shop/store/backend/paths.py",
    "shop/store/codec.py",
    "shop/store/repository.py",
    "shop/store/sqlite.py",
)
_VALIDATION_SCOPE_EMPTY = Variant(
    id="validation-scope-empty",
    section="validation",
    item="scope_empty",
    summary="Every shop/*.py file is removed and the rules array is emptied with it, so no "
    "rule also goes subjectless; the analyzer reports only an uncoded scope_empty "
    "diagnostic, since the configured scope discovers no Python files.",
    files={
        **dict.fromkeys(_SHOP_PY_FILES),
        "architecture-contract.json": contract_top_field("rules", []),
    },
    expected_violations=(),
    expected_codes=(),
    expected_kinds=("scope_empty",),
)
_VALIDATION_RUNTIME_MISMATCH = Variant(
    id="validation-runtime-mismatch",
    section="validation",
    item="runtime_mismatch",
    summary='pyproject.toml declares requires-python "<3.0", which the running interpreter '
    "never satisfies; the analyzer reports an uncoded runtime_mismatch diagnostic "
    "regardless of the rest of the scan.",
    files={
        "pyproject.toml": '[project]\nname = "shop-architecture-fixture"\n'
        'version = "0.1.0"\nrequires-python = "<3.0"\n'
    },
    expected_violations=(),
    expected_codes=(),
    expected_kinds=("runtime_mismatch",),
)
_VALIDATION_MISSING_TOOL = Variant(
    id="validation-missing-tool",
    section="validation",
    item="missing_tool",
    summary="missing_tool requires a broken Python executable; not producible from a "
    "repository overlay.",
    files={},
    expected_violations=(),
    expected_codes=(),
    evidence="tests/test_analyzer.py",
)
_VALIDATION_TIMEOUT = Variant(
    id="validation-timeout",
    section="validation",
    item="timeout",
    summary="timeout requires the analyzer to exceed its 60-second budget; not producible "
    "from a repository overlay.",
    files={},
    expected_violations=(),
    expected_codes=(),
    evidence="tests/test_analyzer.py",
)
_VALIDATION_INCOMPARABLE_RUNTIME = Variant(
    id="validation-incomparable-runtime",
    section="validation",
    item="incomparable_runtime",
    summary="incomparable_runtime compares two observations inside a delta, not a single "
    "validate or report run.",
    files={},
    expected_violations=(),
    expected_codes=(),
    evidence="tests/test_runtime_delta.py",
)
_VALIDATION_EXISTING_FILES = Variant(
    id="validation-existing-files",
    section="validation",
    item="existing_files",
    summary="existing_files is raised by archkeel init refusing to overwrite files, not by "
    "validate or report.",
    files={},
    expected_violations=(),
    expected_codes=(),
    evidence="tests/test_onboarding.py",
)
_VALIDATION_FILTER_UNKNOWN = Variant(
    id="validation-filter-unknown",
    section="validation",
    item="filter_unknown",
    summary="filter_unknown is raised by report --rule or --component naming a rule or "
    "component this contract does not declare (AD-60); the generic overlay harness runs a "
    "plain report/validate with no CLI argument to carry it.",
    files={},
    expected_violations=(),
    expected_codes=(),
    evidence="tests/test_report_filter.py",
)

VARIANTS: tuple[Variant, ...] = (
    *_VALIDATION_CODED_ROWS,
    _VALIDATION_API_SURFACE_UNKNOWN,
    _VALIDATION_RULE_WITHOUT_SUBJECTS,
    _VALIDATION_PARSE_ERROR,
    _VALIDATION_SCOPE_EMPTY,
    _VALIDATION_RUNTIME_MISMATCH,
    _VALIDATION_MISSING_TOOL,
    _VALIDATION_TIMEOUT,
    _VALIDATION_INCOMPARABLE_RUNTIME,
    _VALIDATION_EXISTING_FILES,
    _VALIDATION_FILTER_UNKNOWN,
)
