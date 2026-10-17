# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared context kinds and the real Source frame are independently typed ports."""

import ast
import json
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer.python import source
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir import architecture_graph as graph
from archkeel.ir import facts
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
KINDS = ("if", "for", "async_for", "while", "try", "try_star", "with", "async_with", "match")
BRANCHES = ("body", "else", "handler", "finally", "case")


def _owned(name):
    owned = getattr(facts, name, None)
    assert owned is not None, "the existing facts owner must define the shared vocabulary"
    assert issubclass(owned, StrEnum)
    assert owned.__module__ == facts.__name__
    assert getattr(graph, name) is owned
    return owned


@pytest.mark.parametrize(
    "name,spellings",
    [("DefinitionContextKind", KINDS), ("DefinitionBranchKind", BRANCHES)],
)
def test_graph_reexports_the_one_facts_vocabulary_without_changing_members(name, spellings):
    assert tuple(str(item) for item in _owned(name)) == spellings


def _frame():
    frame = getattr(source, "DefinitionFrame", None)
    assert frame is not None, "Source must own its AST frame independently of Graph evidence"
    return frame


def test_frame_fields_and_branch_producer_expose_the_real_nominal_port():
    frame = _frame()
    assert get_type_hints(frame) == {
        "node": ast.AST,
        "kind": _owned("DefinitionContextKind"),
        "branch": _owned("DefinitionBranchKind"),
    }
    assert get_type_hints(source._branch_context)["return"] is frame
    assert frame is not graph.DefinitionContext


def test_generated_frame_keeps_the_immutable_tuple_protocol():
    tree = ast.parse("if flag:\n def run(): pass\n")
    [(_, _, (frame,))] = list(source.definition_sites(tree))
    assert isinstance(frame, _frame())
    assert frame == (tree.body[0], "if", "body")
    assert tuple(frame) == (tree.body[0], "if", "body")
    assert frame[0] is frame.node
    assert hash(frame) == hash(tuple(frame))
    assert not hasattr(frame, "__dict__")
    with pytest.raises(AttributeError):
        frame.kind = "for"


@pytest.mark.parametrize("as_keyword", [False, True])
def test_public_definition_entry_accepts_valid_old_tuple_string_prefix_once(as_keyword):
    prefix = ast.parse("if prefix: pass").body[0]
    tree = ast.parse("try:\n def run(): pass\nfinally: pass\n")
    legacy = ((prefix, "if", "body"),)
    actual = (
        list(source.definition_sites(tree, contexts=legacy))
        if as_keyword
        else list(source.definition_sites(tree, None, legacy))
    )
    [(_, _, frames)] = actual
    assert len(frames) == 2
    assert all(isinstance(frame, _frame()) for frame in frames)
    assert frames[0].node is prefix
    assert frames[0].kind is _owned("DefinitionContextKind").IF
    assert frames[0].branch is _owned("DefinitionBranchKind").BODY
    assert frames[1].kind is _owned("DefinitionContextKind").TRY


@pytest.mark.parametrize(
    "written,kind,branch",
    [
        ("if flag: pass\nelse:\n def run(): pass\n", "if", "else"),
        ("try: pass\nexcept Exception:\n def run(): pass\n", "try", "handler"),
        ("try: pass\nfinally:\n def run(): pass\n", "try", "finally"),
        ("match value:\n case 1:\n  def run(): pass\n", "match", "case"),
        ("for item in items:\n def run(): pass\n", "for", "body"),
    ],
)
def test_both_ast_entry_points_produce_the_same_nominal_frame(written, kind, branch):
    tree = ast.parse(written)
    [(definition, _, (frame,))] = list(source.definition_sites(tree))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    assert source.control_flow_contexts(definition, parents) == (frame,)
    assert isinstance(frame, _frame())
    assert frame.kind is _owned("DefinitionContextKind")(kind)
    assert frame.branch is _owned("DefinitionBranchKind")(branch)


def test_unknown_future_ast_field_does_not_invent_a_known_branch():
    class Future(ast.AST):
        _fields = ("future_body",)

    tree = Future()
    tree.future_body = [ast.parse("def hidden(): pass").body[0]]
    assert list(source.definition_sites(tree)) == []


