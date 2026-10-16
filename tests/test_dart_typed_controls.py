# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nominal Dart API intent and actual Python implementation control proofs."""

from __future__ import annotations

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer.dart import collect, parse, resolve, snapshot
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
FIELDS = (
    (parse.Parameter, "kind", "ParameterKind"),
    (parse.Member, "kind", "MemberKind"),
    (parse.Member, "visibility", "Visibility"),
    (parse.Definition, "kind", "DefinitionKind"),
    (parse.Definition, "visibility", "Visibility"),
    (parse.Directive, "kind", "DirectiveKind"),
    (parse.Site, "kind", "SiteKind"),
    (parse.Site, "use", "SiteUse"),
    (resolve.ResolutionProblem, "kind", "ResolutionProblemKind"),
    (resolve.ResolvedBinding, "visibility", "Visibility"),
    (resolve.ResolvedSite, "status", "ResolutionStatus"),
    (resolve.ConstructionResolution, "status", "ResolutionStatus"),
    (resolve.ResolvedParameter, "kind", "ParameterKind"),
    (snapshot.Snapshot, "sdk_constraint_state", "RuntimeRequirementState"),
    (snapshot.SnapshotProblem, "kind", "SnapshotProblemKind"),
)
GUARDS = tuple(
    (f"DART-{name.upper()}-TYPED-CONTROL", f"archkeel.analyzer.dart.{name}")
    for name in ("syntax", "parse", "resolve", "snapshot", "collect")
)


@pytest.mark.parametrize("owner,field,expected", FIELDS)
def test_dart_control_fields_have_owned_nominal_types(owner, field, expected):
    actual = get_type_hints(owner)[field]
    assert isinstance(actual, type) and issubclass(actual, StrEnum), (owner, field, actual)
    assert actual.__name__ == expected


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, (result.diagnostics, result.failures)
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _contract():
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/dart.json").read_text())
    )
    contract.pop("$schema", None)
    contract["rules"] = [
        {
            "id": identifier,
            "kind": "forbidden_construct",
            "source": module,
            "constructs": ["string_literal_compare"],
            "rationale": "Closed Dart implementation controls have nominal owners.",
            "decided_by": "agent",
            "provenance": ["docs/architecture/dart-nominal-controls.md"],
        }
        for identifier, module in GUARDS
    ]
    fields = {
        f"{owner.__module__}.{owner.__name__}.{field}": expected
        for owner, field, expected in FIELDS
    }
    fields["archkeel.analyzer.dart.resolve.ResolvedTarget.builtin"] = "bool"
    selected = set(fields)
    selected.add("archkeel.analyzer.dart.syntax.Visibility.from_name")
    for name in fields:
        selected.add(name.rsplit(".", 1)[0])
        selected.add(name.rsplit(".", 2)[0])
    uml = contract["declarations"]["uml"]
    uml["entities"] = [
        entity
        for entity in uml["entities"]
        if entity["qualified_name"] in selected
        or (
            entity["kind"] == "enum"
            and entity["qualified_name"].startswith("archkeel.analyzer.dart.")
        )
    ]
    for entity in uml["entities"]:
        if entity["qualified_name"] in fields:
            entity["annotation"] = fields[entity["qualified_name"]]
    uml["relationships"] = []
    uml["scopes"] = []
    return contract


