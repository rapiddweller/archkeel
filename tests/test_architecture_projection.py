# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The focused architecture view retains ownership, decisions and global evidence."""

import json
import subprocess
from collections import Counter
from dataclasses import replace

import pytest
from test_result_schema import validator as validator
from test_target_graph import _nested_repository

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation, result_bytes
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import (
    architecture_command_envelope,
    architecture_projection,
    short_selector,
    unknown_groups,
)
from archkeel.render.summary import report_summary


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
        '[project]\nname="projection-test"\nversion="0.0.0"\nrequires-python=">=3.11,<3.12"\n'
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


def test_real_cli_answers_intent_permission_ownership_and_finding(tmp_path, capsys, validator):
    root, _ = _repository(tmp_path)
    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "architecture",
                "--output",
                str(tmp_path / "output.json"),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0.0"
    view = payload["architecture_projection"]
    core = next(item for item in view["components"] if item["id"] == "CORE")
    assert core["path"] == "sample/core.py"
    assert core["provenance"] == ["docs/target.md"]
    assert core["responsibilities"] == ["Own core."]
    assert core["not_responsible_for"] == ["Own another boundary."]
    assert core["namespace"] + next(iter(core["public"])) == "sample.core"
    assert core["public"] == {"": [""]}
    assert core["decided_by"] == "architect"
    assert core["modules"] == {"": ""}
    (requirement,) = core["requires"]
    assert requirement["target_id"] == "STORE" and requirement["observed_imports"] == 1
    assert requirement["rationale"] == "Persist through the store boundary."
    permissions = {
        target: item["status"] for item in core["permissions"] for target in item["target_ids"]
    }
    assert permissions == {"IDLE": "forbidden", "OTHER": "forbidden", "STORE": "allowed"}
    assert view["levels"][0]["declared"] == 2
    assert view["levels"][0]["used"] == 2
    assert view["levels"][0]["unused"] == 1
    assert view["levels"][0]["undeclared"] == 1
    assert "sample" in view["levels"][0]["unowned_modules"]
    assert (
        view["source"]["git_head"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    )
    assert view["source"]["source_digest"] and view["contract_digest"]
    violation = next(
        item for item in payload["filtered_violations"] if item["rule_ids"] == ["NO-OTHER"]
    )
    assert violation["locations"] == [{"path": "sample/core.py", "line": 2}]
    assert view["violation_remedy"] == "Change the code or amend the contract with owner approval."
    assert payload["declared_rules"] == "FAIL"
    assert not list(validator.iter_errors(payload))


def test_open_permission_does_not_become_allowed_from_observed_use(tmp_path):
    root, config = _repository(tmp_path, closed=False)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    core = next(item for item in result.architecture_projection.components if item.id == "CORE")
    permissions = {item.target_id: item.status for item in core.permissions}
    assert permissions == {"IDLE": "undecided", "OTHER": "forbidden", "STORE": "allowed"}
    assert core.status == "UNKNOWN" and core.reason
    assert result.architecture_projection.unknowns


def test_component_slice_preserves_global_verdict_coverage_digests_and_unknowns(tmp_path):
    root, config = _repository(tmp_path)
    full, architecture = run_report(root, config=config, analyzer=observe, only_architecture=True)
    sliced, encoded = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    assert encoded == architecture
    assert sliced.declared_rules == full.declared_rules == "FAIL"
    assert sliced.coverage == full.coverage
    assert sliced.rule_assessments == full.rule_assessments
    assert sliced.measurements == full.measurements
    assert sliced.architecture_projection.source == full.architecture_projection.source
    assert (
        sliced.architecture_projection.contract_digest
        == full.architecture_projection.contract_digest
    )
    assert sliced.architecture_projection.unknowns == full.architecture_projection.unknowns
    assert [item.id for item in sliced.architecture_projection.components] == ["STORE"]
    assert "Filtered (only architecture):" in report_summary(full).sentence
    assert "Filtered (only architecture, component store):" in report_summary(sliced).sentence


def test_deepest_ownership_and_repeated_nested_labels_are_scope_qualified(tmp_path):
    root, config = _nested_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    view = result.architecture_projection
    assert view is not None, result.diagnostics
    components = {item.id: item for item in view.components}
    assert components["core:service:core"].modules
    assert not components["ROOT"].modules
    assert not components["core:core"].modules
    selected, _ = run_report(
        root,
        config=config,
        analyzer=observe,
        only_architecture=True,
        component="core:service:operations",
    )
    assert [item.id for item in selected.architecture_projection.components] == [
        "core:service:core"
    ]
    leaf_path = root / "leaf.json"
    raw = json.loads(leaf_path.read_bytes())
    raw["components"].append({**raw["components"][0], "id": "tie", "label": "parallel"})
    for owner in raw["components"]:
        owner.pop("namespace", None)
    leaf_path.write_text(json.dumps(raw))
    tied, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    gap = next(
        item for item in tied.architecture_projection.ownership_gaps if item.module == "sample.core"
    )
    assert gap.candidate_ids == ("core:service:core", "core:service:tie")
    assert not any(item.modules for item in tied.architecture_projection.components)
    assert gap.reason and tied.architecture_projection.status == "UNKNOWN"


def test_missing_target_and_partial_coverage_never_project_pass(tmp_path):
    root, config = _repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    sections = tuple(
        replace(
            section,
            records=tuple(
                item
                for item in section.records
                if item.kind not in {"architecture_target", "uml_target"}
            ),
        )
        for section in model.sections
    )
    incomplete = replace(model, sections=sections)
    view = architecture_projection(
        incomplete, architecture_report(incomplete), (), violation_remedy="existing remedy"
    )
    assert not view.components and view.status == "UNKNOWN" and view.unknowns
    (root / "sample/broken.py").write_text("def broken(:\n")
    partial, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert partial.exit_code == 2
    assert partial.architecture_projection is not None
    assert partial.architecture_projection.status == "UNKNOWN"
    assert all(item.status != "PASS" for item in partial.architecture_projection.components)
    assert partial.architecture_projection.levels[0].used is None


def test_two_same_commit_cli_results_are_identical_including_whole_envelope(tmp_path, capsys):
    root, _ = _repository(tmp_path)
    outputs = []
    for name in ("first", "second"):
        assert (
            main(
                [
                    "report",
                    "--root",
                    str(root),
                    "--only",
                    "architecture",
                    "--output",
                    str(tmp_path / f"{name}.json"),
                    "--json",
                ]
            )
            == 0
        )
        outputs.append(capsys.readouterr().out.encode())
    assert outputs[0] == outputs[1]
    assert len(outputs[0]) < 50_000


def test_unknown_architecture_component_is_a_named_diagnostic(tmp_path):
    root, config = _repository(tmp_path)
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="missing"
    )
    assert result.exit_code == 2 and result.diagnostics[0].kind == "filter_unknown"
    assert result.diagnostics[0].subject == "--component missing"


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


