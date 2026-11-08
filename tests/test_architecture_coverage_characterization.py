# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tests of the coverage logic that the IR and the rules shared as copies (#880, steps S2 and S3).

D3 is the meaning of "the observation is complete". D4 is the meaning of "the scan roots cover
the source". Each test calls one caller with shared cases. #882 pinned the copies and showed
where they differed. AD-322 merged them into `archkeel.ir.coverage` and chose one rule for each
difference. These tests now pin that every caller gives the same answer.
"""

from dataclasses import replace
from typing import Any

import pytest
from test_architecture_owner_characterization import _ownership_model
from test_decisions import _declaration, _observation
from test_module_explore import _sample

from archkeel.check.evaluation.rules import source_domains_complete
from archkeel.ir.architecture_graph import (
    CoverageStatus,
    EntityKind,
    PresenceKind,
    RelationshipKind,
)
from archkeel.ir.coverage import observation_covers_rule
from archkeel.ir.decisions import rule_uncertainty_evidence
from archkeel.ir.facts import SourceInfo
from archkeel.ir.model import EvidenceClass, Observation, Record, RecordData, Section, Verdict
from archkeel.ir.module_explore import module_exploration
from archkeel.ir.profiles import profile_for
from archkeel.ir.report_projection import _import_coverage
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.view_spec import (
    ViewSpec,
    ViewSpecVersion,
    _view_graph,
    check_view,
    snapshot_identity,
)

_FAILURE = Record(
    "FAILURE",
    EvidenceClass.UNKNOWN,
    "analysis_coverage",
    "source_read_failure",
    "one file was not read",
    (),
    (),
    (),
    (),
    (),
    RecordData(),
)

# D3 shared cases: the status and the failure list of the observation coverage.
PASS = "pass"
PASS_WITH_FAILURES = "pass with failures"
FAIL = "fail"
FAIL_WITH_FAILURES = "fail with failures"
_STATES: dict[str, tuple[Verdict, tuple[Record, ...]]] = {
    PASS: (Verdict.PASS, ()),
    PASS_WITH_FAILURES: (Verdict.PASS, (_FAILURE,)),
    FAIL: (Verdict.FAIL, ()),
    FAIL_WITH_FAILURES: (Verdict.FAIL, (_FAILURE,)),
}
# Only a clean PASS is complete (AD-322). Before, some copies also called a PASS with failures
# complete and the others did not. The producer never writes that state: it sets FAIL when it
# records a failure. A saved observation that was written by hand can have it.
COMPLETE = {PASS: True, PASS_WITH_FAILURES: False, FAIL: False, FAIL_WITH_FAILURES: False}


def _in_state(model: Observation, state: str) -> Observation:
    status, failures = _STATES[state]
    return replace(model, coverage=replace(model.coverage, status=status, failures=failures))


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    return _sample(tmp_path_factory.mktemp("sample"))


@pytest.fixture(scope="module")
def inheriting_sample(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    files = {"sample/base.py": "class A:\n    pass\n\n\nclass B(A):\n    pass\n"}
    return _sample(tmp_path_factory.mktemp("inheriting"), extra_files=files)


@pytest.mark.parametrize("state", list(_STATES))
def test_source_graph_coverage_reads_the_status_and_the_failures(
    state: str, inheriting_sample: Observation
) -> None:
    """Records the behaviour of source_graph.observed_graph coverage.
    AD-322 merged the copies of this check.

    The inheritance, ownership and import rows are complete only for a PASS without failures."""
    graph = observed_graph(_in_state(inheriting_sample, state))
    kinds = {item.id: item.kind for item in graph.entities}
    expected = CoverageStatus.COMPLETE if COMPLETE[state] else CoverageStatus.PARTIAL
    for entity_kind, relationship in (
        (EntityKind.CLASS, RelationshipKind.INHERITS),
        (EntityKind.PACKAGE, RelationshipKind.OWNS),
        (EntityKind.MODULE, RelationshipKind.IMPORTS),
    ):
        found = {
            item.status
            for item in graph.coverage
            if kinds[item.scope_id] == entity_kind and relationship in item.relationship_kinds
        }
        assert found == {expected}, relationship


@pytest.mark.parametrize("state", list(_STATES))
def test_report_projection_import_coverage_reads_the_status_and_the_failures(state: str) -> None:
    """Records the behaviour of report_projection._import_coverage.
    AD-322 merged the copies of this check."""
    model = _in_state(_ownership_model(), state)
    observed = observed_graph(model)
    modules = tuple(
        item
        for item in observed.entities
        if item.kind == EntityKind.MODULE and item.presence == PresenceKind.DEFINED
    )
    complete, unknowns = _import_coverage(model, observed, modules)
    assert complete is COMPLETE[state]
    assert bool(unknowns) is (not COMPLETE[state])


@pytest.mark.parametrize("state", list(_STATES))
def test_module_explore_import_status_reads_the_status_and_the_failures(
    state: str, sample: Observation
) -> None:
    """Records the behaviour of module_explore.module_exploration.
    AD-322 merged the copies of this check.

    The import status and the absence hints are PASS only for a PASS without failures."""
    model = _in_state(sample, state)
    level = next(item for item in module_exploration(model) if item.parent_id is None)
    assert (level.import_status == "PASS") is COMPLETE[state]
    hints = {item.kind for item in level.hint_candidates}
    assert ("no_owner" in hints) is COMPLETE[state]


@pytest.mark.parametrize("state", list(_STATES))
def test_view_spec_view_graph_reads_the_status_and_the_failures(state: str) -> None:
    """Records the behaviour of view_spec._view_graph.
    AD-322 merged the copies of this check."""
    graph = _view_graph(_in_state(_ownership_model(), state), story=False)
    assert graph.complete is COMPLETE[state]


@pytest.mark.parametrize("state", list(_STATES))
def test_view_spec_view_graph_layer_reads_the_status_and_the_failures(state: str) -> None:
    """Records the behaviour of view_spec._view_graph layers.
    AD-322 merged the copies of this check."""
    graph = _view_graph(_in_state(_ownership_model(), state), story=False)
    reason = graph.layers[RelationshipKind.IMPORTS].everywhere
    assert (reason is None) is COMPLETE[state]


@pytest.mark.parametrize("state", list(_STATES))
def test_view_spec_check_view_reads_the_status_and_the_failures(state: str) -> None:
    """Records the behaviour of view_spec.check_view.
    AD-322 merged the copies of this check."""
    model = _in_state(_ownership_model(), state)
    spec = ViewSpec(ViewSpecVersion.V1_0_0, "title", snapshot_identity(model), ())
    expected = "complete" if COMPLETE[state] else "incomplete"
    assert check_view(spec, model, strict=False).snapshot_completeness == expected


@pytest.mark.parametrize("state", list(_STATES))
def test_decisions_rule_uncertainty_adds_incomplete_execution_for_status_or_failures(
    state: str,
) -> None:
    """Records the behaviour of decisions.rule_uncertainty_evidence.
    AD-322 merged the copies of this check.

    The rule has no receipt, so no scope is proven in any state."""
    base = _observation((), (_declaration("RULE-A", "complete_requires", ()),))
    model = replace(base, sections=(*base.sections, Section("unknowns", ())))
    result = rule_uncertainty_evidence(_in_state(model, state))
    if COMPLETE[state]:
        assert result == {}
    else:
        assert [item.cause.value for item in result["RULE-A"].actions] == ["incomplete_execution"]


# ---------------------------------------------------------------------------------------------
# D4: do the scanned roots cover the source?
# ---------------------------------------------------------------------------------------------

_PYTHON = "archkeel-python-analyzer"
_TYPESCRIPT = "archkeel-typescript-imports"
_TREE = (
    ("sample", "src/sample/__init__.py"),
    ("sample.core", "src/sample/core/__init__.py"),
    ("sample.core.a", "src/sample/core/a.py"),
    ("sample.peer", "src/sample/peer/__init__.py"),
)
# A name that no directory layout explains: the file is not where the name says.
_OFF_LAYOUT = (*_TREE, ("sample.a.b.c", "x.py"))
_OTHER_LANGUAGE = (*_TREE, ("sample.ui", "src/sample/ui.ts"))
_TS_TREE = (("sample.core", "src/sample/core.ts"), ("sample.peer", "src/sample/peer.ts"))

# case id -> (source, modules, root, language, result). The root is the directory. A saved
# observation records it as `<root>/**/*.py`, the form the Python collector writes; the rules read
# the directory itself. A root that starts with "!" is a recorded scope: the observation reads it
# as written and the rules read it without a trailing Python glob.
_CASES: dict[str, tuple[str, tuple[tuple[str, str], ...], str, str, bool]] = {
    "root is the source directory": ("sample", _TREE, "src", _PYTHON, True),
    "root is the project root dot": ("sample", _TREE, ".", _PYTHON, True),
    "root is a subdirectory below the source": ("sample", _TREE, "src/sample/core", _PYTHON, False),
    "root is exactly the source subdirectory": (
        "sample.core",
        _TREE,
        "src/sample/core",
        _PYTHON,
        True,
    ),
    "root is a sibling directory": ("sample", _TREE, "lib", _PYTHON, False),
    "root is absolute": ("sample", _TREE, "/abs/src", _PYTHON, False),
    "the source has no module": ("other", _TREE, "src", _PYTHON, False),
    "root has a file of another language": ("sample", _OTHER_LANGUAGE, "src", _PYTHON, True),
    "a module file is off the name layout": ("sample", _OFF_LAYOUT, "src", _PYTHON, False),
    "typescript files under the root": ("sample", _TS_TREE, "src", _TYPESCRIPT, True),
    "root is a recorded glob": ("sample", _TREE, "!src/**/*.py", _PYTHON, True),
    "root is a recorded typescript glob": ("sample", _TS_TREE, "!src/**/*.ts", _TYPESCRIPT, False),
}


def _decision_result(source: str, modules: tuple[tuple[str, str], ...], root: str) -> bool:
    scope = root[1:] if root.startswith("!") else f"{root}/**/*.py"
    base = _observation(())
    records = tuple(
        Record(
            f"M-{name}",
            EvidenceClass.FACT,
            "module_topology",
            "module",
            name,
            (),
            (),
            (),
            (),
            (),
            RecordData((("qualified_name", name), ("file", file))),
        )
        for name, file in modules
    )
    model = replace(
        base,
        source=SourceInfo("0" * 40, False, "0" * 16, (scope,)),
        sections=(*base.sections, Section("modules", records)),
    )
    declaration = _declaration("RULE", "source_ownership", (("source", source),))
    return observation_covers_rule(model, declaration)


def _rules_result(
    source: str, modules: tuple[tuple[str, str], ...], root: str, language: str
) -> bool:
    records: Any = [
        {"id": f"M-{name}", "data": {"qualified_name": name, "file": file}}
        for name, file in modules
    ]
    return source_domains_complete(
        modules=records,
        profile=profile_for(language),
        package_scopes=(source,),
        exact_module_scopes=(),
        scan_roots=(root.removeprefix("!").removesuffix("/**/*.py"),),
    )


@pytest.mark.parametrize("case", list(_CASES))
def test_decisions_source_scope_covers_rule_by_case(case: str) -> None:
    """Records the behaviour of coverage.observation_covers_rule."""
    source, modules, root, _, expected = _CASES[case]
    assert _decision_result(source, modules, root) is expected


@pytest.mark.parametrize("case", list(_CASES))
def test_rules_source_domains_complete_by_case(case: str) -> None:
    """Records the behaviour of rules.source_domains_complete."""
    source, modules, root, language, expected = _CASES[case]
    assert _rules_result(source, modules, root, language) is expected


def test_decisions_and_rules_scope_coverage_agree_for_every_case() -> None:
    """The saved observation and the live scan give one answer for the same input.

    #882 pinned two differences. A recorded glob is the same root as its directory, which is an
    input form. A module whose file is off its name layout had an unknown physical domain. The
    copy in `decisions` skipped it and called the scope covered, and `rules` did not. AD-322 chose
    the rules answer: the scope is not covered, because the evidence cannot prove the domain."""
    different = {
        case
        for case, (source, modules, root, language, _) in _CASES.items()
        if _decision_result(source, modules, root) != _rules_result(source, modules, root, language)
    }
    assert different == set()


def test_rules_source_domains_complete_is_false_without_a_root_or_a_module() -> None:
    """Records the behaviour of rules.source_domains_complete."""
    records: Any = [{"id": "M", "data": {"qualified_name": "sample", "file": "src/sample.py"}}]
    python = profile_for(_PYTHON)
    for modules, roots in ((records, ()), ([], ("src",))):
        assert not source_domains_complete(
            modules=modules,
            profile=python,
            package_scopes=("sample",),
            exact_module_scopes=(),
            scan_roots=roots,
        )
    assert not source_domains_complete(
        modules=[], profile=python, package_scopes=(), exact_module_scopes=(), scan_roots=()
    )


def test_decisions_source_scope_needs_every_mapped_prefix_under_a_root() -> None:
    """Two mapped prefixes, src/sample and lib/sample: one root covers only the first.

    A mutant that needs only one covered prefix (`any` instead of `all`) returns True here."""
    modules = (
        ("sample.core", "src/sample/core/__init__.py"),
        ("sample.peer", "lib/sample/peer/__init__.py"),
    )
    assert _decision_result("sample", modules, "src") is False
    assert _decision_result("sample", modules, ".") is True


def test_rules_exact_module_scope_rejects_an_absolute_scan_root() -> None:
    """A module file below an absolute root is not covered: the roots of a scan are relative.

    A mutant that lets an absolute root contain a path returns True here."""
    records: Any = [{"id": "M", "data": {"qualified_name": "sample", "file": "/abs/src/sample.py"}}]
    assert not source_domains_complete(
        modules=records,
        profile=profile_for(_PYTHON),
        package_scopes=(),
        exact_module_scopes=("sample",),
        scan_roots=("/abs/src",),
    )


def test_rules_exact_module_scope_needs_every_exact_module_under_a_root() -> None:
    """The first exact module is under the root and the second is not: the scope is not covered.

    A mutant that checks only the first exact module returns True here."""
    records: Any = [
        {"id": "A", "data": {"qualified_name": "sample.a", "file": "src/sample/a.py"}},
        {"id": "B", "data": {"qualified_name": "sample.b", "file": "lib/sample/b.py"}},
    ]
    for scopes, expected in ((("sample.a",), True), (("sample.a", "sample.b"), False)):
        assert (
            source_domains_complete(
                modules=records,
                profile=profile_for(_PYTHON),
                package_scopes=(),
                exact_module_scopes=scopes,
                scan_roots=("src",),
            )
            is expected
        )
