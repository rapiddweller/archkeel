# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested interface lifecycle checks use evidence from the owning level."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_recursive_inside_independent_contracts import (
    _commit_tree,
    _scan_config,
    _write_three_levels,
)

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, run_validate

_ENTRY = "sample.layer.source.api:Payload"
_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Require intentional local APIs.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _prepare(
    root: Path,
    *,
    source_code: str = "class Payload:\n    pass\n",
    target_code: str = "VALUE = 1\n",
    public: list[str] | None = None,
    planned: list[str] | None = None,
    interface_rule: bool = True,
    unrelated_facade: bool = False,
    facade_case: str | None = None,
) -> None:
    _write_three_levels(root)
    root_path = root / "contract.json"
    root_contract = json.loads(root_path.read_text())
    root_contract["rules"] = []
    leaf_parent = root_contract["components"][0]
    if unrelated_facade:
        leaf_parent["packages"] = ["sample.layer"]
        root_contract["rules"] = [_INTERFACE_RULE]
        root_contract["components"].append(
            _component(
                "foreign",
                packages=["sample.foreign"],
                public=["sample.foreign.api:consume"],
            )
        )
        root_contract["components"].append(
            _component("client", packages=["sample.client"], public=[])
        )
        (root / "sample/foreign").mkdir(parents=True)
        (root / "sample/foreign/__init__.py").write_text("")
        (root / "sample/foreign/api.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def consume(payload: Payload) -> None:\n    return None\n\n"
            "__all__ = ['consume']\n"
        )
        (root / "sample/client").mkdir(parents=True)
        (root / "sample/client/__init__.py").write_text("")
        (root / "sample/client/api.py").write_text(
            "from sample.foreign.api import consume\n\nVALUE = consume\n"
        )
    if facade_case == "ancestor-facade":
        leaf_parent["public"] = ["sample.layer:wrap"]
        (root / "sample/layer/__init__.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def wrap(payload: Payload) -> str:\n    return 'ok'\n\n"
            "__all__ = ['wrap']\n"
        )

    middle_path = root / "contracts/one.json"
    middle_contract = json.loads(middle_path.read_text())
    middle_contract["rules"] = []
    if facade_case == "parent-facade":
        middle_contract["components"][0]["public"] = ["sample.layer:wrap"]
        (root / "sample/layer/__init__.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def wrap(payload: Payload) -> str:\n    return 'ok'\n\n"
            "__all__ = ['wrap']\n"
        )
    elif facade_case in {"parent-constant", "unpublished-parent-import"}:
        if facade_case == "parent-constant":
            middle_contract["components"][0]["public"] = ["sample.layer:VALUE"]
            (root / "sample/layer/__init__.py").write_text(
                "from sample.layer.source.api import VALUE\n__all__ = ['VALUE']\n"
            )
        else:
            (root / "sample/layer/__init__.py").write_text(
                "from sample.layer.source.api import Payload\n__all__ = ['Payload']\n"
            )
    elif facade_case == "parent-reexport-external-definition":
        middle_contract["components"][0]["public"] = ["sample.layer.facade:run"]
        (root / "sample/foreign").mkdir(parents=True)
        (root / "sample/foreign/__init__.py").write_text("")
        (root / "sample/foreign/impl.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def run(payload: Payload) -> str:\n    return 'ok'\n"
        )
        (root / "sample/layer/facade.py").write_text(
            "from sample.foreign.impl import run\n__all__ = ['run']\n"
        )
    elif facade_case == "outside-facade-definition-inside":
        leaf_parent["public"] = ["sample.facade:run"]
        (root / "sample/facade.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def run(payload: Payload) -> str:\n    return 'ok'\n\n"
            "__all__ = ['run']\n"
        )
    if facade_case not in {
        "parent-facade",
        "parent-constant",
        "unpublished-parent-import",
        "parent-reexport-external-definition",
    }:
        middle_contract["components"][0]["public"] = []
    root_path.write_text(json.dumps(root_contract))
    middle_path.write_text(json.dumps(middle_contract))

    leaf_path = root / "contracts/two.json"
    leaf_contract = json.loads(leaf_path.read_text())
    leaf_contract["rules"] = [_INTERFACE_RULE] if interface_rule else []
    source = leaf_contract["components"][0]
    source["public"] = public if public is not None else []
    if planned is not None:
        source["planned"] = planned
    leaf_path.write_text(json.dumps(leaf_contract))
    if facade_case == "outside-facade-definition-inside":
        source_code += "\n\ndef run(payload: Payload) -> str:\n    return 'ok'\n"
    elif facade_case == "parent-constant":
        source_code = "VALUE = 1\n"
    (root / "sample/layer/source/api.py").write_text(source_code)
    (root / "sample/layer/target/api.py").write_text(target_code)
    if unrelated_facade:
        (root / "docs/architecture/sample.md").write_text(
            f"# Architecture\n\n{COMPONENT_GRAPH_MARKER}\n"
            "```mermaid\ngraph TD\n  foreign --> app\n  client --> foreign\n```\n"
        )
    _commit_tree(root)


