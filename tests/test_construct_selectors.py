# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct selectors stay tied to a proven nominal receiver and one operand role."""

import ast
import copy
import json
import subprocess
from pathlib import Path

import pytest

from archkeel.check.evaluation.rules import _construct_violations
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
from archkeel.ir.codec import (
    canonical_json_bytes,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
)
from archkeel.ir.codec_contract import parse_contract
from archkeel.ir.codec_observation import (
    _ObservationVersion,
    _validate_selector_and_argument_versions,
)
from archkeel.ir.decisions import (
    rule_assessments,
    rule_evaluation_binding_id,
    rule_result_digest,
    selector_inventory_binding_id,
)
from archkeel.ir.facts import (
    Evidence,
    EvidenceClass,
    ForbiddenConstructKind,
    Record,
    RecordData,
)
from archkeel.ir.facts_validation import _selector_evidence_excerpt
from archkeel.ir.model import (
    ConstructSelector,
    ConstructSelectorRole,
    ForbiddenConstructRule,
    Section,
)
from archkeel.ir.profiles import ObservedSection, profile_for
from archkeel.ir.trace import trace_valid_violations


def test_selector_grammar_is_closed_and_requires_role_specific_fields():
    raw = {
        "schema_version": "3.11.0",
        "components": [],
        "rules": [
            {
                "id": "SELECT",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.Connection",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Route through the declared port.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            }
        ],
    }
    rule = parse_contract(raw).rules[0]
    assert isinstance(rule, ForbiddenConstructRule)
    assert rule.selector == ConstructSelector(
        "sample.Connection", "backend", ConstructSelectorRole.EQUALITY, "flat"
    )
    raw["schema_version"] = "3.10.0"
    try:
        parse_contract(raw)
    except ValueError as error:
        assert "3.11.0" in str(error)
    else:
        raise AssertionError("older contract version accepted a construct selector")


def test_selected_scope_without_applicable_facts_is_unknown():
    rule = ForbiddenConstructRule(
        "SELECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "Keep the selected port protected.",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector(
            "sample.core.Connection", "password", ConstructSelectorRole.READ
        ),
    )
    findings = _construct_violations([], [rule])
    assert len(findings) == 1
    assert findings[0]["evidence_class"] == "UNKNOWN"
    assert findings[0]["kind"] == "construct_selector_unknown"


def test_dynamic_call_facts_for_one_source_site_produce_one_construct_finding():
    rule = ForbiddenConstructRule(
        "NO-DYNAMIC",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample",
        (ForbiddenConstructKind.GETATTR,),
        "Avoid reflection.",
        ("test",),
        DecisionMaker.ARCHITECT,
    )
    signals = [
        {
            "id": item_id,
            "evidence_class": "FACT",
            "area": "type_architecture",
            "kind": "getattr_call",
            "title": "same source call",
            "subjects": ["sample.core.route"],
            "evidence_ids": [evidence_id],
            "rule_ids": [],
            "fact_ids": [item_id],
            "provenance": [],
            "data": {"owner": "sample.core.route", "construct": "getattr"},
        }
        for item_id, evidence_id in (
            ("CONSTRUCT-1", "EVD-call-1"),
            ("TYPE-1", "EVD-call-1"),
            ("CONSTRUCT-2", "EVD-call-2"),
        )
    ]

    findings = _construct_violations(signals, [rule])

    assert len(findings) == 2
    findings_by_evidence = {row["evidence_ids"][0]: row for row in findings}
    assert set(findings_by_evidence) == {"EVD-call-1", "EVD-call-2"}
    assert set(findings_by_evidence["EVD-call-1"]["fact_ids"]) == {"CONSTRUCT-1", "TYPE-1"}