def _repository(tmp_path):
    paths = [
        *sorted((ROOT / "src/archkeel/analyzer/dart").glob("*.py")),
        ROOT / "src/archkeel/ir/facts.py",
        ROOT / "src/archkeel/ir/protocol.py",
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(_contract()),
        "docs/architecture/dart-nominal-controls.md": "Owned Dart control boundaries.\n",
        "docs/architecture/dart-input-grammar.md": (
            ROOT / "docs/architecture/dart-input-grammar.md"
        ).read_text(),
    }
    for path in paths:
        files[path.relative_to(ROOT / "src").as_posix()] = path.read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_dart_control_api_matches_independent_nominal_target(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessments = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    for identifier, _ in GUARDS:
        assert (
            assessments[identifier].status == "PASS" and assessments[identifier].evaluation_proven
        )
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "probe",
    [
        'def _control_probe(value):\n    return value == "import"\n',
        'def _control_probe(value):\n    return value in ("import", "export")\n',
        'def _control_probe(value):\n    return "import" in value\n',
        (
            'def _control_probe(value):\n    match value:\n        case "import":\n'
            "            return True\n        case _:\n            return False\n"
        ),
        (
            'from typing import Final\nCONTROL: Final[str] = "import"\n'
            "def _control_probe(value):\n    return value == CONTROL\n"
        ),
        'def _control_probe(value):\n    return value.startswith("import")\n',
        'def _control_probe(value):\n    return value.endswith((".dart", ".g.dart"))\n',
    ],
    ids=["equality", "membership", "needle", "match", "final", "prefix", "suffix"],
)
def test_native_dart_control_guard_rejects_actual_source_string_dispatch(tmp_path, probe):
    root, config = _repository(tmp_path)
    path = root / "archkeel/analyzer/dart/parse.py"
    path.write_text(path.read_text() + "\n" + probe)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    probes = {
        row.id
        for row in model.records("constructs")
        if "_control_probe" in str(row.data.get("owner", ""))
        and row.data.get("construct") == "string_literal_compare"
    }
    assert probes
    assert any(probes.intersection(row.fact_ids) for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize(
    "module,narrow,broad",
    [
        ("syntax", "kind: ParameterKind", "kind: str"),
        ("resolve", "status: ResolutionStatus", "status: str"),
        ("resolve", "builtin: bool", "builtin: str"),
        (
            "resolve",
            "visibility: Visibility = field(init=False)",
            "visibility: str = field(init=False)",
        ),
    ],
)
def test_native_dart_nominal_annotation_widening_fails_without_target_change(
    tmp_path, module, narrow, broad
):
    root, config = _repository(tmp_path)
    path = root / f"archkeel/analyzer/dart/{module}.py"
    source = path.read_text()
    assert narrow in source
    path.write_text(source.replace(narrow, broad, 1))
    before = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.aspect == "annotation" and row.status == "FAIL" for row in comparison.assessments
    )
    assert (root / "contract.json").read_bytes() == before


def test_parse_node_view_preserves_tree_identity_fields_and_unknown_children():
    raw = parse._PARSER.parse(
        b"void main() { var value = 1; value = other; return value; }"
    ).root_node
    tree = parse._Tree()
    root = tree.wrap(raw)
    assert tree.wrap(raw) is root
    nodes = tuple(parse._walk(root))
    assert any(node.kind is None and node.named_children for node in nodes)
    assert any(
        node.kind is None
        and any(child.kind == parse._NodeKind.IDENTIFIER for child in node.named_children)
        for node in nodes
    )
    for node in nodes:
        assert tree.wrap(node._raw) is node
        if node.parent is not None:
            assert node in node.parent.children
        for field in (
            parse._NodeKind.NAME,
            parse._NodeKind.LEFT,
            parse._NodeKind.RIGHT,
            parse._NodeKind.VALUE,
        ):
            raw_child = node._raw.child_by_field_name(field.value)
            child = node.child_by_field_name(field)
            assert (child is None) == (raw_child is None)
            if raw_child is not None:
                assert child is tree.wrap(raw_child)
    assert any(node.child_by_field_name(parse._NodeKind.LEFT) is not None for node in nodes)
    assert parse._Tree().wrap(raw) is not root
    tree.clear()
    assert not tree._nodes
    assert tree.wrap(raw) is not root


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("'simple'", "simple"),
        ('"double"', "double"),
        ("r'raw\\n'", "raw\\n"),
        ("R'raw\\n'", "raw\\n"),
        ("'''multi\nline'''", "multi\nline"),
        ("'\\n\\r\\t\\b\\f\\v'", "\n\r\t\b\f\v"),
        ("'\\x41\\u0042\\u{43}'", "ABC"),
        ("'\\\\\\'\\\"\\$'", "\\'\"$"),
        ("'$value'", None),
        ("r'$value'", None),
        ("'\\q'", None),
        ("'\\x4'", None),
        ("'\\u123'", None),
        ("'\\u{}'", None),
        ("'\\u{110000}'", None),
        ("'''unclosed'", None),
        ("'trailing\\'", None),
    ],
)
def test_dart_string_decoder_preserves_delimiters_escape_grammar_and_rejections(raw, expected):
    assert parse._decode_dart_string(raw) == expected