def test_partial_graph_import_coverage_has_no_zero_count_pass(tmp_path):
    root, config = _repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    partial = replace(
        report,
        observed=replace(
            report.observed,
            coverage=tuple(
                item
                for item in report.observed.coverage
                if "imports" not in item.relationship_kinds
            ),
        ),
    )
    view = architecture_projection(
        model, partial, result.rule_assessments, violation_remedy="existing remedy"
    )
    assert view.status == "UNKNOWN"
    assert view.levels[0].used is None and view.levels[0].unused is None
    assert all(item.status != "PASS" for item in view.components)


def test_repeated_inner_labels_require_a_scope_or_stable_id(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    raw = json.loads(path.read_bytes())
    for component in raw["components"]:
        if component["label"] not in {"other", "store"}:
            continue
        inside = component["label"] + ".json"
        component["inside"] = inside
        child = {**component, "id": "SHARED", "label": "shared"}
        child.pop("inside")
        child["requires"] = []
        (root / inside).write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": [child],
                    "rules": [
                        {
                            "id": "INNER-COMPLETE",
                            "kind": "complete_requires",
                            "rationale": "No sibling crossing is permitted.",
                            "provenance": ["docs/target.md"],
                            "decided_by": "architect",
                        }
                    ],
                }
            )
        )
    path.write_text(json.dumps(raw))
    full, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert full.architecture_projection is not None, full.diagnostics
    assert {
        item.id for item in full.architecture_projection.components if item.label == "shared"
    } == {"other:SHARED", "store:SHARED"}
    assert all(item.undecided == 0 for item in full.architecture_projection.levels)
    ambiguous, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="shared"
    )
    assert ambiguous.exit_code == 2 and ambiguous.diagnostics[0].kind == "filter_unknown"
    focused, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store:shared"
    )
    assert [item.id for item in focused.architecture_projection.components] == ["store:SHARED"]
    assert focused.declared_rules == full.declared_rules