def test_bounded_selector_excerpt_supports_match_headers():
    evidence = Evidence("EVD-test", "sample/core.py", 4, 4, 4, "    match conn.backend:")
    parsed = _selector_evidence_excerpt(evidence, "match")
    assert parsed is not None
    roots, offset, column_offset = parsed
    matches = [node for root in roots for node in ast.walk(root) if isinstance(node, ast.Match)]
    assert len(matches) == 1
    assert matches[0].subject.attr == "backend"
    assert offset == 1
    assert column_offset == 0


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
def test_native_free_parameter_capture_keeps_its_exact_lexical_owner(tmp_path: Path, mounted: bool):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "def outer(conn: Connection):\n"
        '    direct = conn.backend == "flat"\n'
        "    def captured():\n"
        '        return conn.backend == "flat"\n'
        "    def shadowed(conn):\n"
        '        return conn.backend == "flat"\n'
        "    def shadowed_lambda():\n"
        '        return (lambda conn: conn.backend == "flat")(factory())\n'
        "    def shadowed_comprehension(connections):\n"
        '        return [conn.backend == "flat" for conn in connections]\n'
        "def reassigned(conn: Connection):\n"
        "    conn = factory()\n"
        '    return conn.backend == "flat"\n'
    )
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Selector fixture.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "SELECT",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.core.Connection",
            "member": "backend",
            "role": "equality",
            "literal": "flat",
        },
        "rationale": "Keep selector proofs bound to their lexical parameter.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    provenance = ["docs/architecture/sample.md"]
    if mounted:
        child = {
            "id": "COMP-child",
            "label": "child",
            "role": "component",
            "packages": ["sample"],
            "responsibilities": ["Own child."],
            "forbidden_responsibilities": [],
            "provenance": provenance,
        }
        parent = dict(child, id="COMP-parent", label="parent", inside="inside.json")
        (root / "inside.json").write_text(
            json.dumps({"schema_version": "3.11.0", "components": [child], "rules": [rule]})
        )
        contract = {"schema_version": "3.11.0", "components": [parent], "rules": []}
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    selectors = [
        row
        for row in model.records("constructs") or ()
        if row.kind == "construct_selector" and row.data.get("selector_role") == "equality"
    ]
    captured = next(row for row in selectors if row.data.get("owner", "").endswith(".captured"))
    assert captured.data.get("receiver_type") == "sample.core.Connection"
    assert captured.data.get("receiver_parameter") == "conn"
    assert captured.data.get("receiver_parameter_owner") == "sample.core.outer"
    assert captured.data.get("receiver_binding").get("origin") == "declared_receiver"
    shadowed = next(row for row in selectors if row.data.get("owner", "").endswith(".shadowed"))
    assert shadowed.data.get("receiver_type") is None
    assert shadowed.data.get("receiver_binding") is None
    reassigned = next(row for row in selectors if row.data.get("owner", "").endswith(".reassigned"))
    assert reassigned.data.get("receiver_type") is None
    assert reassigned.data.get("receiver_binding") is None
    assessment = next(row for row in result.rule_assessments if row.id.endswith("SELECT"))
    assert assessment.status.value == "FAIL"
    for index, payload in enumerate(
        (observation_payload(model), decode_canonical_model(json.loads(encoded)))
    ):
        path = tmp_path / f"captured-selector-{mounted}-{index}.json"
        path.write_bytes(canonical_json_bytes(encode_canonical_model(payload)))
        replay = run_saved_report(path)
        assert not replay.diagnostics, replay.diagnostics
        [saved] = [row for row in replay.rule_assessments if row.id.endswith("SELECT")]
        assert saved.status == assessment.status

    ordinary = observation_payload(model)
    columnar = decode_canonical_model(json.loads(encoded))
    model_evidence = {item.id: item for item in model.evidence}
    for index, payload in enumerate((ordinary, columnar)):
        records = payload["constructs"]
        captured_row = next(
            row
            for row in records
            if row["kind"] == "construct_selector"
            and row["data"].get("owner", "").endswith(".captured")
        )
        for excerpt_marker in ("lambda conn:", "for conn in connections"):
            shadowed_row = next(
                row
                for row in records
                if row["kind"] == "construct_selector"
                and any(
                    excerpt_marker in model_evidence[identifier].excerpt
                    and model_evidence[identifier].line == model_evidence[identifier].end_line
                    for identifier in row["evidence_ids"]
                    if identifier in model_evidence
                )
            )
            changed = copy.deepcopy(payload)
            target = next(row for row in changed["constructs"] if row["id"] == shadowed_row["id"])
            donor = captured_row["data"]
            for field in (
                "receiver_type",
                "receiver_binding",
                "receiver_parameter",
                "receiver_parameter_owner",
                "receiver_parameter_scopes",
            ):
                target["data"][field] = copy.deepcopy(donor[field])
            target["evidence_ids"] = sorted(
                set(target["evidence_ids"]) | set(donor["receiver_binding"]["evidence_ids"])
            )
            tampered_path = tmp_path / f"shadowed-capture-{index}-{excerpt_marker}.json"
            tampered_path.write_bytes(canonical_json_bytes(encode_canonical_model(changed)))
            rejected = run_saved_report(tampered_path)
            assert rejected.rule_assessments is None
            assert rejected.diagnostics


@pytest.mark.parametrize(
    ("section_name", "kind", "entries"),
    [
        (ObservedSection.CONSTRUCTS, "construct_selector", ()),
        (ObservedSection.UNKNOWNS, "construct_selector_unknown", ()),
        (
            "declarations",
            "forbidden_construct",
            (("selector", RecordData(())),),
        ),
        (
            "scope_observations",
            "rule_evaluation",
            (("claim", "construct_selector"),),
        ),
        (
            "scope_observations",
            "rule_evaluation",
            (("selector", RecordData(())),),
        ),
    ],
)
def test_selector_vocabulary_requires_its_introducing_observation_version(
    section_name: str, kind: str, entries: tuple[tuple[str, object], ...]
):
    record = Record(
        "RECORD-1",
        EvidenceClass.FACT,
        "type_architecture",
        kind,
        "selector fixture",
        (),
        (),
        (),
        (),
        (),
        RecordData(entries),
    )
    sections = (Section(section_name, (record,)),)

    with pytest.raises(ValueError, match="selector facts require observation schema 2.6.0"):
        _validate_selector_and_argument_versions(
            _ObservationVersion.V2_5, sections, profile_for("archkeel-python-analyzer")
        )
    _validate_selector_and_argument_versions(
        _ObservationVersion.V2_6, sections, profile_for("archkeel-python-analyzer")
    )