@pytest.mark.parametrize(
    ("source_code", "entry", "expected_code"),
    [
        ("class Payload:\n    pass\n", _ENTRY, "interface.unused"),
        ("VALUE = 1\n", "sample.layer.source.api:VALUE", "interface.unused"),
    ],
    ids=["unused-type", "unused-constant"],
)
def test_nested_unused_public_is_reported_at_its_mounted_pointer(
    tmp_path: Path, source_code: str, entry: str, expected_code: str
) -> None:
    _prepare(tmp_path, source_code=source_code, public=[entry])

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 2, result
    assert [(item.code, item.pointer, item.subject) for item in result.diagnostics] == [
        (
            expected_code,
            "/components/0/inside/components/0/inside/components/0/public/0",
            entry,
        )
    ]


@pytest.mark.parametrize(
    ("target_code", "facade_case", "source_code", "entry"),
    [
        (
            "from sample.layer.source.api import Payload\nVALUE = Payload()\n",
            None,
            "class Payload:\n    pass\n",
            _ENTRY,
        ),
        ("VALUE = 1\n", "ancestor-facade", "class Payload:\n    pass\n", _ENTRY),
        ("VALUE = 1\n", "parent-facade", "class Payload:\n    pass\n", _ENTRY),
        (
            "VALUE = 1\n",
            "parent-constant",
            "VALUE = 1\n",
            "sample.layer.source.api:VALUE",
        ),
        (
            "VALUE = 1\n",
            "parent-reexport-external-definition",
            "class Payload:\n    pass\n",
            _ENTRY,
        ),
    ],
    ids=[
        "local-sibling-import",
        "ancestor-facade-signature",
        "immediate-parent-facade-signature",
        "parent-constant-reexport",
        "parent-reexport-definition-outside",
    ],
)
def test_nested_public_use_is_proven_by_a_sibling_or_parent_facade(
    tmp_path: Path, target_code: str, facade_case: str | None, source_code: str, entry: str
) -> None:
    _prepare(
        tmp_path,
        source_code=source_code,
        target_code=target_code,
        public=[entry],
        facade_case=facade_case,
    )

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 0, result.diagnostics
    assert not any(item.code == "interface.unused" for item in result.diagnostics)
    if facade_case in {
        "ancestor-facade",
        "parent-facade",
        "parent-constant",
        "parent-reexport-external-definition",
    }:
        observed = _observe(tmp_path)
        assert observed.observation is not None, observed.diagnostics
        if facade_case == "ancestor-facade":
            facade = next(
                item
                for item in observed.observation.records("symbols") or ()
                if item.data.get("module") == "sample.layer" and item.data.get("name") == "wrap"
            )
            assert "sample.layer.source.api.Payload" in facade.data.get("facade_types", ())
        elif facade_case == "parent-facade":
            facade = next(
                item
                for item in observed.observation.records("symbols") or ()
                if item.data.get("module") == "sample.layer" and item.data.get("name") == "wrap"
            )
            assert facade.data.get("declared_in_all") is True
            assert facade.data.get("parameters", ())[0].get("annotation") == "Payload"
        else:
            binding = "VALUE" if facade_case == "parent-constant" else "run"
            reexport = next(
                item
                for item in observed.observation.records("imports") or ()
                if item.data.get("source_module")
                == ("sample.layer" if binding == "VALUE" else "sample.layer.facade")
                and item.data.get("binding") == binding
            )
            if binding == "VALUE":
                assert reexport.data.get("reexport_chain") == ("sample.layer.source.api.VALUE",)
            else:
                assert reexport.data.get("reexport") is True
            assert reexport.data.get("declared_in_all") is True
            assert reexport.data.get("origin_definition") in {
                "sample.layer.source.api.VALUE",
                "sample.foreign.impl.run",
            }


