# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Core UML findings use the existing rule/fact/source evidence chain."""

import json

from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import validate_evidence_classes


def _contract():
    context = {"presence": "planned", "language": "python", "provenance": ["docs/target.md"]}
    return {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "core",
                "label": "core",
                "role": "component",
                "packages": ["sample.core"],
                "namespace": "sample.core",
                "responsibilities": ["Own operations."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        ],
        "rules": [],
        "declarations": {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        **context,
                        "id": "module",
                        "kind": "module",
                        "qualified_name": "sample.core",
                        "parent_id": "core",
                        "responsibilities": ["Own the module."],
                    },
                    {
                        **context,
                        "id": "run",
                        "kind": "function",
                        "qualified_name": "sample.core.run",
                        "parent_id": "module",
                        "responsibilities": ["Delegate a request."],
                        "visibility": {"kind": "public", "basis": "declared"},
                        "signature": {
                            "parameters": [
                                {"name": "value", "kind": "positional", "default_known": True}
                            ]
                        },
                    },
                    {
                        **context,
                        "id": "helper",
                        "kind": "function",
                        "qualified_name": "sample.core.helper",
                        "parent_id": "module",
                        "responsibilities": ["Return a value."],
                    },
                ],
                "relationships": [
                    {
                        "id": "call",
                        "kind": "calls",
                        "source_id": "run",
                        "target_id": "helper",
                        "provenance": ["docs/target.md"],
                    }
                ],
            }
        },
    }


def _repository(tmp_path, *, contract=None, source=None):
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": source
            or (
                "def helper(value):\n    return value\n"
                "\ndef run(value):\n    return helper(value)\n"
            ),
            "contract.json": json.dumps(contract or _contract()),
            "docs/target.md": "Own the module and delegate run to helper.\n",
        },
    )
    return root, ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    validate_evidence_classes(model)
    return model


def _uml_rule(model):
    return next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )
