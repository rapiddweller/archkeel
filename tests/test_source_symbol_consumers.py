# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source selectors use the shared vocabulary while wire and graph roles stay distinct."""

import ast
import json
from importlib import import_module
from pathlib import Path

import pytest
from test_analyzer import _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.dart.collect import collect as collect_dart
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.analyzer.typescript.collect import collect as collect_typescript
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import SourceSectionName, SourceSymbolKind
from archkeel.ir.protocol import (
    CollectionRequest,
    DartSettings,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/source-symbol-consumers.md"
FILES = (
    "check/evaluation/boundary_types.py",
    "check/evaluation/rules.py",
    "check/evaluation/state.py",
    "ir/facts_validation.py",
    "ir/interfaces.py",
    "ir/references.py",
    "ir/source_graph.py",
    "analyzer/python/resolve.py",
    "analyzer/python/typing_signals.py",
)
GUARDS = {
    "SOURCE-SYMBOL-PUBLIC-API-CONTROL": (
        "check", "check/evaluation/boundary_types.py", "_public_api_positions"
    ),
    "SOURCE-SYMBOL-REFERENCE-CONTROL": (
        "ir", "ir/references.py", "unreferenced_symbols"
    ),
    "SOURCE-SYMBOL-BASE-CONTROL": (
        "python", "analyzer/python/symbols.py", "_record_class_bases"
    ),
}


def test_actual_source_selectors_do_not_dispatch_on_untyped_known_tag_literals():
    """The forbidden regression is raw source-tag dispatch, never JSON field access."""
    tags = {kind.value for kind in SourceSymbolKind}
    failures = []
    for relative in FILES:
        tree = ast.parse((ROOT / "src/archkeel" / relative).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            literals = {
                child.value
                for operand in operands
                for child in ast.walk(operand)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            }
            if not tags.intersection(literals):
                continue
            expressions = [ast.unparse(operand) for operand in operands]
            source_field = any(
                field in expression
                for field in ("['kind']", "['record_kind']", "['symbol_category']",
                              ".kind", ".get('record_kind')", ".get('symbol_category')")
                for expression in expressions
            )
            if source_field:
                failures.append(f"{relative}:{node.lineno}: {ast.unparse(node)}")
    assert not failures, "\n".join(failures)


def test_actual_python_definition_writer_publishes_nominal_source_tags():
    module = _parsed_module(
        "class Example:\n def run(self): pass\ndef build(): pass\n"
    )
    rows, _, _ = collect_symbols([module], {})
    assert {row["kind"] for row in rows} == {
        SourceSymbolKind.CLASS, SourceSymbolKind.METHOD, SourceSymbolKind.FUNCTION
    }
    assert all(type(row["kind"]) is SourceSymbolKind for row in rows)
    assert all(type(row["data"]["symbol_category"]) is SourceSymbolKind for row in rows)


@pytest.mark.parametrize("language", ("dart", "typescript"))
def test_actual_language_writer_projects_parser_tags_at_the_source_boundary(tmp_path, language, monkeypatch):
    module = import_module(f"archkeel.analyzer.{language}.collect")
    original = module.classified
    published = {}

    def capture(**kwargs):
        record = original(**kwargs)
        published[record["id"]] = record
        return record

    monkeypatch.setattr(module, "classified", capture)
    if language == "dart":
        (tmp_path / "pubspec.yaml").write_text(
            "name: sample\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n"
        )
        source = tmp_path / "lib/main.dart"
        source.parent.mkdir()
        source.write_text(
            "typedef Label = String;\nclass Example { String run() => ''; }\n"
            "String build() => '';\n"
        )
        settings, scope, collect = DartSettings(), ("lib",), collect_dart
    else:
        (tmp_path / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {"module": "CommonJS", "moduleResolution": "Node"},
            "include": ["src"],
        }))
        source = tmp_path / "src/main.ts"
        source.parent.mkdir()
        source.write_text(
            "export type Label = string;\nexport class Example { run(): string { return ''; } }\n"
            "export function build(): string { return ''; }\n"
        )
        settings, scope, collect = TypeScriptSettings(), ("src",), collect_typescript
    facts = collect(CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False), SourceScope(scope, "sample"), settings
    ))
    rows = [
        row for section in facts.sections if section.name is SourceSectionName.SYMBOLS
        for row in section.records
    ]
    assert len(rows) == 4
    actual = [published[row.id] for row in rows]
    assert all(type(row["kind"]) is SourceSymbolKind for row in actual)
    assert all(type(row["data"]["symbol_category"]) is SourceSymbolKind for row in actual)
    assert all(type(row.kind) is str for row in rows)
    assert all(type(row.data.get("symbol_category")) is str for row in rows)
    alias = next(row for row in actual if row["data"]["name"] == "Label")
    assert alias["kind"] is (
        SourceSymbolKind.ALIAS if language == "dart" else SourceSymbolKind.TYPE_ALIAS
    )
    assert alias["data"]["symbol_category"] is SourceSymbolKind.TYPE_ALIAS


def _native(tmp_path, guard):
    contract_owner, relative, function = GUARDS[guard]
    contract = json.loads(
        (ROOT / f"docs/architecture/contracts/{contract_owner}.json").read_text()
    )
    selected = [rule for rule in contract["rules"] if rule["id"] == guard]
    assert len(selected) == 1
    path = "archkeel/" + relative
    target = {
        "schema_version": contract["schema_version"],
        "components": [{
            "id": "source", "label": "source", "role": "component", "packages": ["archkeel"],
            "responsibilities": ["Select known source symbol tags through the Facts owner."],
            "forbidden_responsibilities": [], "provenance": [DOC], "public": ["archkeel"],
        }],
        "rules": selected,
    }
    root = _prepare_repo(tmp_path, {
        path: (ROOT / "src" / path).read_text(),
        "archkeel/__init__.py": "",
        "contract.json": json.dumps(target),
        DOC: (ROOT / DOC).read_text(),
    })
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64), path, function


@pytest.mark.parametrize("guard", GUARDS)
def test_native_actual_consumer_satisfies_its_authored_control_guard(tmp_path, guard):
    root, config, _, _ = _native(tmp_path, guard)
    observed = _model(root, config)
    rows = [row for row in rule_assessments(observed, undecided_by_rule={}) if row.id == guard]
    assert len(rows) == 1 and rows[0].status == "PASS" and rows[0].evaluation_proven
    assert not trace_valid_violations(observed)


@pytest.mark.parametrize("guard", GUARDS)
def test_native_raw_source_dispatch_mutation_fails_unchanged_consumer_intent(tmp_path, guard):
    root, config, relative, function = _native(tmp_path, guard)
    path = root / relative
    text = path.read_text()
    node = next(
        node for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef) and node.name == function
    )
    lines = text.splitlines(keepends=True)
    lines.insert(node.body[0].lineno - 1, '    if future_tag == "class":\n        return None\n')
    path.write_text("".join(lines))
    before = (root / "contract.json").read_bytes()
    observed = _model(root, config)
    assert any(guard in row.rule_ids for row in trace_valid_violations(observed))
    assert (root / "contract.json").read_bytes() == before