def _entities(kind_annotation="DefinitionContextKind"):
    common = dict(language="python", presence="planned", provenance=["context-intent.md"])
    return [
        dict(common, id="SOURCE", kind="module", qualified_name="archkeel.analyzer.python.source"),
        dict(
            common, id="FRAME", kind="class",
            qualified_name="archkeel.analyzer.python.source.DefinitionFrame", parent_id="SOURCE",
        ),
        *[
            dict(
                common, id="FRAME-" + name, kind="attribute",
                qualified_name="archkeel.analyzer.python.source.DefinitionFrame." + name,
                parent_id="FRAME", annotation=annotation,
            )
            for name, annotation in (
                ("node", "ast.AST"), ("kind", kind_annotation),
                ("branch", "DefinitionBranchKind"),
            )
        ],
        dict(
            common, id="BRANCH", kind="function",
            qualified_name="archkeel.analyzer.python.source._branch_context", parent_id="SOURCE",
            visibility=dict(kind="private", basis="declared"),
            signature=dict(
                parameters=[
                    dict(name="node", annotation="ast.AST", kind="positional", default_known=True),
                    dict(name="child", annotation="ast.AST", kind="positional", default_known=True),
                    dict(
                        name="field_name", annotation="_DefinitionField",
                        kind="positional", default_known=True,
                    ),
                ],
                returns="DefinitionFrame",
            ),
        ),
    ]


def _repository(tmp_path, text):
    target = dict(
        schema_version="2.2.0", components=[], rules=[],
        declarations=dict(uml=dict(entities=_entities(), relationships=[], scopes=[])),
    )
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "archkeel/analyzer/python/source.py": text,
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/facts.py": (ROOT / "src/archkeel/ir/facts.py").read_text(),
        "contract.json": json.dumps(target),
        "context-intent.md": "The Source-owned AST frame and branch-producing port.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, [
        item.unknown_claim for item in result.diagnostics
    ]
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _comparison(model):
    comparison = architecture_report(model).comparison
    assert comparison is not None
    return comparison


PROBE = """import ast
from enum import StrEnum
from typing import NamedTuple

class DefinitionContextKind(StrEnum):
    IF = "if"

class DefinitionBranchKind(StrEnum):
    BODY = "body"

class _DefinitionField(StrEnum):
    BODY = "body"

class DefinitionFrame(NamedTuple):
    node: ast.AST
    kind: DefinitionContextKind
    branch: DefinitionBranchKind

def _branch_context(node: ast.AST, child: ast.AST, field_name: _DefinitionField) -> DefinitionFrame:
    return DefinitionFrame(node, DefinitionContextKind.IF, DefinitionBranchKind.BODY)
"""


@pytest.mark.parametrize(
    "old,new",
    [
        ("kind: DefinitionContextKind", "kind: str"),
        ("branch: DefinitionBranchKind", "branch: str"),
        ("-> DefinitionFrame:", "-> tuple[ast.AST, str, str]:"),
    ],
)
def test_native_named_tuple_probe_rejects_real_field_and_return_widening(tmp_path, old, new):
    root, config = _repository(tmp_path, PROBE)
    assert _comparison(_model(root, config)).status == "PASS"
    actual = root / "archkeel/analyzer/python/source.py"
    target = (root / "contract.json").read_bytes()
    actual.write_text(PROBE.replace(old, new, 1))
    observed = _model(root, config)
    assert any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in _comparison(observed).assessments
    )
    assert trace_valid_violations(observed)
    assert (root / "contract.json").read_bytes() == target


def test_native_real_source_frame_matches_the_independent_target(tmp_path):
    text = (ROOT / "src/archkeel/analyzer/python/source.py").read_text()
    root, config = _repository(tmp_path, text)
    comparison = _comparison(_model(root, config))
    assert comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status) for row in comparison.assessments
        if row.status != "PASS"
    ]


@pytest.mark.parametrize(
    "old,new",
    [
        ("kind: DefinitionContextKind", "kind: str"),
        ("branch: DefinitionBranchKind", "branch: str"),
        ("-> DefinitionFrame:", "-> tuple[ast.AST, str, str]:"),
    ],
)
def test_native_actual_frame_widening_fails_unchanged_authored_port(tmp_path, old, new):
    text = (ROOT / "src/archkeel/analyzer/python/source.py").read_text()
    assert old in text, "the actual nominal field/return must exist before mutation"
    root, config = _repository(tmp_path, text.replace(old, new, 1))
    observed = _model(root, config)
    assert any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in _comparison(observed).assessments
    )
    assert trace_valid_violations(observed)
