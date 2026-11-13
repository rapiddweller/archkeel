# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call argument rules bind written actuals to canonical formal parameters."""

import json
from pathlib import Path

from test_exact_module_ownership import _component

from archkeel.cli.observe import observe
from archkeel.ir.decisions import rule_assessments

_PROVENANCE = ["docs/architecture/sample.md"]


def _selector_rule():
    return {
        "id": "SELECT-PAGE",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {"receiver": "sample.storage.Storage", "member": "page", "role": "call"},
        "rationale": "Selector facts are only collected for a declared selector rule.",
        "provenance": _PROVENANCE,
        "decided_by": "architect",
    }


def _contract(
    *, source="sample.caller", target="sample.storage.page", parameter="query", selector=False
):
    return {
        "schema_version": "3.11.0" if selector else "3.10.0",
        "components": [
            {
                "id": "COMP-SAMPLE",
                "label": "sample",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own the synthetic sample."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
            }
        ],
        "rules": [
            {
                "id": "FORBID-QUERY-LITERAL",
                "kind": "forbidden_call_argument",
                "source": source,
                "target": target,
                "parameter": parameter,
                "rationale": "Query text must come from the selected typed argument.",
                "provenance": _PROVENANCE,
                "decided_by": "architect",
            },
            *([_selector_rule()] if selector else []),
        ],
    }


def _observe(
    tmp_path: Path,
    caller: str,
    *,
    storage: str | None = None,
    mounted: bool = False,
    source: str = "sample.caller",
    target: str = "sample.storage.page",
    parameter: str = "query",
    selector: bool = False,
):
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Synthetic decision.\n",
        "contract.json": json.dumps(
            _contract(source=source, target=target, parameter=parameter, selector=selector)
        ),
        "sample/__init__.py": "",
        "sample/storage.py": storage
        or ("class QuerySpec: pass\ndef page(query: QuerySpec, label: str = '') -> None: pass\n"),
        "sample/caller.py": caller,
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    contract = _contract(source=source, target=target, parameter=parameter, selector=selector)
    if mounted:
        (tmp_path / "inside.json").write_text(json.dumps(contract))
        contract = {
            "schema_version": "3.11.0" if selector else "3.10.0",
            "components": [_component("sample", ["sample"], inside="inside.json")],
            "rules": [],
        }
        (tmp_path / "contract.json").write_text(json.dumps(contract))
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.kind == "forbidden_call_argument"
    ]
    return result, row


def test_argument_rule_is_admitted_only_by_contract_3_10_schema():
    from test_result_schema import _validator

    validator = _validator("command-result-9.0.schema.json")
    payload = _contract()
    current = validator.evolve(schema={"$ref": "urn:archkeel:architecture-contract:3.10.0"})
    historical = validator.evolve(schema={"$ref": "urn:archkeel:architecture-contract:3.9.0"})
    assert current.is_valid(payload)
    payload["schema_version"] = "3.9.0"
    assert not historical.is_valid(payload)