def test_native_saved_report_keeps_fail_and_unknown_for_selected_scope(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/ports.py").write_text("class ExternalConnection:\n    backend: str\n")
    (root / "sample/aliases.py").write_text(
        "from .ports import ExternalConnection as Conn\n\ndef build():\n    Conn()\n"
    )
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "class Label:\n    backend: str\n"
        "def route(conn: Connection, label: Label, unclear, key):\n"
        '    conn.backend == "flat"\n'
        '    "flat" == conn.backend\n'
        '    label.backend == "flat"\n'
        '    unclear.backend == "flat"\n'
        "    getattr(conn, key)\n"
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = {
        "schema_version": "3.11.0",
        "components": [],
        "rules": [
            {
                "id": "SELECT",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.core.Connection",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Keep route selection on the declared port.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            },
            {
                "id": "SELECT_ALIAS",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.ports.ExternalConnection",
                    "role": "constructor",
                },
                "rationale": "Resolve imported selector aliases canonically.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            },
        ],
    }
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics[0].unknown_claim if result.diagnostics else None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert model.schema_version == "2.10.0"
    assert any(row.kind == "construct_selector" for row in model.records("constructs"))
    reflection = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector" and row.data.get("selector_role") == "reflect"
    ]
    assert len(reflection) == 1
    assert reflection[0].data.get("status") == "unknown"
    assert reflection[0].data.get("receiver_type") == "sample.core.Connection"
    assert reflection[0].data.get("receiver_binding").get("origin") == "declared_receiver"
    assert len(trace_valid_violations(model)) == 3
    selected = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector"
        and row.data.get("receiver_type") == "sample.core.Connection"
    ]
    assert {
        row.data.get("receiver_binding").get("origin")
        for row in selected
        if row.data.get("selector_role") == "equality"
    } >= {"declared_receiver"}
    assert any(
        row.data.get("selector_role") == "constructor"
        and row.data.get("receiver_type") == "sample.ports.ExternalConnection"
        and row.data.get("status") == "decided"
        for row in model.records("constructs")
        if row.kind == "construct_selector"
    )
    assert any(row.kind == "construct_selector_unknown" for row in model.records("unknowns"))
    [receipt] = [
        row
        for row in model.records("scope_observations")
        if row.kind == "rule_evaluation" and row.rule_ids == ("SELECT",)
    ]
    assert receipt.data.get("claim") == "construct_selector"
    selector_data = receipt.data.get("selector")
    assert selector_data.get("receiver") == "sample.core.Connection"
    assert selector_data.get("member") == "backend"
    assert selector_data.get("role") == "equality"
    assert selector_data.get("literal") == "flat"
    assert receipt.data.get("inventory_fact_ids")
    relabeled = decode_canonical_model(json.loads(encoded))
    relabeled["schema_version"] = "2.5.0"
    relabeled["declarations"] = [
        item for item in relabeled["declarations"] if item["kind"] != "source_ownership"
    ]
    old_references = relabeled["references"]
    relabeled["references"] = []
    for item in old_references:
        if item["kind"] != "source_role":
            item["data"].pop("reference_context", None)
            relabeled["references"].append(item)
    with pytest.raises(ValueError, match="selector facts require observation schema 2.6.0"):
        parse_observation(relabeled)
    stripped = copy.deepcopy(relabeled)
    stripped["constructs"] = [
        row for row in stripped["constructs"] if row["kind"] != "construct_selector"
    ]
    assert stripped["declarations"]
    assert any(row["kind"] == "construct_selector_unknown" for row in stripped["unknowns"])
    assert any(
        row["kind"] == "rule_evaluation" and row["data"].get("claim") == "construct_selector"
        for row in stripped["scope_observations"]
    )
    with pytest.raises(ValueError, match="selector facts require observation schema 2.6.0"):
        parse_observation(stripped)

    ordinary = observation_payload(model)
    columnar = decode_canonical_model(json.loads(encoded))
    for index, payload in enumerate((ordinary, columnar)):
        valid_path = tmp_path / f"valid-{index}.json"
        valid_path.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(valid_path)
        assert not replay.diagnostics, (
            replay.diagnostics[0].unknown_claim if replay.diagnostics else None
        )
        assert next(row for row in replay.rule_assessments if row.id == "SELECT").status == "FAIL"
        assert (
            next(row for row in replay.rule_assessments if row.id == "SELECT_ALIAS").status
            == "FAIL"
        )
    for payload in (ordinary, columnar):
        selectors = [
            item
            for item in payload["constructs"]
            if item["kind"] == "construct_selector"
            and item["data"]["selector_role"] == "equality"
            and item["data"]["receiver_type"] == "sample.core.Connection"
        ]
        assert selectors
        selectors[0]["data"]["receiver_type"] = "sample.core.Label"
        selectors[0]["data"]["receiver_binding"]["target"] = "sample.core.Label"

    for index, payload in enumerate(
        (observation_payload(model), decode_canonical_model(json.loads(encoded)))
    ):
        for mode in ("delete", "move"):
            changed = copy.deepcopy(payload)
            finding = next(row for row in changed["violations"] if "SELECT" in row["rule_ids"])
            if mode == "delete":
                changed["violations"].remove(finding)
            else:
                finding["rule_ids"] = ["SELECT_ALIAS"]
            path = tmp_path / f"{mode}-selector-finding-{index}.json"
            path.write_bytes(canonical_json_bytes(encode_canonical_model(changed)))
            replay = run_saved_report(path)
            assessed = {row.id: row for row in replay.rule_assessments or ()}
            assert not assessed["SELECT"].evaluation_proven
            assert assessed["SELECT_ALIAS"].evaluation_proven is (mode == "delete")

    ordinary_path = tmp_path / "tampered-ordinary.json"
    ordinary_path.write_bytes(canonical_json_bytes(ordinary))
    columnar_path = tmp_path / "tampered-columnar.json"
    columnar_path.write_bytes(canonical_json_bytes(encode_canonical_model(columnar)))
    for saved in (ordinary_path, columnar_path):
        replay = run_saved_report(saved)
        assert replay.rule_assessments is None
        assert replay.diagnostics

    # Couple the changed receiver claim to a genuine Label proof from the same source.
    # The source expression remains conn.
    for index, payload in enumerate(
        (observation_payload(model), decode_canonical_model(json.loads(encoded)))
    ):
        _transplant_label_selector(payload)
        coupled_path = tmp_path / f"tampered-coupled-{index}.json"
        coupled_path.write_bytes(canonical_json_bytes(encode_canonical_model(payload)))
        replay = run_saved_report(coupled_path)
        assert replay.rule_assessments is None
        assert replay.diagnostics


