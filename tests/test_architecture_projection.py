# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The focused architecture view retains ownership, decisions and global evidence."""

import json
import subprocess
from dataclasses import asdict, replace

import pytest
from test_result_schema import current_validator as current_validator

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import RuleAssessment as GraphRuleAssessment
from archkeel.ir.architecture_graph import RuleAssessmentStatus as GraphRuleAssessmentStatus
from archkeel.ir.command_view import short_selector
from archkeel.ir.model import (
    RuleAssessment,
    RuleAssessmentStatus,
)


def test_public_rule_assessment_import_preserves_identity_constructor_and_fields():
    assert RuleAssessment is GraphRuleAssessment
    assert RuleAssessmentStatus is GraphRuleAssessmentStatus
    values = (
        "RULE",
        "complete_requires",
        "UNKNOWN",
        False,
        0,
        2,
        "architect",
        "Own boundaries.",
        ("docs/target.md",),
        "missing receipt",
        "core",
        ("CORE",),
    )
    assessment = RuleAssessment(*values)

    assert assessment == GraphRuleAssessment(*values)
    assert asdict(assessment) == {
        "id": "RULE",
        "kind": "complete_requires",
        "status": "UNKNOWN",
        "evaluation_proven": False,
        "count": 0,
        "undecided": 2,
        "decided_by": "architect",
        "rationale": "Own boundaries.",
        "provenance": ("docs/target.md",),
        "reason": "missing receipt",
        "scope": "core",
        "components": ("CORE",),
    }


def _repository(tmp_path, *, closed=True):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "sample").mkdir()
    for name, source in {
        "__init__": "",
        "core": "import sample.store\nimport sample.other\n",
        "store": "",
        "other": "",
        "idle": "",
    }.items():
        (root / "sample" / f"{name}.py").write_text(source)
    components = [
        {
            "id": name.upper(),
            "label": name,
            "role": "component",
            "packages": [f"sample.{name}"],
            "namespace": f"sample.{name}",
            "responsibilities": [f"Own {name}."],
            "forbidden_responsibilities": ["Own another boundary."],
            "public": [f"sample.{name}"],
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
            "requires": [],
        }
        for name in ("core", "store", "other", "idle")
    ]
    components[0]["requires"] = [
        {
            "component": "store",
            "rationale": "Persist through the store boundary.",
            "decided_by": "architect",
        }
    ]
    components[2]["requires"] = [
        {
            "component": "idle",
            "rationale": "Keep the unused boundary permission explicit.",
            "decided_by": "agent",
        }
    ]
    rules = [
        {
            "id": "NO-OTHER",
            "kind": "forbidden_dependency",
            "source": "sample.core",
            "target": "sample.other",
            "include_type_checking": True,
            "rationale": "Other owns an independent boundary.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    if closed:
        rules.append(
            {
                "id": "COMPLETE",
                "kind": "complete_requires",
                "rationale": "Only named permissions may cross.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
    (root / "architecture-contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": rules})
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots=["sample"]\nnamespace="sample"\ncontract="architecture-contract.json"\n'
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname="projection-test"\nversion="0.0.0"\nrequires-python=">=3.11"\n'
    )
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("Own explicit boundaries.\n")
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "demo@example.invalid"),
        ("config", "user.name", "Demo"),
        ("add", "-A"),
        ("-c", "commit.gpgsign=false", "commit", "-qm", "projection fixture"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root, ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "sample.store"),
        ("target", "sample.store"),
        ("rationale", "Forged reason."),
        ("decided_by", "agent"),
        ("include_type_checking", False),
    ],
)
def test_permission_metadata_cannot_disagree_with_authenticated_contract(tmp_path, field, value):
    root, config = _repository(tmp_path)

    def forged_analyzer(*args, **kwargs):
        original = observe(*args, **kwargs)
        model = original.observation
        sections = tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=replace(
                            record.data,
                            entries=tuple({**dict(record.data.entries), field: value}.items()),
                        ),
                    )
                    if record.id == "NO-OTHER"
                    else record
                    for record in section.records
                ),
            )
            for section in model.sections
        )
        return replace(original, observation=replace(model, sections=sections))

    result, _ = run_report(root, config=config, analyzer=forged_analyzer, only_architecture=True)
    assert result.exit_code == 2 and result.diagnostics
    assert (
        result.architecture_projection is None
        or not result.architecture_projection.permission_rules
    )


@pytest.mark.parametrize(
    "selector",
    ["sample.core", "sample.core.child", "sample.core:API", "sample.other", "sample.core_extra"],
)
def test_namespace_abbreviation_reconstructs_the_exact_identity(selector):
    prefix = "sample.core"
    short = short_selector(selector, prefix)
    restored = prefix + short if not short or short.startswith((".", ":")) else short
    assert restored == selector


