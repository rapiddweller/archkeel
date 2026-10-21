# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Saved selector proofs stay bound to the exact lexical receiver scope."""

from __future__ import annotations

import ast
import copy
import json
import subprocess
from pathlib import Path

import pytest

from archkeel.check.ports import ScanConfig
from archkeel.check.report import _validate_saved_sources, run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    canonical_json_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
)
from archkeel.ir.decisions import (
    rule_evaluation_binding_id,
    rule_result_digest,
    selector_inventory_binding_id,
)
from archkeel.ir.facts import Record, stable_id

_SOURCE = """class Connection:
    backend: str

class Other:
    backend: str

def outer(conn: Connection):
    def captured():
        return conn.backend == "flat"

    def safe_sibling():
        return conn.backend == "flat"

    def local_assignment():
        conn = make()
        return conn.backend == "flat"

    def local_import():
        from sample.other import Connection as conn
        return conn.backend == "flat"

    def global_name():
        global conn
        return conn.backend == "flat"

    lambda_shadow = lambda conn: conn.backend == "flat"
    comprehension_shadow = [conn.backend == "flat" for conn in candidates]

    class class_shadow:
        conn = make()
        conn.backend == "flat"
"""


def _fixture(root: Path, *, mounted: bool):
    (root / "sample").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text(_SOURCE)
    (root / "sample/other.py").write_text("class Connection:\n    backend: str\n")
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Selector replay fixture.\n")
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
        "rationale": "Keep saved selector proofs lexically bound.",
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
    assert not result.diagnostics
    return model, result


def _selector_line(record: Record, evidence_by_id: dict[str, object]) -> int:
    evidence = [evidence_by_id[item] for item in record.evidence_ids if item in evidence_by_id]
    candidates = [item for item in evidence if "conn.backend" in item.excerpt]
    assert candidates
    return min(candidates, key=lambda item: len(item.excerpt)).line


def _scope_chain(
    owner_name: str,
    parameter_owner: str,
    declarations: dict[str, Record],
    evidence_rows: list[dict[str, object]],
) -> list[dict[str, str]]:
    scopes = _scope_nodes()
    current = declarations[owner_name]
    chain: list[dict[str, str]] = []
    while True:
        qualified_name = current.data.get("qualified_name")
        node = scopes[qualified_name]
        end_line = node.end_lineno
        assert end_line is not None
        line = node.lineno
        column = node.col_offset
        evidence_id = stable_id("EVD", "sample/core.py", line, end_line, column, "numeric_scope")
        if not any(item["id"] == evidence_id for item in evidence_rows):
            evidence_rows.append(
                {
                    "id": evidence_id,
                    "file": "sample/core.py",
                    "line": line,
                    "end_line": end_line,
                    "column": column,
                    "excerpt": "\n".join(_SOURCE.splitlines()[line - 1 : end_line]),
                }
            )
        chain.append(
            {
                "scope_owner": qualified_name,
                "scope_evidence_id": evidence_id,
                "scope_symbol_id": current.id,
            }
        )
        if qualified_name == parameter_owner:
            return chain
        parent_id = current.data.get("lexical_parent_id")
        parent = next(item for item in declarations.values() if item.id == parent_id)
        current = parent