def _transplant_label_selector(payload: dict[str, object]) -> None:
    selectors = [
        row
        for row in payload["constructs"]
        if row["kind"] == "construct_selector"
        and row["data"]["selector_role"] == "equality"
        and row["data"]["literal"] == "flat"
    ]
    target = next(
        row
        for row in selectors
        if row["data"]["receiver_parameter"] == "conn"
        and row["data"]["owner"] == "sample.core.route"
    )
    donor = next(
        row
        for row in selectors
        if row["data"]["receiver_parameter"] == "label"
        and row["data"]["owner"] == "sample.core.route"
    )
    target_data = target["data"]
    donor_data = donor["data"]
    target_data["receiver_type"] = donor_data["receiver_type"]
    target_data["receiver_parameter"] = donor_data["receiver_parameter"]
    target_data["receiver_binding"] = donor_data["receiver_binding"]
    target["evidence_ids"] = sorted(
        set(target["evidence_ids"]) | set(donor_data["receiver_binding"]["evidence_ids"])
    )


def test_native_escaped_stored_and_constructed_selector_receivers_replay(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\nclass Label:\n    backend: str\n"
        "class Built: pass\n"
        "class Holder:\n"
        "    def __init__(self, conn: Connection, label: Label):\n"
        "        self.conn = conn\n        self.label = label\n"
        "    def route(self):\n"
        '        self.conn.backend == "flat"\n'
        '        self.label.backend == "flat"\n'
        "        built = Built()\n"
        '        built.backend == "flat"\n'
        "class StoredHolder:\n"
        "    def __init__(self, conn: Connection, label: Label):\n"
        "        self.conn = conn\n        self.label = label\n"
        "    def route(self):\n"
        '        self.conn.backend.startswith("flat")\n'
        '        self.label.backend.startswith("flat")\n'
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = {
        "schema_version": "3.11.0",
        "components": [],
        "rules": [
            {
                "id": "SELECT",
                "kind": "forbidden_construct",
                "source": "sample.core",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.core.Connection",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Keep selected routes on the declared connection.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            },
            {
                "id": "SELECT_BUILT",
                "kind": "forbidden_construct",
                "source": "sample.core",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.core.Built",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Keep constructed route selection explicit.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            },
            {
                "id": "SELECT_STORED",
                "kind": "forbidden_construct",
                "source": "sample.core",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.core.Connection",
                    "member": "backend",
                    "role": "startswith",
                    "literal": "flat",
                },
                "rationale": "Keep stored connection route selection explicit.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            },
        ],
    }
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    equality_unknown = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector"
        and row.data.get("selector_role") == "equality"
        and row.data.get("member") == "backend"
        and row.data.get("receiver_type") is None
    ]
    assert {row.data.get("status") for row in equality_unknown} == {"unknown"}
    built = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector"
        and row.data.get("selector_role") == "equality"
        and row.data.get("receiver_type") == "sample.core.Built"
    ]
    assert {row.data.get("receiver_binding").get("origin") for row in built} == {
        "constructed_receiver"
    }
    stored = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector"
        and row.data.get("selector_role") == "startswith"
        and row.data.get("receiver_type") == "sample.core.Connection"
    ]
    assert {row.data.get("receiver_binding").get("origin") for row in stored} == {"stored_receiver"}
    assert next(row for row in result.rule_assessments if row.id == "SELECT").status == "UNKNOWN"
    assert next(row for row in result.rule_assessments if row.id == "SELECT_BUILT").status == "FAIL"
    assert (
        next(row for row in result.rule_assessments if row.id == "SELECT_STORED").status == "FAIL"
    )

    payloads = (observation_payload(model), decode_canonical_model(json.loads(encoded)))
    for index, payload in enumerate(payloads):
        valid_path = tmp_path / f"stored-valid-{index}.json"
        valid_path.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(valid_path)
        assert not replay.diagnostics
        assert (
            next(row for row in replay.rule_assessments if row.id == "SELECT").status == "UNKNOWN"
        )
        assert (
            next(row for row in replay.rule_assessments if row.id == "SELECT_BUILT").status
            == "FAIL"
        )
        assert (
            next(row for row in replay.rule_assessments if row.id == "SELECT_STORED").status
            == "FAIL"
        )

        selectors = [
            row
            for row in payload["constructs"]
            if row["kind"] == "construct_selector" and row["data"]["selector_role"] == "startswith"
        ]
        target = next(
            row
            for row in selectors
            if row["data"]["receiver_parameter"] is None
            and row["data"]["receiver_type"] == "sample.core.Connection"
        )
        donor = next(
            row
            for row in selectors
            if row["data"]["receiver_parameter"] is None
            and row["data"]["receiver_type"] == "sample.core.Label"
        )
        target["data"]["receiver_type"] = donor["data"]["receiver_type"]
        target["data"]["receiver_binding"] = donor["data"]["receiver_binding"]
        target["evidence_ids"] = sorted(
            set(target["evidence_ids"]) | set(donor["data"]["receiver_binding"]["evidence_ids"])
        )
        tampered_path = tmp_path / f"stored-retarget-{index}.json"
        tampered_path.write_bytes(canonical_json_bytes(encode_canonical_model(payload)))
        rejected = run_saved_report(tampered_path)
        assert rejected.rule_assessments is None
        assert rejected.diagnostics


