# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11/AD-12 validate diagnostic rows: coded contract_invalid findings and uncoded kinds."""

from __future__ import annotations

from archkeel.check.validation import COMPONENT_GRAPH_MARKER
from fixtures.demo_catalog_support import (
    CLEAN_SHOP_MD,
    HEADER,
    Variant,
    contract_component_field_appended,
    contract_rule_field,
    contract_rule_provenance_appended,
    contract_top_field,
    contract_with_rule,
    contract_without_component_field,
    contract_without_top_field,
)

_VALIDATION_CODED_ROWS: tuple[Variant, ...] = (
    Variant(
        id="validation-interface-undeclared",
        section="validation",
        item="interface.undeclared",
        summary="Removing COMP-APP's public declaration leaves its existing inbound import "
        "from shop.cli undeclared.",
        files={"architecture-contract.json": contract_without_component_field("app", "public")},
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
        "marked graphs. graph.drift is demonstrated separately by the forbidden_dependency "
        "pair variant, whose new edge disagrees with the (still present) marked graph.",
        files={"docs/architecture/shop.md": CLEAN_SHOP_MD.split(COMPONENT_GRAPH_MARKER, 1)[0]},
        expected_violations=(),
        expected_codes=("graph.count",),
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

VARIANTS: tuple[Variant, ...] = (
    *_VALIDATION_CODED_ROWS,
    _VALIDATION_RULE_WITHOUT_SUBJECTS,
    _VALIDATION_PARSE_ERROR,
    _VALIDATION_SCOPE_EMPTY,
    _VALIDATION_RUNTIME_MISMATCH,
    _VALIDATION_MISSING_TOOL,
    _VALIDATION_TIMEOUT,
    _VALIDATION_INCOMPARABLE_RUNTIME,
    _VALIDATION_EXISTING_FILES,
)
