# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inside declarations must be evaluated, or must not claim conformance."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe
from test_architecture_demo import FIXTURE_DIR, _prepare_repo

from archkeel.cli import main
from archkeel.ir.trace import trace_valid_violations, validate_evidence_classes
from archkeel.render.flow import build_flow


def _write_inside_case(
    root: Path,
    *,
    rules: list[dict[str, object]],
    b_requires: list[str] | None = None,
    eval_in_a: bool = False,
) -> None:
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("core") | {"inside": "inner.json"}],
                "rules": [],
            }
        )
    )
    (root / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _inside_component("a", ["b"]),
                    _inside_component("b", b_requires or []),
                ],
                "rules": rules,
            }
        )
    )
    package = root / "sample/core"
    package.mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "a.py").write_text('VALUE = eval("1")\n' if eval_in_a else "VALUE = 1\n")
    (package / "b.py").write_text("import sample.core.a\n")


def _inside_edge(root: Path):
    result = _observe(root)
    assert result.observation is not None
    flow = build_flow(result.observation)
    core = next(item for item in flow.components if item.label == "core")
    assert core.inside is not None
    return result, next(
        edge for edge in core.inside.edges if (edge.source, edge.target) == ("b", "a")
    )


@pytest.mark.parametrize(
    ("rule", "kind", "subjects"),
    [
        (
            {
                "kind": "external_dependency_scope",
                "dependency": "json",
                "allowed_sources": ["sample.core.b"],
            },
            "external_dependency_scope",
            {"sample.core.a", "json"},
        ),
        (
            {"kind": "complete_assignment", "source": "sample.core"},
            "complete_assignment",
            {"sample.core.orphan"},
        ),
        (
            {"kind": "no_component_cycles", "level": "module"},
            "module_cycle",
            {"sample.core.a", "sample.foreign.x"},
        ),
    ],
)
def test_inside_scope_keeps_parent_orphans_and_global_targets_but_not_foreign_sources(
    tmp_path: Path, rule: dict[str, object], kind: str, subjects: set[str]
) -> None:
    _write_inside_case(
        tmp_path,
        rules=[
            {
                "id": "SCOPED",
                "rationale": "Judge this parent with complete global target evidence.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **rule,
            }
        ],
    )
    path = tmp_path / "contract.json"
    contract = json.loads(path.read_bytes())
    contract["components"].append(_component("foreign"))
    path.write_text(json.dumps(contract))
    foreign = tmp_path / "sample/foreign"
    foreign.mkdir()
    (foreign / "__init__.py").write_text("")
    (foreign / "x.py").write_text("import json\nimport sample.core.a\n")
    (foreign / "y.py").write_text("import sample.foreign.z\n")
    (foreign / "z.py").write_text("import sample.foreign.y\n")
    (tmp_path / "sample/core/a.py").write_text("import json\nimport sample.foreign.x\n")
    (tmp_path / "sample/core/b.py").write_text("import json\n")
    (tmp_path / "sample/core/orphan.py").write_text("VALUE = 1\n")

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 1
    assert findings[0].kind == kind
    assert set(findings[0].subjects) == subjects
    assert findings[0].rule_ids == ("core:SCOPED",)
    if kind == "module_cycle":
        imports = {record.id: record for record in result.observation.records("imports") or ()}
        closing = [imports[item_id] for item_id in findings[0].fact_ids]
        assert {
            (record.data.get("source_module"), record.data.get("target_module"))
            for record in closing
        } == {
            ("sample.core.a", "sample.foreign.x"),
            ("sample.foreign.x", "sample.core.a"),
        }
        assert set(findings[0].evidence_ids) == {
            evidence for record in closing for evidence in record.evidence_ids
        }