def _retarget_selector_source_scope(payload: dict[str, object], rule_id: str) -> None:
    receipts = payload["scope_observations"]
    receipt = next(
        row for row in receipts if row["kind"] == "rule_evaluation" and row["rule_ids"] == [rule_id]
    )
    safe = next(row for row in payload["modules"] if row["data"]["qualified_name"] == "sample.safe")
    safe_symbols = [
        row for row in payload["symbols"] if row["data"]["qualified_name"] == "sample.safe"
    ]
    receipt["subjects"] = ["sample.safe"]
    receipt["fact_ids"] = sorted([safe["id"], *(row["id"] for row in safe_symbols)])
    receipt["data"]["source_modules"] = ["sample.safe"]
    receipt["data"]["inventory_fact_ids"] = []
    proof = receipt["data"]["selector_scope_proof"]
    proof["source_modules"] = ["sample.safe"]
    proof["inventory_fact_ids"] = []
    payload["violations"] = [row for row in payload["violations"] if rule_id not in row["rule_ids"]]
    parsed = parse_observation(payload)
    proof["result_digest"] = rule_result_digest(parsed.sections, rule_id)
    parsed = parse_observation(payload)
    receipt_record = next(
        row
        for row in parsed.records("scope_observations") or ()
        if row.kind == "rule_evaluation" and row.rule_ids == (rule_id,)
    )
    proof["binding_id"] = rule_evaluation_binding_id(
        selector_inventory_binding_id(parsed.sections, parsed.evidence),
        receipt_record,
        parsed.schema_version,
    )


