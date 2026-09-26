# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent regressions for recursive Git identity and analyzer scope boundaries."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from test_analyzer import _component, _observe
from test_delta import _model
from test_expectation import _expectation_payload
from test_git_lock import _lock
from test_recursive_inside_independent_contracts import (
    _commit_tree,
    _contract,
    _scan_config,
    _write_three_levels,
)

from archkeel.analyzer import observe
from archkeel.check.run import _authenticate_inputs, materialize_declarations
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    _inside_contract_tree,
    _revision_contract_tree,
    run_validate,
)
from archkeel.ir.codec import parse_contract
from archkeel.ir.levels import inside_levels
from archkeel.ir.lock import LOCK_PATH, LockError
from archkeel.ir.model import ObservationResult, Record
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.flow import build_flow


def _component_at(
    label: str,
    package: str,
    *,
    public: list[str] | None = None,
    inside: str | None = None,
) -> dict[str, object]:
    value = _component(label, packages=[package], public=public or [])
    if inside is not None:
        value["inside"] = inside
    return value


def _forbidden_edge(identifier: str, source: str, target: str) -> dict[str, object]:
    return {
        "id": identifier,
        "kind": "forbidden_dependency",
        "source": source,
        "target": target,
        "include_type_checking": True,
        "rationale": "Keep this fixture boundary closed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }


def test_git_readers_normalize_duplicate_inside_mount_identities(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/inner.json").write_text(json.dumps(_contract([], [])))
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text("Architecture decision.\n")
    root = _contract(
        [
            _component_at("left", "sample.left", inside="contracts/inner.json"),
            _component_at("right", "sample.right", inside="./contracts/inner.json"),
        ],
        [],
    )
    root_path = tmp_path / "contract.json"
    root_path.write_text(json.dumps(root))
    contract = parse_contract(root)

    local = _inside_contract_tree(tmp_path, "contract.json", contract)
    assert local is not None
    assert any("duplicate mount" in issue.reason for issue in local.issues)

    symlink = tmp_path / "contracts/alias.json"
    symlink.symlink_to("inner.json")
    symlink_contract = _contract(
        [
            _component_at("left", "sample.left", inside="contracts/inner.json"),
            _component_at("right", "sample.right", inside="contracts/alias.json"),
        ],
        [],
    )
    symlink_tree = _inside_contract_tree(
        tmp_path, "contract.json", parse_contract(symlink_contract)
    )
    assert symlink_tree is not None
    assert any("duplicate mount" in issue.reason for issue in symlink_tree.issues)
    symlink.unlink()

    revision = _commit_tree(tmp_path)
    try:
        revision_tree = _revision_contract_tree(tmp_path, revision, "contract.json")
    except ValueError as error:
        duplicate_in_revision = "duplicate mount" in str(error)
    else:
        duplicate_in_revision = any(
            "duplicate mount" in issue.reason for issue in revision_tree.issues
        )

    destination = tmp_path / "declarations"
    try:
        materialize_declarations(
            tmp_path,
            revision,
            _scan_config(),
            destination,
        )
    except ValueError as error:
        snapshot_rejected = "duplicate mount" in str(error)
    else:
        snapshot_rejected = False

    inputs = {
        "contract.json": root_path.read_bytes(),
        "contracts/inner.json": (tmp_path / "contracts/inner.json").read_bytes(),
        "docs/architecture/sample.md": (tmp_path / "docs/architecture/sample.md").read_bytes(),
    }
    lock_bytes = _lock(_model(git_head="a" * 40))
    config = replace(_scan_config(), digest="b" * 64)
    expected = _expectation_payload()
    expected.update(accepted_digest=sha256(lock_bytes).hexdigest(), baseline_commit="b" * 40)
    expected_bytes = json.dumps(expected).encode()

    def read_blob(root: Path, commit: str, path: str) -> bytes:
        if path == LOCK_PATH:
            return lock_bytes
        if path == "expectation.json":
            return expected_bytes
        return inputs[path.removeprefix("./")]

    try:
        with (
            patch("archkeel.check.run.remote_tip", return_value="b" * 40),
            patch("archkeel.check.run.read_blob", side_effect=read_blob),
            patch("archkeel.check.run.parents", return_value=["a" * 40]),
            patch("archkeel.check.run.changed_paths", return_value={LOCK_PATH}),
            patch("archkeel.check.run.package_digest", return_value="c" * 64),
        ):
            _authenticate_inputs(
                tmp_path,
                config=config,
                baseline="b" * 40,
                expectation_commit="e" * 40,
                head="f" * 40,
                expected_path="expectation.json",
                expected_digest=sha256(expected_bytes).hexdigest(),
                accepted_branch="main",
            )
    except LockError as error:
        auth_rejected = "duplicate mount" in str(error)
        auth_error = str(error)
    else:
        auth_rejected = False
        auth_error = "no LockError"

    assert duplicate_in_revision, revision_tree.issues
    assert snapshot_rejected
    assert auth_rejected, auth_error
    assert not destination.exists()


def test_nested_scope_escape_stays_unknown_while_valid_sibling_is_evaluated(
    tmp_path: Path,
) -> None:
    _write_three_levels(tmp_path)
    contracts = tmp_path / "contracts"
    foreign_nested = "contracts/foreign.json"
    good_nested = "contracts/good.json"
    middle = _contract(
        [
            _component_at("foreign", "sample.foreign", inside=foreign_nested),
            _component_at("good", "sample.layer.good", inside=good_nested),
        ],
        [],
    )
    (contracts / "two.json").write_text(json.dumps(middle))
    (contracts / "foreign.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at("source", "sample.foreign.source"),
                    _component_at("target", "sample.foreign.target"),
                ],
                [
                    _forbidden_edge(
                        "FOREIGN-NO-EDGE", "sample.foreign.source", "sample.foreign.target"
                    )
                ],
            )
        )
    )
    (contracts / "good.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at("source", "sample.layer.good.source"),
                    _component_at("target", "sample.layer.good.target"),
                ],
                [
                    _forbidden_edge(
                        "GOOD-NO-EDGE",
                        "sample.layer.good.source",
                        "sample.layer.good.target",
                    )
                ],
            )
        )
    )
    for package in (
        "sample/foreign/source",
        "sample/foreign/target",
        "sample/layer/good/source",
        "sample/layer/good/target",
    ):
        path = tmp_path / package
        path.mkdir(parents=True)
        (path.parent / "__init__.py").touch()
        (path / "__init__.py").touch()
    (tmp_path / "sample/foreign/source/api.py").write_text(
        "from sample.foreign.target.api import Payload\n"
    )
    (tmp_path / "sample/foreign/target/api.py").write_text("class Payload: pass\n")
    (tmp_path / "sample/layer/good/source/api.py").write_text(
        "from sample.layer.good.target.api import Payload\n"
    )
    (tmp_path / "sample/layer/good/target/api.py").write_text("class Payload: pass\n")

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = result.observation.records("violations") or ()
    unknowns = result.observation.records("unknowns") or ()

    assert any(item.kind == "inside_source_domain_incomplete" for item in unknowns)
    assert any(
        any(rule_id.endswith("GOOD-NO-EDGE") for rule_id in item.rule_ids) for item in violations
    ), (
        violations,
        unknowns,
        result.observation.records("imports"),
    )
    assert not any(
        any(rule_id.endswith("FOREIGN-NO-EDGE") for rule_id in item.rule_ids) for item in violations
    )

    levels = {level.parent: level for level in inside_levels(result.observation)}
    foreign_level = levels["app:app:foreign"]
    assert {item.label: item.modules for item in foreign_level.components} == {
        "source": (),
        "target": (),
    }
    assert foreign_level.edges == ()
    good_level = levels["app:app:good"]
    assert {item.label: item.modules for item in good_level.components} == {
        "source": ("sample.layer.good.source", "sample.layer.good.source.api"),
        "target": ("sample.layer.good.target", "sample.layer.good.target.api"),
    }
    assert [(edge.source, edge.target) for edge in good_level.edges] == [("source", "target")]

    flow = build_flow(result.observation)
    app = next(item for item in flow.components if item.label == "app")
    assert app.inside is not None
    middle_app = next(item for item in app.inside.components if item.label == "app")
    assert middle_app.inside is not None
    foreign = next(item for item in middle_app.inside.components if item.label == "foreign")
    assert foreign.inside is not None
    assert {item.label: item.modules for item in foreign.inside.components} == {
        "source": (),
        "target": (),
    }
    assert foreign.inside.edges == ()
    good = next(item for item in middle_app.inside.components if item.label == "good")
    assert good.inside is not None
    assert any(
        edge.source == "source" and edge.target == "target" and edge.state == "violation"
        for edge in good.inside.edges
    )