def _target_boundary_repository(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["schema_version"] = "2.2.0"
    entities = [
        ("CLASS-A", "class", "sample.core.A", "CORE"),
        ("CLASS-B", "class", "sample.core.B", "CORE"),
        ("METHOD-A", "method", "sample.core.A.run", "CLASS-A"),
        ("METHOD-B", "method", "sample.core.B.run", "CLASS-B"),
        ("PORT", "interface", "sample.core.Port", "CORE"),
        ("PORT-METHOD", "method", "sample.core.Port.send", "PORT"),
        ("PEER", "class", "sample.store.Peer", "STORE"),
        ("OUTSIDE", "class", "sample.unowned.External", None),
    ]
    edges = [
        ("INTERNAL-TYPE", "references", "CLASS-A", "CLASS-B"),
        ("INTERNAL-METHOD", "calls", "METHOD-A", "METHOD-B"),
        ("PORT-REQUIRED", "realizes", "CLASS-A", "PORT"),
        ("PORT-METHOD-REQUIRED", "calls", "METHOD-A", "PORT-METHOD"),
        ("CROSS-REQUIRED", "references", "CLASS-A", "PEER"),
        ("COMPONENT-REQUIRED", "references", "CORE", "STORE"),
        ("UNOWNED-REQUIRED", "references", "CLASS-A", "OUTSIDE"),
        ("PUBLISHED-REQUIRED", "publishes", "CLASS-A", "CLASS-B"),
    ]
    contract["declarations"] = {
        "uml": {
            "schema_version": "1.0.0",
            "entities": [
                {
                    "id": identity,
                    "kind": kind,
                    "qualified_name": name,
                    "language": "python",
                    "parent_id": parent,
                    "presence": "planned",
                    "responsibilities": ["Own this declared Target fact."],
                    "provenance": ["docs/target.md"],
                }
                for identity, kind, name, parent in entities
            ],
            "relationships": [
                {
                    "id": identity,
                    "kind": kind,
                    "source_id": source,
                    "target_id": target,
                    "provenance": ["docs/target.md"],
                }
                for identity, kind, source, target in edges
            ],
        }
    }
    path.write_text(json.dumps(contract))
    return root, config


_POLICY_KINDS = (
    "sibling_isolation",
    "interface_boundary",
    "external_dependency_scope",
    "complete_external_scope",
    "no_component_cycles",
)


def _policy_repository(tmp_path, kind, *, include_type_checking=True):
    root, config = _repository(tmp_path)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    rule = {
        "id": "RESTRICT",
        "kind": kind,
        "rationale": "Preserve the explicitly governed boundary.",
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    target = "sample.store"
    if kind == "sibling_isolation":
        rule.update(
            members=["sample.core", "sample.store"], include_type_checking=include_type_checking
        )
    elif kind == "interface_boundary":
        (root / "sample/store.py").unlink()
        (root / "sample/store").mkdir()
        for name in ("__init__", "public", "private"):
            (root / "sample/store" / f"{name}.py").write_text("")
        contract["components"][1]["public"] = ["sample.store.public"]
        contract["components"][1]["planned"] = ["sample.store.future"]
        rule["include_type_checking"] = include_type_checking
        target = "sample.store.private"
    elif kind == "external_dependency_scope":
        (root / "sample/store.py").unlink()
        (root / "sample/store").mkdir()
        for name in ("__init__", "allowed", "denied"):
            (root / "sample/store" / f"{name}.py").write_text("")
        rule.update(
            dependency="sqlite3",
            allowed_sources=["sample.store.allowed"],
            exact_sources=["sample.store"],
        )
        target = "sqlite3"
    elif kind == "complete_external_scope":
        rule["source"] = "sample.core"
        contract["rules"].append(
            {
                "id": "EXTERNAL",
                "kind": "external_dependency_scope",
                "dependency": "sqlite3",
                "allowed_sources": ["sample.store"],
                "exact_sources": ["sample.core"],
                "rationale": "Use a declared database driver.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
        target = "requests"
    elif kind == "no_component_cycles":
        rule["components"] = ["core"]
        contract["components"][1]["requires"] = [
            {
                "component": "core",
                "rationale": "Call the explicit core boundary.",
            }
        ]
        (root / "sample/store.py").write_text("import sample.core\n")
    contract["rules"].append(rule)
    path.write_text(json.dumps(contract))
    (root / "sample/core.py").write_text("")
    return root, config, target


def _policy_row(view, identity="RESTRICT"):
    return next(item for item in view["permission_rules"] if item["declaration"]["id"] == identity)