def _selector_scope_fixture(root: Path, *, mounted: bool, source: str = "sample"):
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        'def route(conn: Connection):\n    conn.backend == "flat"\n'
    )
    (root / "sample/safe.py").write_text("VALUE = 1\n")
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Fixture provenance.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "SELECT",
        "kind": "forbidden_construct",
        "source": source,
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.core.Connection",
            "member": "backend",
            "role": "equality",
            "literal": "flat",
        },
        "rationale": "Exercise selector source binding.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    if mounted:
        provenance = ["docs/architecture/sample.md"]
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.11.0",
                    "components": [
                        {
                            "id": "COMP-child",
                            "label": "child",
                            "role": "component",
                            "packages": ["sample"],
                            "responsibilities": ["Own child."],
                            "forbidden_responsibilities": [],
                            "provenance": provenance,
                        }
                    ],
                    "rules": [rule],
                }
            )
        )
        contract = {
            "schema_version": "3.11.0",
            "components": [
                {
                    "id": "COMP-parent",
                    "label": "parent",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": ["Own parent."],
                    "forbidden_responsibilities": [],
                    "provenance": provenance,
                    "inside": "inside.json",
                }
            ],
            "rules": [],
        }
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    result = observe(
        root,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


def _selector_read_role_fixture(root: Path, *, mounted: bool):
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "def route(conn: Connection, key):\n"
        "    conn.backend\n"
        "    match conn.backend:\n        case 'flat': pass\n"
        "    conn.backend.startswith('flat')\n"
        "    getattr(conn, key)\n"
    )
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Fixture provenance.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "READ",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.core.Connection",
            "member": "backend",
            "role": "read",
        },
        "rationale": "Only ordinary reads are forbidden.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    provenance = ["docs/architecture/sample.md"]
    if mounted:
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.11.0",
                    "components": [
                        {
                            "id": "COMP-child",
                            "label": "child",
                            "role": "component",
                            "packages": ["sample"],
                            "responsibilities": ["Own child."],
                            "forbidden_responsibilities": [],
                            "provenance": provenance,
                        }
                    ],
                    "rules": [rule],
                }
            )
        )
        contract = {
            "schema_version": "3.11.0",
            "components": [
                {
                    "id": "COMP-parent",
                    "label": "parent",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": ["Own parent."],
                    "forbidden_responsibilities": [],
                    "provenance": provenance,
                    "inside": "inside.json",
                }
            ],
            "rules": [],
        }
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    result = observe(
        root,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


def _match_indentation_fixture(root: Path, *, mounted: bool, indent: str):
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "def route(conn: Connection):\n"
        f"{indent}if True:\n"
        f"{indent * 2}match conn.backend:\n"
        f"{indent * 3}case 'flat': pass\n"
    )
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Fixture provenance.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "MATCH",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.core.Connection",
            "member": "backend",
            "role": "match",
            "literal": "flat",
        },
        "rationale": "Keep the selected match receiver proven.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    provenance = ["docs/architecture/sample.md"]
    if mounted:
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.11.0",
                    "components": [
                        {
                            "id": "COMP-child",
                            "label": "child",
                            "role": "component",
                            "packages": ["sample"],
                            "responsibilities": ["Own child."],
                            "forbidden_responsibilities": [],
                            "provenance": provenance,
                        }
                    ],
                    "rules": [rule],
                }
            )
        )
        contract = {
            "schema_version": "3.11.0",
            "components": [
                {
                    "id": "COMP-parent",
                    "label": "parent",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": ["Own parent."],
                    "forbidden_responsibilities": [],
                    "provenance": provenance,
                    "inside": "inside.json",
                }
            ],
            "rules": [],
        }
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
@pytest.mark.parametrize(
    "indent",
    ["\t", "    "],
    ids=["tabs", "spaces"],
)
def test_nested_match_selector_excerpt_preserves_its_indentation(
    tmp_path: Path, mounted: bool, indent: str
):
    result, encoded = _match_indentation_fixture(
        tmp_path / f"repo-{mounted}-{len(indent)}", mounted=mounted, indent=indent
    )
    assert not result.diagnostics, result.diagnostics
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    [selector] = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector" and row.data.get("selector_role") == "match"
    ]
    assert selector.data.get("status") == "decided"
    assert selector.data.get("receiver_type") == "sample.core.Connection"
    [assessment] = [row for row in result.rule_assessments if row.id.endswith("MATCH")]
    assert assessment.status.value == "FAIL"

    ordinary = observation_payload(model)
    columnar = decode_canonical_model(
        json.loads(canonical_json_bytes(encode_canonical_model(ordinary)))
    )
    for index, payload in enumerate((ordinary, columnar)):
        path = tmp_path / f"match-indent-{mounted}-{len(indent)}-{index}.json"
        path.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(path)
        assert not replay.diagnostics, replay.diagnostics
        [saved] = [row for row in replay.rule_assessments if row.id.endswith("MATCH")]
        assert saved.status == assessment.status


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
def test_read_role_excludes_match_and_predicate_operands_live_and_saved(
    tmp_path: Path, mounted: bool
):
    model = _selector_read_role_fixture(tmp_path / "repo", mounted=mounted)
    reads = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector"
        and row.data.get("selector_role") == "read"
        and row.data.get("member") == "backend"
    ]
    assert len(reads) == 1
    reflects = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector" and row.data.get("selector_role") == "reflect"
    ]
    assert len(reflects) == 1
    assert reflects[0].data.get("status") == "unknown"
    assert reflects[0].data.get("receiver_type") == "sample.core.Connection"
    assert reflects[0].data.get("receiver_binding").get("origin") == "declared_receiver"
    assert (
        next(
            row for row in rule_assessments(model, undecided_by_rule={}) if row.id.endswith("READ")
        ).status
        == "FAIL"
    )
    ordinary = observation_payload(model)
    columnar = decode_canonical_model(
        json.loads(canonical_json_bytes(encode_canonical_model(ordinary)))
    )
    payloads = (ordinary, columnar)
    for index, payload in enumerate(payloads):
        path = tmp_path / f"read-role-{mounted}-{index}.json"
        path.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(path)
        assert replay.rule_assessments is not None, replay.diagnostics
        [assessment] = [row for row in replay.rule_assessments if row.id.endswith("READ")]
        assert assessment.status == "FAIL"
        assert not replay.diagnostics