@pytest.mark.parametrize(
    ("source_code", "facade_case"),
    [
        ("class Payload:\n    pass\n", "unpublished-parent-import"),
        (
            "class Payload:\n    pass\n\ndef run(payload: Payload) -> str:\n    return 'ok'\n",
            "outside-facade-definition-inside",
        ),
    ],
    ids=["unpublished-parent-import", "outside-facade-definition-inside"],
)
def test_unpublished_or_outside_facade_does_not_count_as_local_use(
    tmp_path: Path, source_code: str, facade_case: str
) -> None:
    _prepare(tmp_path, source_code=source_code, public=[_ENTRY], facade_case=facade_case)

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    if facade_case == "unpublished-parent-import":
        reexport = next(
            item
            for item in observed.observation.records("imports") or ()
            if item.data.get("source_module") == "sample.layer"
            and item.data.get("binding") == "Payload"
        )
        assert reexport.data.get("reexport_chain") == ("sample.layer.source.api.Payload",)
        assert reexport.data.get("declared_in_all") is True
        assert reexport.data.get("origin_definition") == "sample.layer.source.api.Payload"
        middle = json.loads((tmp_path / "contracts/one.json").read_text())
        assert middle["components"][0]["public"] == []
    else:
        facade = next(
            item
            for item in observed.observation.records("symbols") or ()
            if item.data.get("module") == "sample.facade" and item.data.get("name") == "run"
        )
        assert "sample.layer.source.api.Payload" in facade.data.get("facade_types", ())
        assert facade.data.get("declared_in_all") is True

    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "interface.unused"
    ] == [
        (
            "interface.unused",
            "/components/0/inside/components/0/inside/components/0/public/0",
            _ENTRY,
        )
    ]


def test_unrelated_facade_signature_does_not_satisfy_nested_public_usage(
    tmp_path: Path,
) -> None:
    _prepare(tmp_path, public=[_ENTRY], unrelated_facade=True)

    result, _ = run_validate(tmp_path, _scan_config(), observe)
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    facade = next(
        item
        for item in observed.observation.records("symbols") or ()
        if item.data.get("module") == "sample.foreign.api" and item.data.get("name") == "consume"
    )
    assert "sample.layer.source.api.Payload" in facade.data.get("facade_types", ())
    assert any(item.code == "rule.violated" for item in result.diagnostics), result

    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "interface.unused"
    ] == [
        (
            "interface.unused",
            "/components/0/inside/components/0/inside/components/0/public/0",
            _ENTRY,
        )
    ]


@pytest.mark.parametrize(
    ("target_code", "expected_codes"),
    [
        ("VALUE = 1\n", ()),
        (
            "from sample.layer.source.api import Payload\nVALUE = Payload()\n",
            ("interface.planned_built", "rule.violated"),
        ),
    ],
    ids=["built-unused-remains-planned", "used-planned-needs-promotion"],
)
def test_nested_planned_entry_lifecycle(
    tmp_path: Path, target_code: str, expected_codes: tuple[str, ...]
) -> None:
    _prepare(tmp_path, target_code=target_code, planned=[_ENTRY])

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert {item.code for item in result.diagnostics} == set(expected_codes), result
    assert result.exit_code == (2 if expected_codes else 0), result
    if "interface.planned_built" in expected_codes:
        assert any(
            item.pointer == "/components/0/inside/components/0/inside/components/0/planned/0"
            and item.subject == _ENTRY
            for item in result.diagnostics
        )


