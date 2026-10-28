# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard library demo gets the same verdicts on every supported Python (issue #724)."""

import json
import subprocess

import pytest
from test_runtime import ROOT, _fixture, _interpreter, _report

from archkeel.ir.codec import decode_canonical_model, parse_observation

FIXTURE = ROOT / "fixtures/python-stdlib-demo"

# Each facade parameter is an external type; the stdlib bindings decide the routes and decorator.
EXPECTED_UNKNOWNS = [
    ("boundary_type_limit", "STDLIB-TYPES-DECLARED decided 1 of 4 declared facade type positions"),
    ("boundary_type_position", "sample.api.first_lines path: external_type"),
    ("boundary_type_position", "sample.api.opened path: external_type"),
    ("boundary_type_position", "sample.api.opened return: external_type"),
]


@pytest.mark.parametrize("minor", [11, 12, 13, 14])
def test_stdlib_demo_verdicts_do_not_depend_on_the_python_version(tmp_path, minor):
    try:
        _interpreter(minor)
    except subprocess.CalledProcessError:
        pytest.skip(f"Python 3.{minor} is not installed")
    root = _fixture(tmp_path, FIXTURE)
    code, result = _report(minor, root)
    assert result["python_version"].startswith(f"3.{minor}.")
    assert code == 0, result["diagnostics"]
    [rule] = result["rule_assessments"]
    assert (rule["id"], rule["status"], rule["undecided"]) == ("STDLIB-TYPES-DECLARED", "PASS", 0)
    observation = parse_observation(
        decode_canonical_model(json.loads((root / "architecture.json").read_bytes()))
    )
    unknowns = sorted(
        (record.kind, record.title)
        for record in observation.records("unknowns") or ()
        if "STDLIB-TYPES-DECLARED" in record.rule_ids
    )
    assert unknowns == EXPECTED_UNKNOWNS