@pytest.mark.parametrize(
    ("mounted", "source"),
    [
        (False, "sample"),
        (True, "sample"),
        (False, "sample.core.route"),
        (True, "sample.core.route"),
    ],
    ids=["root-package", "mounted-package", "root-symbol", "mounted-symbol"],
)
def test_selector_receipt_cannot_retarget_source_modules_to_safe_sibling(
    tmp_path: Path, mounted: bool, source: str
):
    model = _selector_scope_fixture(tmp_path / "repo", mounted=mounted, source=source)
    [original] = [
        row for row in rule_assessments(model, undecided_by_rule={}) if row.status == "FAIL"
    ]
    assert original.evaluation_proven
    ordinary = observation_payload(model)
    columnar = decode_canonical_model(
        json.loads(canonical_json_bytes(encode_canonical_model(ordinary)))
    )
    for index, payload in enumerate((ordinary, columnar)):
        changed = copy.deepcopy(payload)
        _retarget_selector_source_scope(changed, original.id)
        path = tmp_path / f"retarget-source-scope-{mounted}-{index}.json"
        path.write_bytes(canonical_json_bytes(encode_canonical_model(changed)))
        replay = run_saved_report(path)
        assert replay.rule_assessments is not None, replay.diagnostics
        assessment = next(row for row in replay.rule_assessments if row.id == original.id)
        assert not (assessment.status == "PASS" and assessment.evaluation_proven)