def test_parse_compatibility_exports_are_the_canonical_syntax_types():
    from archkeel.analyzer.dart import syntax

    for name in (
        "Span",
        "Parameter",
        "Member",
        "Definition",
        "Directive",
        "Site",
        "Concern",
        "Syntax",
    ):
        assert getattr(parse, name) is getattr(syntax, name)


def test_own_dart_module_guards_are_proven_from_actual_source(self_observation):
    assessments = {row.id: row for row in rule_assessments(self_observation, undecided_by_rule={})}
    for identifier, _ in GUARDS:
        row = assessments[identifier]
        assert row.status == "PASS" and row.evaluation_proven, row
    assert not [
        row
        for row in self_observation.records("constructs")
        if row.data.get("construct") == "string_literal_compare"
        and any(
            str(row.data.get("owner", "")) == module
            or str(row.data.get("owner", "")).startswith(module + ".")
            for _, module in GUARDS
        )
    ]


def test_native_dart_enum_identity_cannot_be_replaced_by_a_string_alias(tmp_path):
    root, config = _repository(tmp_path)
    path = root / "archkeel/analyzer/dart/syntax.py"
    source = path.read_text()
    original = 'class ParameterKind(StrEnum):\n    POSITIONAL = "positional"\n    NAMED = "named"'
    assert original in source
    path.write_text(source.replace(original, "ParameterKind = str", 1))
    before = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and comparison.status == "FAIL"
    assert any(
        row.status == "FAIL" and row.subject_id == "archkeel.analyzer.dart.syntax.ParameterKind"
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == before


def test_dart_parser_produces_nominal_values_at_the_syntax_boundary():
    result = parse.parse(
        b"import 'other.dart' show Other; "
        b"class Service { final int value; Service(this.value); int run(int x) => x; }"
    )
    assert result.directives and result.definitions and result.sites
    assert all(isinstance(item.kind, parse.DirectiveKind) for item in result.directives)
    assert all(
        isinstance(mode, parse.Combinator)
        for directive in result.directives
        for mode, _ in directive.combinators
    )
    for definition in result.definitions:
        assert isinstance(definition.kind, parse.DefinitionKind)
        assert isinstance(definition.visibility, parse.Visibility)
        for member in definition.members:
            assert isinstance(member.kind, parse.MemberKind)
            assert isinstance(member.visibility, parse.Visibility)
            assert all(isinstance(item.kind, parse.ParameterKind) for item in member.parameters)
    assert all(isinstance(item.kind, parse.SiteKind) for item in result.sites)
    assert all(isinstance(item.use, parse.SiteUse) for item in result.sites)


def test_resolver_owns_builtin_classification_for_sdk_local_and_external_targets():
    snap = snapshot.Snapshot(
        sources=(
            snapshot.Source("lib/main.dart", "sample.main", b""),
            snapshot.Source("lib/other.dart", "sample.other", b""),
        ),
        package_name="sample",
        sdk_constraint=">=3.0.0 <4.0.0",
        sdk_constraint_state=snapshot.RuntimeRequirementState.DECLARED,
        inputs=(),
        problems=(),
        roots=("lib",),
    )
    resolver = resolve.Resolver(snap, {})
    for uri, expected in (
        ("dart:async", True),
        ("package:other/api.dart", False),
        ("package:sample/other.dart", False),
        ("other.dart", False),
    ):
        target = resolver.resolve_uri("lib/main.dart", uri)
        assert target is not None and target.builtin is expected
        assert target.uri == uri


@pytest.mark.parametrize("value", ["mixin", "class", "protocol", "enum", None, "foreign", 1, []])
def test_collector_decodes_only_its_owned_class_fact_vocabulary(value):
    result = collect._class_kind(value)
    if isinstance(value, str) and value in {item.value for item in collect._ClassKind}:
        assert isinstance(result, collect._ClassKind)
        assert str(result) == value
    else:
        assert result is None


@pytest.mark.parametrize("fails", [False, True])
def test_parse_releases_its_node_cache_on_success_and_failure(monkeypatch, fails):
    cleared = []
    clear = parse._Tree.clear

    def remember_clear(tree):
        assert tree._nodes
        clear(tree)
        cleared.append(tree)

    def fail_parse(*_args):
        raise RuntimeError("injected extraction failure")

    monkeypatch.setattr(parse._Tree, "clear", remember_clear)
    if fails:
        monkeypatch.setattr(parse, "_parse_tree", fail_parse)
        with pytest.raises(RuntimeError, match="injected extraction failure"):
            parse.parse(b"class Example {}")
    else:
        assert parse.parse(b"class Example {}").definitions
    assert len(cleared) == 1 and not cleared[0]._nodes


def test_resolver_outcomes_exclude_collector_only_partial_evidence_status():
    assert set(resolve.ResolutionStatus) == {
        resolve.ResolutionStatus.RESOLVED,
        resolve.ResolutionStatus.UNKNOWN,
        resolve.ResolutionStatus.UNRESOLVED,
    }
    for status in resolve.ResolutionStatus:
        resolution = resolve.ConstructionResolution(status, None, None)
        record, outcome = collect._Collection._construction_record(resolution)
        assert isinstance(outcome, collect._FactStatus)
        assert outcome is collect._FactStatus.UNRESOLVED
        assert record["status"] is outcome
    assert not isinstance(collect._FactStatus.PARTIALLY_RESOLVED, resolve.ResolutionStatus)


def test_parser_keywords_do_not_misclassify_identifier_substrings():
    result = parse.parse(
        b"class Probe { int staticValue=1; int finalize=2; int constellation=3; "
        b"int translate=4; static const actual=5; late final int delayed; "
        b"void method({required int count, int requiredValue=0}) {} }"
    )
    members = {member.name: member for member in result.definitions[0].members}
    for name in ("staticValue", "finalize", "constellation", "translate"):
        member = members[name]
        assert not any((member.static, member.constant, member.final, member.late))
    assert members["actual"].static and members["actual"].constant
    assert members["delayed"].final and members["delayed"].late
    count, required_value = members["method"].parameters
    assert count.required and not required_value.required


@pytest.mark.parametrize("widened", [False, True])
def test_native_visibility_ingress_return_matches_fixed_authored_intent(tmp_path, widened):
    root, config = _repository(tmp_path)
    path = root / "archkeel/analyzer/dart/syntax.py"
    source = path.read_text()
    narrow = "def from_name(cls, name: str) -> Visibility:"
    assert narrow in source
    if widened:
        source = source.replace(narrow, "def from_name(cls, name: str) -> str:", 1)
        path.write_text(source)
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    selected = [
        row
        for row in comparison.assessments
        if row.subject_id == "archkeel.analyzer.dart.syntax.Visibility.from_name"
        and row.aspect == "signature"
    ]
    assert len(selected) == 1 and selected[0].status == ("FAIL" if widened else "PASS"), selected
    if widened:
        assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == intent
