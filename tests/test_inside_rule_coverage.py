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


def test_inner_edge_without_complete_requires_is_observed_not_conforming(
    tmp_path: Path,
) -> None:
    _write_inside_case(tmp_path, rules=[])

    _result, edge = _inside_edge(tmp_path)

    assert edge.state in {"observed", "undecided"}
    assert edge.rule_ids == ()


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