def _partial_selector_scope_fixture(root: Path, *, mounted: bool, literal: str):
    (root / "sample/core").mkdir(parents=True)
    (root / "sample/safe").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core/__init__.py").write_text("")
    (root / "sample/safe/__init__.py").write_text("")
    (root / "sample/safe/ports.py").write_text(
        "class Connection:\n    backend: str\n"
        "def route(conn: Connection):\n"
        f"    conn.backend == {literal!r}\n"
    )
    (root / "sample/core/routes.py").write_text(
        "from sample.safe.ports import Connection\n"
        "def route(conn: Connection):\n    conn.backend == 'flat'\n"
    )
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Fixture provenance.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "SELECT",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.safe.ports.Connection",
            "member": "backend",
            "role": "equality",
            "literal": "flat",
        },
        "rationale": "Exercise partial selector source coverage.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    if mounted:
        provenance = ["docs/architecture/sample.md"]
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.11.0",
                    "components": [
                        {
                            "id": "COMP-child",
                            "label": "child",
                            "role": "component",
                            "packages": ["sample"],
                            "responsibilities": ["Own child."],
                            "forbidden_responsibilities": [],
                            "provenance": provenance,
                        }
                    ],
                    "rules": [rule],
                }
            )
        )
        contract = {
            "schema_version": "3.11.0",
            "components": [
                {
                    "id": "COMP-parent",
                    "label": "parent",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": ["Own parent."],
                    "forbidden_responsibilities": [],
                    "provenance": provenance,
                    "inside": "inside.json",
                }
            ],
            "rules": [],
        }
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    result = observe(
        root,
        roots=("sample/safe",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
@pytest.mark.parametrize(
    ("literal", "expected_status"),
    [("round", "UNKNOWN"), ("flat", "FAIL")],
    ids=["covered-safe-subset", "known-fail-remains-visible"],
)
def test_selector_partial_source_scope_is_unknown_without_hiding_known_failures(
    tmp_path: Path, mounted: bool, literal: str, expected_status: str
):
    model = _partial_selector_scope_fixture(tmp_path / "repo", mounted=mounted, literal=literal)
    assessments = rule_assessments(model, undecided_by_rule={})
    [assessment] = [row for row in assessments if row.id.endswith("SELECT")]
    assert assessment.status == expected_status
    assert not assessment.evaluation_proven
    assert model.coverage.status == "PASS"
    unknown_rows = [
        row
        for row in model.records("unknowns") or ()
        if row.kind == "construct_selector_unknown"
        and any(rule_id.endswith("SELECT") for rule_id in row.rule_ids)
    ]
    assert unknown_rows, [
        (row.kind, row.rule_ids, row.data) for row in model.records("violations") or ()
    ] + [(row.kind, row.rule_ids, row.data) for row in model.records("unknowns") or ()]
    if expected_status == "FAIL":
        assert any(
            row.kind == "forbidden_construct"
            and any(rule_id.endswith("SELECT") for rule_id in row.rule_ids)
            for row in model.records("violations") or ()
        )
    for index, payload in enumerate(
        (
            observation_payload(model),
            decode_canonical_model(
                json.loads(canonical_json_bytes(encode_canonical_model(observation_payload(model))))
            ),
        )
    ):
        assert any(
            row["kind"] == "construct_selector_unknown"
            and any(rule_id.endswith("SELECT") for rule_id in row["rule_ids"])
            for row in payload["unknowns"]
        )
        if expected_status == "FAIL":
            assert any(
                row["kind"] == "forbidden_construct"
                and any(rule_id.endswith("SELECT") for rule_id in row["rule_ids"])
                for row in payload["violations"]
            )
        path = tmp_path / f"partial-selector-{mounted}-{expected_status}-{index}.json"
        path.write_bytes(canonical_json_bytes(encode_canonical_model(payload)))
        replay = run_saved_report(path)
        assert replay.rule_assessments is not None, replay.diagnostics
        [replayed] = [row for row in replay.rule_assessments if row.id.endswith("SELECT")]
        assert replayed.status == expected_status
        assert not replayed.evaluation_proven
        assert not replay.diagnostics


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
@pytest.mark.parametrize(
    ("local_use", "role", "literal", "safe_literal", "member"),
    [
        (
            "candidate.backend == key",
            "equality",
            "flat",
            "wide",
            "backend",
        ),
        (
            'match candidate.backend:\n        case "flat": pass',
            "match",
            "flat",
            "wide",
            "backend",
        ),
        (
            'unclear.backend == "flat"',
            "equality",
            "round",
            "flat",
            "backend",
        ),
        (
            'candidate.startswith("flat")',
            "startswith",
            "flat",
            "flat",
            "startswith",
        ),
    ],
    ids=[
        "dynamic-compare",
        "match-case",
        "unannotated-parameter",
        "unannotated-direct-predicate",
    ],
)
def test_ambiguous_selector_receiver_is_unknown_live_and_in_saved_reports(
    tmp_path: Path,
    mounted: bool,
    local_use: str,
    role: str,
    literal: str,
    safe_literal: str,
    member: str,
):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "class Label:\n    backend: str\n"
        "def route(conn: Connection, label: Label, key, unclear):\n"
        f'    conn.backend == "{safe_literal}"\n'
        '    label.backend == "flat"\n'
        '    conn.startswith("wide")\n'
        '    label.startswith("flat")\n'
        "    candidate = factory()\n"
        f"    {local_use}\n"
    )
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Selector fixture.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    rule = {
        "id": "SELECT",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "sample.core.Connection",
            "member": member,
            "role": role,
            "literal": literal,
        },
        "rationale": "Keep route selection on the declared port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    component = {
        "id": "COMPONENT",
        "label": "component",
        "role": "component",
        "packages": ["sample"],
        "responsibilities": ["Own sample."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }
    if mounted:
        (root / "inside.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.11.0",
                    "components": [component],
                    "rules": [rule],
                }
            )
        )
        contract = {
            "schema_version": "3.11.0",
            "components": [{**component, "id": "PARENT", "inside": "inside.json"}],
            "rules": [],
        }
    else:
        contract = {"schema_version": "3.11.0", "components": [], "rules": [rule]}
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)

    live, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, live.diagnostics[0].unknown_claim if live.diagnostics else None
    assert live.rule_assessments is not None
    [native] = [row for row in live.rule_assessments if row.id.endswith("SELECT")]
    assert native.status == "UNKNOWN"
    assert native.evaluation_proven

    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert any(
        row.kind == "construct_selector_unknown"
        and any(rule_id.endswith("SELECT") for rule_id in row.rule_ids)
        for row in model.records("unknowns") or ()
    )
    [receipt] = [
        row
        for row in model.records("scope_observations") or ()
        if row.kind == "rule_evaluation"
        and any(rule_id.endswith("SELECT") for rule_id in row.rule_ids)
    ]
    assert receipt.data.get("claim") == "construct_selector"
    selector = receipt.data.get("selector")
    assert selector.get("receiver") == "sample.core.Connection"
    assert selector.get("member") == member
    assert selector.get("role") == role
    assert selector.get("literal") == literal
    proof = receipt.data.get("selector_scope_proof")
    assert proof.get("source_modules") == ("sample", "sample.core")
    assert proof.get("selected_files") == ("sample/__init__.py", "sample/core.py")
    assert proof.get("inventory_fact_ids")
    assert proof.get("binding_id", "").startswith("RULE-EVALUATION-PROOF-")
    assert proof.get("result_digest", "").startswith("RULE-RESULT-")
    assert len(proof.get("contract_digest", "")) == 64
    assert len(proof.get("source_digest", "")) == 64

    if role == "startswith":
        predicate_signals = [
            row
            for row in model.records("constructs") or ()
            if row.kind == "construct_selector" and row.data.get("selector_role") == "startswith"
        ]
        assert any(
            row.data.get("receiver_type") == "sample.core.Connection"
            and row.data.get("member") == "startswith"
            and row.data.get("literal") == "wide"
            and row.data.get("status") == "decided"
            for row in predicate_signals
        )
        assert any(
            row.data.get("receiver_type") == "sample.core.Label"
            and row.data.get("literal") == "flat"
            and row.data.get("status") == "decided"
            for row in predicate_signals
        )
        assert any(
            row.data.get("receiver_type") is None
            and row.data.get("member") == "startswith"
            and row.data.get("literal") == "flat"
            and row.data.get("status") == "unknown"
            for row in predicate_signals
        )

    for index, payload in enumerate((observation_payload(model), json.loads(encoded))):
        path = tmp_path / f"ambiguous-selector-{mounted}-{index}.json"
        path.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(path)
        assert not replay.diagnostics, replay.diagnostics
        assert replay.rule_assessments is not None
        [saved] = [row for row in replay.rule_assessments if row.id == native.id]
        assert (saved.status, saved.evaluation_proven) == (
            native.status,
            native.evaluation_proven,
        )