def test_required_target_relationships_are_distinct_from_permission_and_usage(tmp_path):
    root, config = _nested_repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe, only_architecture=True)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    expected = {item.id for item in report.target.relationships if item.kind != "requires"}
    relationships = result.architecture_projection.required_relationships
    assert relationships and {item.id for item in relationships} == expected
    assert all(item.kind != "requires" and item.reasons for item in relationships)
    unavailable = architecture_projection(
        model,
        replace(report, comparison=None),
        result.rule_assessments,
        violation_remedy="existing remedy",
    )
    assert all(item.status == "UNKNOWN" for item in unavailable.required_relationships)
    assert unavailable.unknowns and unavailable.status == "UNKNOWN"


def test_symbol_finding_is_attached_to_its_component_without_changing_id_or_location(tmp_path):
    root, config = _repository(tmp_path)
    path = root / config.contract
    raw = json.loads(path.read_bytes())
    raw["rules"].append(
        {
            "id": "NO-GETATTR",
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["getattr"],
            "rationale": "Keep runtime access explicit.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    )
    path.write_text(json.dumps(raw))
    (root / "sample/core.py").write_text("def lookup(obj):\n    return getattr(obj, 'field')\n")
    result, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core"
    )
    violation = next(
        item for item in result.filtered_violations if item.record.rule_ids == ("NO-GETATTR",)
    )
    (component,) = result.architecture_projection.components
    assert component.status == "FAIL"
    assert violation.record.id in component.finding_ids
    assert [(item.path, item.line) for item in violation.locations] == [("sample/core.py", 2)]


def test_every_unknown_enters_one_exact_cause_and_scope_group(tmp_path):
    root, config = _repository(tmp_path, closed=False)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    unknowns = result.architecture_projection.unknowns
    expected = Counter((row.kind, row.reason, row.scopes) for row in unknowns)
    groups = unknown_groups(unknowns)
    actual = {
        (kind, reason, scopes): count
        for kind, reasons in groups.items()
        for reason, counts in reasons.items()
        for scopes, count in counts
    }
    assert actual == expected
    assert sum(actual.values()) == len(unknowns)
    assert any("other" in scopes for _, _, scopes in actual)
    selected, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    assert architecture_command_envelope(selected).architecture_projection.unknowns == groups
    assert selected.declared_rules == result.declared_rules == "FAIL"


@pytest.mark.parametrize(
    "selector",
    ["sample.core", "sample.core.child", "sample.core:API", "sample.other", "sample.core_extra"],
)
def test_namespace_abbreviation_reconstructs_the_exact_identity(selector):
    prefix = "sample.core"
    short = short_selector(selector, prefix)
    restored = prefix + short if not short or short.startswith((".", ":")) else short
    assert restored == selector


def test_compact_required_relationships_restore_exact_ids_names_and_core_results(
    tmp_path, validator
):
    root, config = _nested_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    payload = json.loads(result_bytes(result))
    wire = payload["architecture_projection"]
    expected = {
        item.id: item
        for item in result.architecture_projection.required_relationships
        if item.internal_scope is None
    }
    restored = wire["required_relationships"]
    assert {item["id"] for item in restored} == set(expected) and restored
    for item in restored:
        original = expected[item["id"]]
        assert (
            item["kind"],
            item["source_id"],
            item["source"],
            item["target_id"],
            item["target"],
            item["status"],
            tuple(item["reasons"]),
        ) == (
            original.kind,
            original.source_id,
            original.source,
            original.target_id,
            original.target,
            original.status,
            original.reasons,
        )
    assert not list(validator.iter_errors(payload))


def test_compact_components_restore_api_modules_and_all_permission_deciders(tmp_path):
    root, config = _repository(tmp_path)
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_bytes())
    contract["components"][0]["public"] = [
        "sample.core",
        "sample.core:API",
        "sample.core:Secondary",
        "sample.core.child:Nested",
    ]
    contract["components"][0]["planned"] = []
    contract_path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    wire = json.loads(result_bytes(result))["architecture_projection"]
    canonical = {item.id: item for item in result.architecture_projection.components}
    for item in wire["components"]:
        original = canonical[item["id"]]
        prefix = item.get("selector_prefix", item.get("namespace"))

        def full_name(value, prefix=prefix):
            return (
                prefix + value
                if prefix is not None and (not value or value.startswith((".", ":")))
                else value
            )

        for key in ("public", "planned"):
            groups = item.get(key)
            restored = (
                None
                if groups is None
                else tuple(
                    full_name(module) + (":" + symbol if symbol else "")
                    for module, symbols in groups.items()
                    for symbol in symbols
                )
            )
            expected = original.public if key == "public" else original.planned
            assert (None if restored is None else tuple(sorted(restored))) == expected
        assert {
            full_name(name): None
            if path is None
            else item["path"]
            if not path
            else item["path"] + "/" + path
            for name, path in item.get("modules", {}).items()
        } == {module.name: module.path for module in original.modules}
        restored_permissions = {}
        for permission in item.get("permissions", []):
            for target in permission["target_ids"]:
                identifiers = permission.get("rule_ids", []) + [
                    requirement["id"]
                    for requirement in item.get("requires", [])
                    if permission["status"] == "allowed" and requirement["target_id"] == target
                ]
                restored_permissions[target] = (
                    permission["status"],
                    tuple(sorted(identifiers)),
                    wire["reasons"][permission["reason"]],
                )
        assert restored_permissions == {
            row.target_id: (row.status, row.rule_ids, row.reason) for row in original.permissions
        }


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