def _scope_nodes() -> dict[str, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    result: dict[str, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def visit(node: ast.AST, parent: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                qualified = f"{parent}.{child.name}"
                result[qualified] = child
                visit(child, qualified)
            else:
                visit(child, parent)

    visit(ast.parse(_SOURCE), "sample.core")
    return result


def _tamper_with_outer_receiver(
    payload: dict[str, object],
    donor_id: str,
    target_id: str,
    declarations: dict[str, Record],
) -> str:
    rows = payload["constructs"]
    donor = next(row for row in rows if row["id"] == donor_id)
    target = next(row for row in rows if row["id"] == target_id)
    donor_data = donor["data"]
    target_data = target["data"]
    own_evidence_ids = set(target["evidence_ids"])
    parameter_owner = donor_data["receiver_parameter_owner"]
    receiver_binding = copy.deepcopy(donor_data["receiver_binding"])
    scopes = _scope_chain(target_data["owner"], parameter_owner, declarations, payload["evidence"])
    binding_evidence = sorted(
        set(receiver_binding["evidence_ids"]) | {item["scope_evidence_id"] for item in scopes}
    )
    receiver_binding["evidence_ids"] = binding_evidence
    target_data.update(
        {
            "status": "decided",
            "receiver_type": donor_data["receiver_type"],
            "receiver_parameter": donor_data["receiver_parameter"],
            "receiver_parameter_owner": parameter_owner,
            "receiver_parameter_scopes": scopes,
            "receiver_binding": receiver_binding,
        }
    )
    target["evidence_ids"] = sorted(set(target["evidence_ids"]) | set(binding_evidence))
    own_evidence = next(
        item
        for item in payload["evidence"]
        if item["id"] in own_evidence_ids
        and item["file"] == "sample/core.py"
        and "conn.backend" in item["excerpt"]
    )
    target["id"] = stable_id(
        "CONSTRUCT-SELECTOR",
        "sample/core.py",
        own_evidence["line"],
        own_evidence["column"],
        target_data["selector_role"],
        target_data["receiver_type"],
        target_data.get("member") or "",
        target_data.get("literal") or "",
        target_data["operation"],
    )
    return target["id"]


def _refresh_selector_receipt(payload: dict[str, object]) -> None:
    parsed = parse_observation(payload)
    receipt = next(
        row
        for row in payload["scope_observations"]
        if row["kind"] == "rule_evaluation"
        and any(identity.endswith("SELECT") for identity in row["rule_ids"])
    )
    receipt_data = next(
        row
        for row in parsed.records("scope_observations") or ()
        if row.kind == "rule_evaluation"
        and any(identity.endswith("SELECT") for identity in row.rule_ids)
    )
    proof = receipt["data"]["selector_scope_proof"]
    rule_id = receipt["rule_ids"][0]
    proof["result_digest"] = rule_result_digest(parsed.sections, rule_id)
    proof["binding_id"] = rule_evaluation_binding_id(
        selector_inventory_binding_id(parsed.sections, parsed.evidence),
        receipt_data,
        parsed.schema_version,
    )


def _retarget_to_sibling_owner(
    payload: dict[str, object], target_id: str, declarations: dict[str, Record]
) -> None:
    target = next(row for row in payload["constructs"] if row["id"] == target_id)
    data = target["data"]
    parameter_owner = data["receiver_parameter_owner"]
    sibling_owner = "sample.core.outer.safe_sibling"
    scopes = _scope_chain(sibling_owner, parameter_owner, declarations, payload["evidence"])
    binding = data["receiver_binding"]
    owner_evidence = set(declarations[parameter_owner].evidence_ids)
    owner_evidence.update(declarations[sibling_owner].evidence_ids)
    binding_evidence = set(binding["evidence_ids"])
    binding_evidence.update(owner_evidence)
    binding_evidence.update(item["scope_evidence_id"] for item in scopes)
    binding["evidence_ids"] = sorted(binding_evidence)
    data["owner"] = sibling_owner
    data["receiver_parameter_scopes"] = scopes
    target["evidence_ids"] = sorted(set(target["evidence_ids"]) | binding_evidence)


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
def test_saved_selector_receiver_proof_rejects_lexical_shadow_transplants(
    tmp_path: Path, mounted: bool
) -> None:
    model, _result = _fixture(tmp_path / "repo", mounted=mounted)
    records = [row for row in model.records("constructs") or () if row.kind == "construct_selector"]
    evidence_by_id = {item.id: item for item in model.evidence}
    source_lines = _SOURCE.splitlines()
    return_lines = [
        index + 1
        for index, line in enumerate(source_lines)
        if line.strip() == 'return conn.backend == "flat"'
    ]
    line_for = {
        "captured": return_lines[0],
        "safe_sibling": return_lines[1],
        "local_assignment": return_lines[2],
        "local_import": (
            source_lines.index("        from sample.other import Connection as conn") + 2
        ),
        "global_name": return_lines[4],
        "lambda_shadow": (
            source_lines.index('    lambda_shadow = lambda conn: conn.backend == "flat"') + 1
        ),
        "comprehension_shadow": source_lines.index(
            '    comprehension_shadow = [conn.backend == "flat" for conn in candidates]'
        )
        + 1,
        "class_shadow": source_lines.index('        conn.backend == "flat"') + 1,
    }
    # Resolve target rows by owner as well as source location; several sites share a line shape.
    rows_by_owner = {
        name: next(
            row
            for row in records
            if row.data.get("owner", "").endswith(f".{name}")
            and _selector_line(row, evidence_by_id) == line_for[name]
        )
        for name in (
            "captured",
            "safe_sibling",
            "local_assignment",
            "local_import",
            "global_name",
            "class_shadow",
        )
    }
    donor = rows_by_owner["captured"]
    assert donor.data.get("receiver_binding") is not None
    for name in ("local_assignment", "local_import", "global_name", "class_shadow"):
        assert rows_by_owner[name].data.get("receiver_binding") is None
    lambda_row = next(
        row for row in records if _selector_line(row, evidence_by_id) == line_for["lambda_shadow"]
    )
    comprehension_row = next(
        row
        for row in records
        if _selector_line(row, evidence_by_id) == line_for["comprehension_shadow"]
    )
    assert lambda_row.data.get("receiver_binding") is None
    assert comprehension_row.data.get("receiver_binding") is None
    declarations = {
        row.data.get("qualified_name"): row
        for row in model.records("symbols") or ()
        if isinstance(row.data.get("qualified_name"), str)
    }
    donor_id = donor.id
    target_ids = {
        "local_assignment": rows_by_owner["local_assignment"].id,
        "local_import": rows_by_owner["local_import"].id,
        "global_name": rows_by_owner["global_name"].id,
        "lambda_shadow": lambda_row.id,
        "comprehension_shadow": comprehension_row.id,
        "class_shadow": rows_by_owner["class_shadow"].id,
    }

    for format_name, original in (
        ("ordinary", observation_payload(model)),
        ("columnar", decode_canonical_model(json.loads(canonical_report_bytes(model)))),
    ):
        valid_path = tmp_path / f"valid-{format_name}-{mounted}.json"
        valid_payload = original if format_name == "ordinary" else encode_canonical_model(original)
        valid_path.write_bytes(canonical_json_bytes(valid_payload))
        valid_replay = run_saved_report(valid_path)
        assert not valid_replay.diagnostics, valid_replay.diagnostics
        valid_assessment = next(
            row for row in valid_replay.rule_assessments if row.id.endswith("SELECT")
        )
        assert valid_assessment.status.value == "FAIL"
        for site, target_id in target_ids.items():
            tampered = copy.deepcopy(original)
            _tamper_with_outer_receiver(tampered, donor_id, target_id, declarations)
            _refresh_selector_receipt(tampered)
            parsed = parse_observation(tampered)
            with pytest.raises(
                ValueError,
                match="selector receiver proof|declared selector receiver|saved selector proof",
            ):
                _validate_saved_sources(parsed)
            path = tmp_path / f"{format_name}-{site}-{mounted}.json"
            serialized = tampered if format_name == "ordinary" else encode_canonical_model(tampered)
            path.write_bytes(canonical_json_bytes(serialized))
            replay = run_saved_report(path)
            assert replay.rule_assessments is None
            assert replay.diagnostics

        retargeted = copy.deepcopy(original)
        assignment_id = target_ids["local_assignment"]
        assignment_id = _tamper_with_outer_receiver(
            retargeted, donor_id, assignment_id, declarations
        )
        _retarget_to_sibling_owner(retargeted, assignment_id, declarations)
        _refresh_selector_receipt(retargeted)
        with pytest.raises(ValueError, match="selector|scope|source"):
            _validate_saved_sources(parse_observation(retargeted))
        path = tmp_path / f"{format_name}-owner-retarget-{mounted}.json"
        serialized = retargeted if format_name == "ordinary" else encode_canonical_model(retargeted)
        path.write_bytes(canonical_json_bytes(serialized))
        replay = run_saved_report(path)
        assert replay.rule_assessments is None
        assert replay.diagnostics