def test_nested_public_without_interface_rule_stays_ungated(tmp_path: Path) -> None:
    _prepare(tmp_path, public=[_ENTRY], interface_rule=False)

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 0
    assert result.diagnostics == ()


def test_repeated_child_labels_keep_usage_evidence_within_each_mount(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "sample/layer/source").mkdir(parents=True)
    (tmp_path / "sample/layer/target").mkdir(parents=True)
    (tmp_path / "sample/other/source").mkdir(parents=True)
    (tmp_path / "sample/other/target").mkdir(parents=True)
    for package in (
        "sample",
        "sample/layer",
        "sample/layer/source",
        "sample/layer/target",
        "sample/other",
        "sample/other/source",
        "sample/other/target",
    ):
        (tmp_path / f"{package}/__init__.py").write_text("")
    (tmp_path / "sample/layer/source/api.py").write_text("class Payload:\n    pass\n")
    (tmp_path / "sample/layer/target/api.py").write_text("VALUE = 1\n")
    (tmp_path / "sample/other/source/api.py").write_text("class Payload:\n    pass\n")
    (tmp_path / "sample/other/target/api.py").write_text(
        "from sample.other.source.api import Payload\nVALUE = Payload()\n"
    )
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    rule = dict(_INTERFACE_RULE)
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("layer", packages=["sample.layer"], public=[])
                    | {"inside": "contracts/layer.json"},
                    _component("other", packages=["sample.other"], public=[])
                    | {"inside": "contracts/other.json"},
                ],
                "rules": [],
            }
        )
    )
    for path, package in (
        ("contracts/layer.json", "sample.layer"),
        ("contracts/other.json", "sample.other"),
    ):
        (tmp_path / path).write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": [
                        _component(
                            "source",
                            packages=[f"{package}.source"],
                            public=[f"{package}.source.api:Payload"],
                        ),
                        _component("target", packages=[f"{package}.target"], public=[]),
                    ],
                    "rules": [rule],
                }
            )
        )
    _commit_tree(tmp_path)

    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    assert any(
        item.data.get("source_module") == "sample.other.target.api"
        and item.data.get("target_module") == "sample.other.source.api"
        for item in observed.observation.records("imports") or ()
    )

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "interface.unused"
    ] == [
        (
            "interface.unused",
            "/components/0/inside/components/0/public/0",
            "sample.layer.source.api:Payload",
        )
    ]


def test_unknown_profile_import_is_not_reported_as_an_unused_nested_name(
    tmp_path: Path,
) -> None:
    _write_three_levels(tmp_path)
    (tmp_path / "pubspec.yaml").write_text("name: sample\n")
    root_path = tmp_path / "contract.json"
    root_contract = json.loads(root_path.read_text())
    root_contract["rules"] = []
    root_path.write_text(json.dumps(root_contract))
    middle_path = tmp_path / "contracts/one.json"
    middle = json.loads(middle_path.read_text())
    middle["rules"] = []
    middle_path.write_text(json.dumps(middle))
    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_text())
    leaf["rules"] = [_INTERFACE_RULE]
    leaf["components"][0]["public"] = [_ENTRY]
    leaf_path.write_text(json.dumps(leaf))
    source = tmp_path / "lib/layer/source/api.dart"
    target = tmp_path / "lib/layer/target/api.dart"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text("class Payload {}\n")
    target.write_text("import 'package:sample/layer/source/api.dart';\n")
    _commit_tree(tmp_path)
    config = ScanConfig(("lib",), "sample", "contract.json", "0" * 64, "dart")

    observed = observe(
        tmp_path,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="0" * 40,
        dirty=False,
        contract_root=tmp_path,
        language="dart",
    )
    assert observed.observation is not None, observed.diagnostics
    assert any(
        item.data.get("source_module") == "sample.layer.target.api"
        and item.data.get("target_module") == "sample.layer.source.api"
        and item.data.get("symbols_known") is False
        for item in observed.observation.records("imports") or ()
    )
    result, _ = run_validate(tmp_path, config, observe)

    assert result.exit_code == 0
    assert result.observation_complete == "PASS"
    assert result.declared_rules == "UNKNOWN"
    assert not any(item.code == "interface.unused" for item in result.diagnostics)
