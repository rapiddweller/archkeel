# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inside declarations must be evaluated, or must not claim conformance."""

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe
from test_architecture_demo import FIXTURE_DIR, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import inside_diagnostics
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, parse_contract, parse_observation
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


def _scan_config(root: Path, *, language: str = "python", source: str = "sample") -> None:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        f'[scan]\nroots = ["{source}"]\nnamespace = "sample"\n'
        f'contract = "contract.json"\nlanguage = "{language}"\n'
    )


def _commit_test_root(root: Path) -> None:
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "demo@example.invalid"],
        ["git", "config", "user.name", "Demo"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)


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


def test_inside_component_cannot_claim_packages_outside_its_parent(tmp_path: Path) -> None:
    _write_inside_case(tmp_path, rules=[])
    path = tmp_path / "inner.json"
    inner = json.loads(path.read_bytes())
    inner["components"][0]["packages"] = ["sample.foreign"]
    path.write_text(json.dumps(inner))

    outer = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = inside_diagnostics(tmp_path, outer)

    assert any(
        item.pointer == "/components/0/inside" and "sample.foreign" in item.unknown_claim
        for item in diagnostics
    ), diagnostics


def test_out_of_parent_inside_is_unknown_in_report_not_a_foreign_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_inside_case(
        tmp_path,
        b_requires=["a"],
        rules=[
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "Do not judge code outside the parent component.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    outer_path = tmp_path / "contract.json"
    outer = json.loads(outer_path.read_bytes())
    outer["components"].append(_component("foreign"))
    outer_path.write_text(json.dumps(outer))
    inside_path = tmp_path / "inner.json"
    inside = json.loads(inside_path.read_bytes())
    inside["components"][0]["packages"] = ["sample.foreign"]
    inside_path.write_text(json.dumps(inside))
    foreign = tmp_path / "sample/foreign"
    foreign.mkdir()
    (foreign / "__init__.py").write_text("")
    (foreign / "x.py").write_text("import sample.core.b\n")
    _scan_config(tmp_path)
    _commit_test_root(tmp_path)

    artifact_path = tmp_path / "architecture.json"
    exit_code = main(["report", "--root", str(tmp_path), "--output", str(artifact_path), "--json"])
    result = json.loads(capsys.readouterr().out)
    observation = parse_observation(decode_canonical_model(json.loads(artifact_path.read_bytes())))
    foreign_violations = [
        item
        for item in trace_valid_violations(observation)
        if item.rule_ids == ("core:REQUIRES-COMPLETE",)
    ]
    assert (
        exit_code,
        result["declared_rules"],
        any("sample.foreign" in json.dumps(item) for item in result["diagnostics"]),
        len(foreign_violations),
    ) == (
        2,
        "UNKNOWN",
        True,
        0,
    )


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


def test_runtime_finding_does_not_attribute_excluded_type_checking_import(
    tmp_path: Path,
) -> None:
    _write_inside_case(
        tmp_path,
        rules=[
            {
                "id": "BLOCK-A",
                "kind": "forbidden_dependency",
                "source": "sample.core.b",
                "target": "sample.core.a",
                "include_type_checking": False,
                "rationale": "Decide runtime imports only.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    (tmp_path / "sample/core/b.py").write_text(
        "import sample.core.a\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    import sample.core.a\n"
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    imports = {
        item.id: item
        for item in result.observation.records("imports") or ()
        if item.data.get("source_module") == "sample.core.b"
        and item.data.get("target_module") == "sample.core.a"
    }
    runtime = {
        item_id for item_id, item in imports.items() if not item.data.get("under_type_checking")
    }
    type_checking = {
        item_id for item_id, item in imports.items() if item.data.get("under_type_checking")
    }
    violations = [
        item
        for item in trace_valid_violations(result.observation)
        if item.rule_ids == ("core:BLOCK-A",)
    ]
    assert len(runtime) == len(type_checking) == 1
    assert len(violations) == 1
    assert set(violations[0].fact_ids) == runtime


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


def test_dart_inside_keeps_supported_violation_with_unsupported_rule_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: sample\n")
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("core") | {"inside": "inner.json"}],
                "rules": [],
            }
        )
    )
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _inside_component("a", []),
                    _inside_component("b", []),
                ],
                "rules": [
                    {
                        "id": "BLOCK-IO",
                        "kind": "forbidden_dependency",
                        "source": "sample.core.a",
                        "target": "dart.io",
                        "rationale": "Keep I/O out of the core component.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    },
                    {
                        "id": "TYPES",
                        "kind": "boundary_types",
                        "source": "sample.core.a",
                        "rationale": "Keep the public boundary typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    },
                ],
            }
        )
    )
    (tmp_path / "lib/core").mkdir(parents=True)
    (tmp_path / "lib/core/a.dart").write_text("import 'dart:io';\n")
    (tmp_path / "lib/core/b.dart").write_text("")
    result = observe(
        tmp_path,
        roots=("lib",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
        language="dart",
    )

    assert result.observation is not None, result.diagnostics
    supported_violation = any(
        item.rule_ids == ("core:BLOCK-IO",) for item in trace_valid_violations(result.observation)
    )
    unsupported_unknown = any(
        item.kind == "rule-unsupported-by-profile" and item.rule_ids == ("core:TYPES",)
        for item in result.observation.records("unknowns") or ()
    )
    assert (supported_violation, unsupported_unknown) == (True, True)


def test_inside_facade_reexport_uses_global_origin_signature(tmp_path: Path) -> None:
    facade = "sample.core.api:run"
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("core", public=[facade]) | {"inside": "inner.json"},
                    _component("foreign"),
                ],
                "rules": [],
            }
        )
    )
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _inside_component("api", [])
                    | {"packages": ["sample.core.api"], "public": [facade]}
                ],
                "rules": [
                    {
                        "id": "API-TYPES",
                        "kind": "boundary_types",
                        "source": "sample.core.api",
                        "rationale": "Keep the inner public facade typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    for package in ("core", "foreign"):
        directory = tmp_path / f"sample/{package}"
        directory.mkdir(parents=True)
        (directory / "__init__.py").write_text("")
    (tmp_path / "sample/core/api.py").write_text(
        'from sample.foreign.impl import run\n__all__ = ["run"]\n'
    )
    (tmp_path / "sample/foreign/impl.py").write_text(
        "def run(payload: dict) -> str:\n    return str(payload)\n"
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    reexport = next(
        item
        for item in result.observation.records("imports") or ()
        if item.data.get("source_module") == "sample.core.api" and item.data.get("binding") == "run"
    )
    assert reexport.data.get("origin_definition") == "sample.foreign.impl.run"
    findings = [
        item
        for item in trace_valid_violations(result.observation)
        if item.rule_ids == ("core:API-TYPES",)
    ]
    assert [(item.kind, item.subjects) for item in findings] == [
        ("boundary_types", ("sample.core.api", "sample.core.api.run"))
    ]


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


def test_missing_inside_does_not_suppress_valid_sibling_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = {
        "id": "REQUIRES-COMPLETE",
        "kind": "complete_requires",
        "rationale": "Declare every inner dependency.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    components = [
        _component("core") | {"inside": "missing.json"},
        _component("service") | {"inside": "service-inner.json"},
    ]
    inner = {
        "schema_version": "2.1.0",
        "components": [
            _inside_component("a", []) | {"packages": ["sample.service.a"]},
            _inside_component("b", []) | {"packages": ["sample.service.b"]},
        ],
        "rules": [rule],
    }
    (tmp_path / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": []})
    )
    (tmp_path / "service-inner.json").write_text(json.dumps(inner))
    for module in ("core", "service"):
        package = tmp_path / f"sample/{module}"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
    (tmp_path / "sample/service/a.py").write_text("VALUE = 1\n")
    (tmp_path / "sample/service/b.py").write_text("import sample.service.a\n")

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert [
        item.rule_ids
        for item in trace_valid_violations(result.observation)
        if item.kind == "complete_requires"
    ] == [("service:REQUIRES-COMPLETE",)]

    outer = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    missing_diagnostics = inside_diagnostics(tmp_path, outer)
    assert any("missing.json" in item.subject for item in missing_diagnostics), missing_diagnostics
    _scan_config(tmp_path)
    _commit_test_root(tmp_path)
    artifact_path = tmp_path / "architecture.json"
    exit_code = main(["report", "--root", str(tmp_path), "--output", str(artifact_path), "--json"])
    report = json.loads(capsys.readouterr().out)
    report_observation = parse_observation(
        decode_canonical_model(json.loads(artifact_path.read_bytes()))
    )
    sibling_violations = [
        item
        for item in trace_valid_violations(report_observation)
        if item.rule_ids == ("service:REQUIRES-COMPLETE",)
    ]
    assert (
        exit_code,
        report["declared_rules"],
        any("missing.json" in item["subject"] for item in report["diagnostics"]),
        len(sibling_violations),
    ) == (
        2,
        "UNKNOWN",
        True,
        1,
    )


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