def _write_deep_boundary_type_case(
    tmp_path: Path,
    target_public: list[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text("Architecture decision.\n")
    (tmp_path / "sample/layer/source").mkdir(parents=True)
    (tmp_path / "sample/layer/target").mkdir(parents=True)
    for package in ("sample", "sample/layer", "sample/layer/source", "sample/layer/target"):
        (tmp_path / package / "__init__.py").touch()
    (tmp_path / "sample/layer/source/api.py").write_text(
        "from sample.layer.target.api import Payload\n\n"
        "def run() -> Payload:\n    return Payload()\n"
    )
    (tmp_path / "sample/layer/target/api.py").write_text("class Payload: pass\n")

    public_api = ["sample.layer.source.api:run"]
    deepest = _contract(
        [_component_at("source", "sample.layer.source", public=public_api)],
        [
            {
                "id": "SOURCE-TYPES",
                "kind": "boundary_types",
                "source": "sample.layer.source",
                "rationale": "Keep exported source types within published boundaries.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    middle = _contract(
        [
            _component_at(
                "source",
                "sample.layer.source",
                public=public_api,
                inside="contracts/three.json",
            )
        ],
        [],
    )
    layer = _contract(
        [
            _component_at(
                "layer",
                "sample.layer",
                public=[*public_api, *target_public],
                inside="contracts/two.json",
            ),
        ],
        [],
    )
    root = _contract(
        [_component_at("app", "sample", public=public_api, inside="contracts/one.json")],
        [],
    )
    (tmp_path / "contract.json").write_text(json.dumps(root))
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/one.json").write_text(json.dumps(layer))
    (tmp_path / "contracts/two.json").write_text(json.dumps(middle))
    (tmp_path / "contracts/three.json").write_text(json.dumps(deepest))


@pytest.mark.parametrize(
    ("target_public", "expected_violation"),
    [([], True), (["sample.layer.target.api:Payload"], False)],
    ids=["private-type-is-rejected", "published-type-is-accepted"],
)
def test_deep_boundary_types_preserve_intermediate_target_ownership(
    tmp_path: Path,
    target_public: list[str],
    expected_violation: bool,
) -> None:
    _write_deep_boundary_type_case(tmp_path, target_public)
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "boundary_types"
        and any(rule_id.endswith("SOURCE-TYPES") for rule_id in item.rule_ids)
    ]
    unknowns = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
        and any(rule_id.endswith("SOURCE-TYPES") for rule_id in item.rule_ids)
    ]

    assert bool(violations) is expected_violation, (violations, unknowns)
    if expected_violation:
        assert not unknowns
        assert any("Payload" in item.title for item in violations)
    else:
        assert not violations
        assert not unknowns


def _add_nested_target_owner(tmp_path: Path, *, label: str, public: list[str]) -> None:
    path = tmp_path / "contracts/two.json"
    middle = json.loads(path.read_text())
    target = _component_at(label, "sample.layer.target", public=public)
    target["id"] = f"COMP-NESTED-TARGET-{label.upper()}"
    middle["components"].append(target)
    path.write_text(json.dumps(middle))


def _boundary_type_records(result: ObservationResult) -> tuple[list[Record], list[Record]]:
    assert result.observation is not None, result.diagnostics
    records: dict[str, list[Record]] = {
        section: [
            item
            for item in result.observation.records(section) or ()
            if any(rule.endswith("SOURCE-TYPES") for rule in item.rule_ids)
        ]
        for section in ("violations", "unknowns")
    }
    return records["violations"], records["unknowns"]


def test_same_label_nearest_private_reexport_remains_a_violation(tmp_path: Path) -> None:
    _write_deep_boundary_type_case(tmp_path, ["sample.layer.target.api:Payload"])
    _add_nested_target_owner(tmp_path, label="layer", public=[])
    (tmp_path / "sample/layer/target/impl.py").write_text("class Payload: pass\n")
    (tmp_path / "sample/layer/target/api.py").write_text(
        'from .impl import Payload\n__all__ = ["Payload"]\n'
    )

    violations, unknowns = _boundary_type_records(_observe(tmp_path))

    assert len(violations) == 1, (violations, unknowns)
    assert "Payload" in violations[0].title
    assert not unknowns


def test_nearest_owner_public_reexport_is_accepted(tmp_path: Path) -> None:
    _write_deep_boundary_type_case(tmp_path, [])
    _add_nested_target_owner(tmp_path, label="target", public=["sample.layer.target.api:Payload"])
    (tmp_path / "sample/layer/target/impl.py").write_text("class Payload: pass\n")
    (tmp_path / "sample/layer/target/api.py").write_text(
        'from .impl import Payload\n__all__ = ["Payload"]\n'
    )

    violations, unknowns = _boundary_type_records(_observe(tmp_path))

    assert not violations
    assert not unknowns


def test_published_dto_with_private_field_type_is_rejected(tmp_path: Path) -> None:
    _write_deep_boundary_type_case(tmp_path, ["sample.layer.target.api:Payload"])
    (tmp_path / "sample/layer/target/api.py").write_text(
        "class Secret: pass\nclass Payload:\n    value: Secret\n"
    )

    violations, unknowns = _boundary_type_records(_observe(tmp_path))

    assert len(violations) == 1, (violations, unknowns)
    assert violations[0].data.get("path") == "return.value"
    assert violations[0].data.get("nested_annotation") == "Secret"
    assert not unknowns


@pytest.mark.parametrize(
    ("external_public", "invalid_public", "expected_violation"),
    [
        (["sample.foreign.api:Payload"], [], False),
        ([], ["sample.foreign.api:Payload"], True),
    ],
    ids=["root-public-survives-invalid-sibling", "invalid-sibling-cannot-publish"],
)
def test_invalid_inside_sibling_does_not_replace_root_type_ownership(
    tmp_path: Path,
    external_public: list[str],
    invalid_public: list[str],
    expected_violation: bool,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    for package in ("sample", "sample/layer", "sample/layer/source", "sample/foreign"):
        path = tmp_path / package
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").touch()
    (tmp_path / "contracts").mkdir()
    (tmp_path / "sample/layer/source/api.py").write_text(
        "from sample.foreign.api import Payload\n\ndef run() -> Payload: ...\n"
    )
    (tmp_path / "sample/foreign/api.py").write_text("class Payload: pass\n")

    public_api = ["sample.layer.source.api:run"]
    deepest = _contract(
        [_component_at("source", "sample.layer.source", public=public_api)],
        [
            {
                "id": "SOURCE-TYPES",
                "kind": "boundary_types",
                "source": "sample.layer.source",
                "rationale": "Keep exported source types within published boundaries.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    inside = _contract(
        [
            _component_at(
                "source",
                "sample.layer.source",
                public=public_api,
                inside="contracts/two.json",
            ),
            _component_at("invalid", "sample.foreign", public=invalid_public),
        ],
        [],
    )
    root = _contract(
        [
            _component_at("app", "sample.layer", inside="contracts/one.json"),
            _component_at("external", "sample.foreign", public=external_public),
        ],
        [],
    )
    (tmp_path / "contract.json").write_text(json.dumps(root))
    (tmp_path / "contracts/one.json").write_text(json.dumps(inside))
    (tmp_path / "contracts/two.json").write_text(json.dumps(deepest))

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "boundary_types"
        and any(rule_id.endswith("SOURCE-TYPES") for rule_id in item.rule_ids)
    ]
    unknowns = result.observation.records("unknowns") or ()

    assert any(item.kind == "inside_source_domain_incomplete" for item in unknowns), unknowns
    assert not any(
        item.kind == "boundary_type_limit"
        and any(rule_id.endswith("SOURCE-TYPES") for rule_id in item.rule_ids)
        for item in unknowns
    ), unknowns
    assert bool(violations) is expected_violation, (violations, unknowns)


def _write_ancestor_type_case(
    root: Path, *, layer_public_target: bool, root_public_target: bool = False
) -> None:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    for package in (
        "sample",
        "sample/layer",
        "sample/layer/source",
        "sample/layer/target",
    ):
        path = root / package
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").touch()
    (root / "contracts").mkdir()
    (root / "sample/layer/source/api.py").write_text(
        "from sample.layer.target.api import Payload\n\n"
        "def run() -> Payload:\n    return Payload()\n"
    )
    (root / "sample/layer/target/api.py").write_text("class Payload: pass\n")

    public_api = ["sample.layer.source.api:run"]
    deepest = _contract(
        [_component_at("source", "sample.layer.source", public=public_api)],
        [
            {
                "id": "SOURCE-TYPES",
                "kind": "boundary_types",
                "source": "sample.layer.source",
                "rationale": "Keep exported source types within published boundaries.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    middle = _contract(
        [
            _component_at(
                "source",
                "sample.layer.source",
                public=public_api,
                inside="contracts/three.json",
            )
        ],
        [],
    )
    layer_public = list(public_api)
    if layer_public_target:
        layer_public.append("sample.layer.target.api:Payload")
    layer = _contract(
        [
            _component_at(
                "layer",
                "sample.layer",
                public=layer_public,
                inside="contracts/two.json",
            )
        ],
        [],
    )
    root_public = list(public_api)
    if root_public_target:
        root_public.append("sample.layer.target.api:Payload")
    root_contract = _contract(
        [_component_at("app", "sample", public=root_public, inside="contracts/one.json")],
        [],
    )
    (root / "contract.json").write_text(json.dumps(root_contract))
    (root / "contracts/one.json").write_text(json.dumps(layer))
    (root / "contracts/two.json").write_text(json.dumps(middle))
    (root / "contracts/three.json").write_text(json.dumps(deepest))


def test_validate_reports_an_ancestor_owned_private_type(tmp_path: Path) -> None:
    _write_ancestor_type_case(tmp_path, layer_public_target=False)
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    findings = trace_valid_violations(observed.observation)
    assert [(item.kind, item.rule_ids, item.subjects) for item in findings] == [
        (
            "boundary_types",
            ("app:layer:source:SOURCE-TYPES",),
            ("sample.layer.source.api", "sample.layer.source.api.run"),
        )
    ]
    [finding] = findings
    assert finding.title == (
        "sample.layer.source.api.run returns Payload which layer does not declare"
    )
    assert (finding.data.get("position"), finding.data.get("annotation")) == ("return", "Payload")
    assert not any(
        item.kind == "boundary_type_position" and item.data.get("reason") == "external_type"
        for item in observed.observation.records("unknowns") or ()
    )

    _commit_tree(tmp_path)
    result, _ = run_validate(tmp_path, _scan_config(), observe)
    assert result.exit_code == 2
    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "rule.violated"
    ] == [
        (
            "rule.violated",
            "/components/0/inside",
            "app:layer:source:SOURCE-TYPES",
        )
    ]
    [diagnostic] = [item for item in result.diagnostics if item.code == "rule.violated"]
    assert diagnostic.unknown_claim == (
        "The observed code violates the declared rule: "
        "sample.layer.source.api.run returns Payload which layer does not declare"
    )


def test_deep_rule_diagnostic_pointer_uses_mount_with_colon_and_repeated_labels(
    tmp_path: Path,
) -> None:
    _write_ancestor_type_case(tmp_path, layer_public_target=False)
    root_path = tmp_path / "contract.json"
    root_contract = json.loads(root_path.read_text())
    app = root_contract["components"][0]
    app["label"] = "outer:layer"
    sibling = _component_at("layer", "sample.unused", inside="contracts/empty.json")
    sibling["id"] = "COMP-ROOT-SIBLING-LAYER"
    root_contract["components"] = [sibling, app]
    root_path.write_text(json.dumps(root_contract))

    middle_path = tmp_path / "contracts/one.json"
    middle = json.loads(middle_path.read_text())
    middle["components"][0]["id"] = "COMP-MIDDLE-LAYER"
    middle_path.write_text(json.dumps(middle))
    source_path = tmp_path / "contracts/two.json"
    source_contract = json.loads(source_path.read_text())
    source_contract["components"][0]["id"] = "COMP-MIDDLE-SOURCE"
    source_path.write_text(json.dumps(source_contract))
    deepest_path = tmp_path / "contracts/three.json"
    deepest = json.loads(deepest_path.read_text())
    deepest["components"][0]["id"] = "COMP-DEEP-SOURCE"
    deepest_path.write_text(json.dumps(deepest))
    (tmp_path / "contracts/empty.json").write_text(json.dumps(_contract([], [])))

    _commit_tree(tmp_path)
    result, _ = run_validate(tmp_path, _scan_config(), observe)
    assert result.exit_code == 2
    findings = [item for item in result.diagnostics if item.code == "rule.violated"]
    assert len(findings) == 1, result.diagnostics
    assert findings[0].subject.endswith(":SOURCE-TYPES")
    assert findings[0].pointer == "/components/1/inside"


def test_public_ancestor_type_is_accepted_by_deep_boundary_rule(tmp_path: Path) -> None:
    _write_ancestor_type_case(tmp_path, layer_public_target=True)
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    assert trace_valid_violations(observed.observation) == ()
    rule_id = "app:layer:source:SOURCE-TYPES"
    assert not any(
        item.kind in {"boundary_type_position", "boundary_type_limit"} and rule_id in item.rule_ids
        for item in observed.observation.records("unknowns") or ()
    )


def test_root_public_type_does_not_override_private_nearest_ancestor(tmp_path: Path) -> None:
    _write_ancestor_type_case(tmp_path, layer_public_target=False, root_public_target=True)
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    [finding] = trace_valid_violations(observed.observation)
    assert finding.kind == "boundary_types"
    assert finding.rule_ids == ("app:layer:source:SOURCE-TYPES",)
    assert finding.title == (
        "sample.layer.source.api.run returns Payload which layer does not declare"
    )
    assert not any(
        item.kind == "boundary_type_position" and item.data.get("reason") == "external_type"
        for item in observed.observation.records("unknowns") or ()
    )


def test_overlapping_same_level_owners_do_not_fall_back_to_public_ancestor(
    tmp_path: Path,
) -> None:
    _write_ancestor_type_case(tmp_path, layer_public_target=True, root_public_target=True)
    path = tmp_path / "contracts/two.json"
    middle = json.loads(path.read_text())
    middle["components"].extend(
        [
            _component_at("target_one", "sample.layer.target"),
            _component_at("target_two", "sample.layer.target"),
        ]
    )
    path.write_text(json.dumps(middle))

    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    rule_id = "app:layer:source:SOURCE-TYPES"
    assert not [
        item for item in trace_valid_violations(observed.observation) if rule_id in item.rule_ids
    ]
    positions = [
        item
        for item in observed.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position" and rule_id in item.rule_ids
    ]
    assert len(positions) == 1, observed.observation.records("unknowns")
    assert positions[0].data.get("reason") not in {None, "external_type"}, positions[0]
    limits = [
        item
        for item in observed.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit" and rule_id in item.rule_ids
    ]
    assert len(limits) == 1
    assert (
        limits[0].data.get("positions"),
        limits[0].data.get("decided"),
        limits[0].data.get("undecided"),
        limits[0].data.get("external_type"),
    ) == (1, 0, 1, 0)


def test_partially_valid_multi_package_ancestor_cannot_claim_foreign_type(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    for package in ("sample", "sample/layer", "sample/layer/local", "sample/foreign"):
        path = tmp_path / package
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").touch()
    (tmp_path / "contracts").mkdir()
    (tmp_path / "sample/layer/local/api.py").write_text(
        "from sample.foreign.api import Payload\n\n"
        "class LocalPayload: pass\n\n"
        "def local() -> LocalPayload: ...\n\n"
        "def foreign() -> Payload: ...\n"
    )
    (tmp_path / "sample/foreign/api.py").write_text("class Payload: pass\n")

    intermediate_public = [
        "sample.layer.local.api:LocalPayload",
        "sample.layer.local.api:local",
        "sample.layer.local.api:foreign",
        "sample.foreign.api:Payload",
    ]
    source_public = intermediate_public[:3]
    deepest = _contract(
        [_component_at("source", "sample.layer.local", public=source_public)],
        [
            {
                "id": "SOURCE-TYPES",
                "kind": "boundary_types",
                "source": "sample.layer.local",
                "rationale": "Keep exported source types within published boundaries.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    local = _component(
        "local",
        packages=["sample.layer.local", "sample.foreign"],
        public=intermediate_public,
    )
    local["inside"] = "contracts/two.json"
    middle = _contract([local], [])
    root = _contract(
        [
            _component_at("app", "sample.layer", inside="contracts/one.json"),
            _component_at("external", "sample.foreign", public=[]),
        ],
        [],
    )
    (tmp_path / "contract.json").write_text(json.dumps(root))
    (tmp_path / "contracts/one.json").write_text(json.dumps(middle))
    (tmp_path / "contracts/two.json").write_text(json.dumps(deepest))

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "boundary_types"
        and any(rule_id.endswith("SOURCE-TYPES") for rule_id in item.rule_ids)
    ]
    unknowns = result.observation.records("unknowns") or ()

    assert len(violations) == 1, (violations, unknowns)
    assert violations[0].subjects[-1] == "sample.layer.local.api.foreign"
    assert any(item.kind == "inside_source_domain_incomplete" for item in unknowns), unknowns