def test_required_partition_keeps_ports_cross_scope_components_and_unowned_details(tmp_path):
    root, config = _target_boundary_repository(tmp_path)
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert result.architecture_projection is not None, result.diagnostics
    view = result.architecture_projection
    assert {row.id for row in view.required_relationships if row.internal_scope is not None} == {
        "INTERNAL-TYPE",
        "INTERNAL-METHOD",
    }
    envelope = architecture_command_envelope(result).architecture_projection
    assert {row.id for row in envelope.required_relationships} == {
        "PORT-REQUIRED",
        "PORT-METHOD-REQUIRED",
        "CROSS-REQUIRED",
        "COMPONENT-REQUIRED",
        "UNOWNED-REQUIRED",
        "PUBLISHED-REQUIRED",
    }
    expected = Counter(
        (row.internal_scope, row.kind, row.status, row.reasons)
        for row in view.required_relationships
        if row.internal_scope is not None
    )
    assert {
        (row.scope, row.kind, row.status, row.reasons): row.count
        for row in envelope.required_summaries
    } == expected
    assert len(envelope.required_relationships) + sum(
        row.count for row in envelope.required_summaries
    ) == len(view.required_relationships)
    assert all(row.scope == "core" for row in envelope.required_summaries)
    peer, _ = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="store"
    )
    peer_wire = architecture_command_envelope(peer).architecture_projection
    assert {row.id for row in peer_wire.required_relationships} == {
        "CROSS-REQUIRED",
        "COMPONENT-REQUIRED",
    }
    assert not peer_wire.required_summaries
    assert peer_wire.unknowns == envelope.unknowns and peer.coverage == result.coverage


@pytest.mark.parametrize("role", ["interface", "contract"])
def test_interface_and_contract_component_roles_never_hide_required_details(tmp_path, role):
    root, config = _target_boundary_repository(tmp_path)
    path = root / config.contract
    contract = json.loads(path.read_bytes())
    contract["components"][0]["role"] = role
    path.write_text(json.dumps(contract))
    result, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert result.architecture_projection is not None, result.diagnostics
    wire = architecture_command_envelope(result).architecture_projection
    assert not wire.required_summaries
    assert (
        len(wire.required_relationships)
        == len(result.architecture_projection.required_relationships)
        == 8
    )


def test_required_summaries_preserve_missing_core_evidence_reasons_and_counts(tmp_path):
    root, config = _target_boundary_repository(tmp_path)
    result, encoded = run_report(root, config=config, analyzer=observe, only_architecture=True)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = replace(architecture_report(model), comparison=None)
    projection = architecture_projection(
        model, report, result.rule_assessments, violation_remedy="existing remedy"
    )
    unavailable = replace(result, architecture_projection=projection)
    wire = architecture_command_envelope(unavailable).architecture_projection
    assert len(wire.required_relationships) == 6
    assert sum(row.count for row in wire.required_summaries) == 2
    assert all(row.status == "UNKNOWN" for row in wire.required_summaries)
    assert all(
        row.reasons == ("No authenticated Core assessment exists for this required relationship.",)
        for row in wire.required_summaries
    )
    assert sum(
        count
        for reasons in wire.unknowns.values()
        for rows in reasons.values()
        for scopes, count in rows
    ) == len(projection.unknowns)