def test_inside_forbidden_construct_is_evaluated_or_explicitly_refused(tmp_path: Path) -> None:
    _write_inside_case(
        tmp_path,
        eval_in_a=True,
        rules=[
            {
                "id": "NO-EVAL",
                "kind": "forbidden_construct",
                "source": "sample.core.a",
                "constructs": ["eval"],
                "rationale": "Keep dynamic evaluation out of the inner component.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )

    result = _observe(tmp_path)
    if any(item.kind == "rule_unsupported_by_profile" for item in result.diagnostics):
        return
    assert result.observation is not None
    violations = tuple(
        item
        for item in result.observation.records("violations") or ()
        if item.rule_ids == ("core:NO-EVAL",)
    )
    assert violations, "inside NO-EVAL was silently reported as clean"


def test_inside_namespace_finding_references_its_scoped_component(tmp_path: Path) -> None:
    _write_inside_case(tmp_path, rules=[])
    path = tmp_path / "inner.json"
    inner = json.loads(path.read_bytes())
    inner["components"][0]["packages"].append("sample.core.extra")
    inner["components"][0]["namespace"] = "sample.core.a"
    path.write_text(json.dumps(inner))
    (tmp_path / "sample/core/extra.py").write_text("VALUE = 1\n")

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    validate_evidence_classes(observation)
    findings = [
        record
        for record in observation.records("violations") or ()
        if record.kind == "module.placement"
    ]
    assert len(findings) == 1
    declaration_id = f"core:{inner['components'][0]['id']}"
    assert findings[0].rule_ids == (declaration_id,)
    assert any(record.id == declaration_id for record in observation.records("declarations") or ())
    assert tuple(findings) == trace_valid_violations(observation)


def test_inner_edge_without_complete_requires_is_observed_not_conforming(
    tmp_path: Path,
) -> None:
    _write_inside_case(tmp_path, rules=[])

    _result, edge = _inside_edge(tmp_path)

    assert edge.state in {"observed", "undecided"}
    assert edge.rule_ids == ()


def test_inner_type_checking_edge_excluded_by_rule_is_not_called_checked(tmp_path: Path) -> None:
    _write_inside_case(
        tmp_path,
        rules=[
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "include_type_checking": False,
                "rationale": "Check runtime imports only.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    (tmp_path / "sample/core/b.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sample.core.a\n"
    )
    result, edge = _inside_edge(tmp_path)
    assert result.observation is not None
    assert not result.observation.records("violations")
    assert edge.state in {"observed", "undecided"}


def test_inner_unknown_keeps_another_proven_violation(tmp_path: Path) -> None:
    metadata = {
        "rationale": "Preserve independent verdicts.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    _write_inside_case(
        tmp_path,
        rules=[
            {**metadata, "id": "REQUIRES-COMPLETE", "kind": "complete_requires"},
            {**metadata, "id": "TYPES", "kind": "boundary_types", "source": "sample.core.a"},
        ],
    )
    result, edge = _inside_edge(tmp_path)
    assert result.observation is not None
    assert edge.state == "violation"
    assert any(
        record.rule_ids == ("core:REQUIRES-COMPLETE",)
        for record in result.observation.records("violations") or ()
    )
    assert any(
        record.rule_ids == ("core:TYPES",)
        for record in result.observation.records("unknowns") or ()
    )


def test_inside_complete_requires_violation_control(tmp_path: Path) -> None:
    _write_inside_case(
        tmp_path,
        rules=[
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "Declare every inner dependency.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )

    result, edge = _inside_edge(tmp_path)

    assert result.observation is not None
    assert edge.state == "violation"
    assert edge.rule_ids == ("core:REQUIRES-COMPLETE",)
    assert any(
        item.kind == "complete_requires" and item.rule_ids == edge.rule_ids
        for item in result.observation.records("violations") or ()
    )


def test_inside_complete_requires_satisfied_control(tmp_path: Path) -> None:
    _write_inside_case(
        tmp_path,
        b_requires=["a"],
        rules=[
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "Declare every inner dependency.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )

    result, edge = _inside_edge(tmp_path)

    assert result.observation is not None
    assert not any(
        item.kind == "complete_requires" for item in result.observation.records("violations") or ()
    )
    assert edge.state == "conforms"
    assert edge.rule_ids == ()


def test_same_label_sibling_inside_levels_keep_findings_scoped(tmp_path: Path) -> None:
    rule = {
        "id": "REQUIRES-COMPLETE",
        "kind": "complete_requires",
        "rationale": "Declare every inner dependency.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    components = []
    for parent in ("core", "service"):
        components.append(_component(parent) | {"inside": f"{parent}-inner.json"})
        inner_components = [
            _inside_component("a", ["b"]) | {"packages": [f"sample.{parent}.a"]},
            _inside_component("b", ["a"] if parent == "service" else [])
            | {"packages": [f"sample.{parent}.b"]},
        ]
        (tmp_path / f"{parent}-inner.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": inner_components,
                    "rules": [rule],
                }
            )
        )
        package = tmp_path / f"sample/{parent}"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "a.py").write_text("VALUE = 1\n")
        (package / "b.py").write_text(f"import sample.{parent}.a\n")
    (tmp_path / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": []})
    )
    (tmp_path / "sample/__init__.py").write_text("")

    result = _observe(tmp_path)
    assert result.observation is not None
    flow = build_flow(result.observation)
    inside_by_parent = {
        component.label: component.inside
        for component in flow.components
        if component.label in {"core", "service"}
    }
    core_edge = next(
        edge for edge in inside_by_parent["core"].edges if (edge.source, edge.target) == ("b", "a")
    )
    service_edge = next(
        edge
        for edge in inside_by_parent["service"].edges
        if (edge.source, edge.target) == ("b", "a")
    )

    assert core_edge.state == "violation"
    assert core_edge.rule_ids == ("core:REQUIRES-COMPLETE",)
    assert service_edge.state == "conforms", (
        service_edge,
        [item for item in result.observation.records("violations") or ()],
    )
    assert service_edge.rule_ids == ()
    assert [
        item.rule_ids
        for item in result.observation.records("violations") or ()
        if item.kind == "complete_requires"
    ] == [("core:REQUIRES-COMPLETE",)]


@pytest.mark.parametrize("command", ["report", "validate"])
def test_cli_never_reports_pass_for_an_unevaluated_inside_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    contract["rules"] = [rule for rule in contract["rules"] if rule["id"] != "CONSTRUCT-NO-DYNAMIC"]
    inside_path = "shop/store/architecture-contract.json"
    inner = json.loads((FIXTURE_DIR / inside_path).read_text())
    inner["rules"].append(
        {
            "id": "NO-INNER-EVAL",
            "kind": "forbidden_construct",
            "source": "shop.store.codec",
            "constructs": ["eval"],
            "rationale": "The codec must not evaluate source text.",
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    )
    codec_path = "shop/store/codec.py"
    root = _prepare_repo(
        tmp_path,
        {
            "architecture-contract.json": json.dumps(contract),
            inside_path: json.dumps(inner),
            codec_path: (FIXTURE_DIR / codec_path).read_text() + '\neval("1")\n',
        },
    )

    args = [command, "--root", str(root), "--json"]
    if command == "report":
        args.extend(["--output", str(tmp_path / "result.json")])
    code = main(args)
    payload = json.loads(capsys.readouterr().out)

    if code == 2:
        assert any(
            diagnostic["kind"] == "rule_unsupported_by_profile"
            and "NO-INNER-EVAL" in diagnostic["subject"]
            for diagnostic in payload["diagnostics"]
        ), payload["diagnostics"]
    else:
        assert payload["declared_rules"] == "FAIL", payload
        assert "store:NO-INNER-EVAL" in json.dumps(payload["violations_by_rule"])
