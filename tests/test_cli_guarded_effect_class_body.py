# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native rule cannot prove a guard after an eager class-body mutation."""

import json
from pathlib import Path

from test_cli_native_python_imports import RULE, project, rows, verdict


def test_class_body_guard_mutation_is_unknown(release_core: Path, tmp_path: Path) -> None:
    source = """\
import secrets

class Generator:
    def __init__(self):
        self.seeded = True

    def generate(self):
        if self.seeded:
            class Local:
                self.seeded = False
            return secrets.token_hex(8)
"""
    rule = {
        **RULE,
        "id": "GUARDED-EFFECT",
        "kind": "forbidden_effect_under_condition",
        "source": "app.client",
        "target": "secrets.token_hex",
        "condition": {"kind": "member", "owner": "app.client.Generator", "name": "seeded"},
    }
    root = project(
        tmp_path,
        {"src/app/__init__.py": "", "src/app/client.py": source},
        contract_rules=[rule],
    )
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = "3.18.0"
    contract_path.write_text(json.dumps(contract))

    result = verdict(release_core, root)

    assert result["status"] == "UNKNOWN", result
    assert rows(result).get("GUARDED-EFFECT") != "PASS", result
    assert "rule_kind_not_ported" in json.dumps(result), result
