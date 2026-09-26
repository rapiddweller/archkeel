# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A nested Dart interface keeps profile limits scoped and known violations visible."""

import json
from pathlib import Path

from test_recursive_inside_independent_contracts import _commit_tree, _write_three_levels

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.run import inspect_observation
from archkeel.check.validation import run_validate


def _nested_package(
    tmp_path: Path,
    public: list[str],
    imports: dict[str, str],
    *,
    deep_rules: list[dict[str, object]] | None = None,
) -> Path:
    _write_three_levels(tmp_path)
    (tmp_path / "pubspec.yaml").write_text("name: sample\n")

    root_contract = json.loads((tmp_path / "contract.json").read_text())
    root_contract["rules"] = []
    (tmp_path / "contract.json").write_text(json.dumps(root_contract))

    middle_path = tmp_path / "contracts/one.json"
    middle_contract = json.loads(middle_path.read_text())
    middle_contract["rules"] = []
    middle_path.write_text(json.dumps(middle_contract))

    deep_path = tmp_path / "contracts/two.json"
    deep_contract = json.loads(deep_path.read_text())
    deep_contract["rules"] = deep_rules or [
        {
            "id": "INTERFACE",
            "kind": "interface_boundary",
            "rationale": "Check the source component against its declared public API.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    source, target = deep_contract["components"]
    source["requires"] = [{"component": "target", "rationale": "The source imports target."}]
    target["public"] = public
    deep_path.write_text(json.dumps(deep_contract))

    api = tmp_path / "lib/layer/target/api.dart"
    api.parent.mkdir(parents=True)
    api.write_text("class Api {}\nclass Secret {}\n")
    for relative, text in imports.items():
        path = tmp_path / "lib/layer/source" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    _commit_tree(tmp_path)
    return tmp_path


def _validate(root: Path):
    config = ScanConfig(("lib",), "sample", "contract.json", "0" * 64, "dart")
    return run_validate(root, config, observe)[0]


def _observe(root: Path):
    config = ScanConfig(("lib",), "sample", "contract.json", "0" * 64, "dart")
    return observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="0" * 40,
        dirty=False,
        contract_root=root,
        language="dart",
    )


def test_deep_no_show_symbol_boundary_is_unknown_not_incomplete(tmp_path: Path) -> None:
    root = _nested_package(
        tmp_path,
        ["sample.layer.target.api:Api"],
        {"root/nested/deep.dart": "import 'package:sample/layer/target/api.dart';\n"},
    )

    result = _validate(root)

    assert result.observation_complete == "PASS"
    assert result.declared_rules == "UNKNOWN"
    assert result.exit_code == 0
    assert result.observation is not None
    unknowns = [
        record
        for record in result.observation.records("unknowns") or ()
        if record.kind == "interface_symbol_limit"
    ]
    assert len(unknowns) == 1
    assert unknowns[0].rule_ids == ("INTERFACE",)
    assert unknowns[0].subjects == ("sample.layer.source.root.nested.deep",)


def test_deep_show_of_declared_symbol_is_decidable(tmp_path: Path) -> None:
    root = _nested_package(
        tmp_path,
        ["sample.layer.target.api:Api"],
        {"root/nested/deep.dart": "import 'package:sample/layer/target/api.dart' show Api;\n"},
    )

    result = _validate(root)

    assert result.exit_code == 0, result.diagnostics
    assert result.observation_complete == "PASS"
    assert result.declared_rules == "PASS"


def test_deep_no_show_to_whole_public_module_remains_pass(tmp_path: Path) -> None:
    root = _nested_package(
        tmp_path,
        ["sample.layer.target.api"],
        {"root/nested/deep.dart": "import 'package:sample/layer/target/api.dart';\n"},
    )

    result = _validate(root)

    assert result.exit_code == 0, result.diagnostics
    assert result.observation_complete == "PASS"
    assert result.declared_rules == "PASS"


def test_known_symbol_violation_survives_alongside_deep_unknown(tmp_path: Path) -> None:
    root = _nested_package(
        tmp_path,
        ["sample.layer.target.api:Api"],
        {
            "root/nested/deep.dart": "import 'package:sample/layer/target/api.dart';\n",
            "known_violation.dart": (
                "import 'package:sample/layer/target/api.dart' show Secret;\n"
            ),
        },
    )

    observed = _observe(root)

    assert observed.exit_code == 0, observed.diagnostics
    assert observed.observation is not None
    assert inspect_observation(observed.observation)[1] == "FAIL"
    assert any(
        record.kind == "interface_symbol_limit"
        and record.subjects == ("sample.layer.source.root.nested.deep",)
        for record in observed.observation.records("unknowns") or ()
    )
    assert any(
        "sample.layer.source.known_violation" in record.subjects
        for record in observed.observation.records("violations") or ()
    )


def test_deep_no_show_forbidden_symbol_limit_is_unknown(tmp_path: Path) -> None:
    root = _nested_package(
        tmp_path,
        [],
        {"root/nested/deep.dart": "import 'package:sample/layer/target/api.dart';\n"},
        deep_rules=[
            {
                "id": "NO-SECRET",
                "kind": "forbidden_dependency",
                "source": "sample.layer.source",
                "target": "sample.layer.target.api",
                "target_symbol": "Secret",
                "include_type_checking": True,
                "rationale": "Do not use Secret from the target API.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )

    result = _validate(root)

    assert result.observation_complete == "PASS"
    assert result.declared_rules == "UNKNOWN"
    assert result.exit_code == 0
    assert result.observation is not None
    unknowns = [
        record
        for record in result.observation.records("unknowns") or ()
        if record.kind == "dependency_symbol_limit"
    ]
    assert len(unknowns) == 1
    assert unknowns[0].rule_ids == ("NO-SECRET",)
    assert unknowns[0].subjects == ("sample.layer.source.root.nested.deep",)


def test_known_forbidden_symbol_violation_survives_alongside_deep_unknown(
    tmp_path: Path,
) -> None:
    root = _nested_package(
        tmp_path,
        [],
        {
            "root/nested/deep.dart": "import 'package:sample/layer/target/api.dart';\n",
            "known_violation.dart": (
                "import 'package:sample/layer/target/api.dart' show Secret;\n"
            ),
        },
        deep_rules=[
            {
                "id": "NO-SECRET",
                "kind": "forbidden_dependency",
                "source": "sample.layer.source",
                "target": "sample.layer.target.api",
                "target_symbol": "Secret",
                "include_type_checking": True,
                "rationale": "Do not use Secret from the target API.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )

    observed = _observe(root)

    assert observed.exit_code == 0, observed.diagnostics
    assert observed.observation is not None
    assert inspect_observation(observed.observation)[1] == "FAIL"
    assert any(
        record.kind == "dependency_symbol_limit"
        and record.subjects == ("sample.layer.source.root.nested.deep",)
        for record in observed.observation.records("unknowns") or ()
    )
    assert any(
        "sample.layer.source.known_violation" in record.subjects
        for record in observed.observation.records("violations") or ()
    )
