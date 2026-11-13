# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep the authored profile-port intent fixed while observed annotations are widened."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "port,old,new,aspect",
    [
        (
            "optional_sections",
            "optional_sections: frozenset[ObservedSection]",
            "optional_sections: frozenset[object]",
            "annotation",
        ),
        (
            "additional_optional_section_groups",
            "additional_optional_section_groups: tuple[frozenset[ObservedSection], ...]",
            "additional_optional_section_groups: tuple[object, ...]",
            "annotation",
        ),
        (
            "optional_section_groups",
            "def optional_section_groups(self) -> tuple[frozenset[ObservedSection], ...]:",
            "def optional_section_groups(self) -> tuple[object, ...]:",
            "signature",
        ),
        (
            "all_optional_sections",
            "def all_optional_sections(self) -> frozenset[ObservedSection]:",
            "def all_optional_sections(self) -> frozenset[object]:",
            "signature",
        ),
    ],
)
@pytest.mark.parametrize("widened", [False, True], ids=["declared-port", "widened-port"])
def test_native_profile_receipt_ports_use_fixed_authored_intent(
    tmp_path, port, old, new, aspect, widened
):
    declared = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_bytes())
    component = next(row for row in declared["components"] if row["id"] == "TARGET-PROFILES")
    component.pop("requires")
    wanted = {"IR-MODULE-OBJECT-profiles", "IR-MODULE-OBJECT-Profile", f"IR-PROFILE-{port}"}
    contract = {
        "schema_version": declared["schema_version"],
        "components": [component],
        "rules": [],
        "declarations": {
            "uml": {
                "schema_version": "1.1.0",
                "entities": [
                    row
                    for row in declared["declarations"]["uml"]["entities"]
                    if row["id"] in wanted
                ],
                "relationships": [],
            }
        },
    }
    source = (ROOT / "src/archkeel/ir/profiles.py").read_text()
    assert old in source
    if widened:
        source = source.replace(old, new, 1)
    paths = {
        "docs/architecture/language-adapter-target.md",
        "docs/architecture/module-object-grants.md",
        "docs/architecture/typescript-written-string-controls.md",
    }
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/profiles.py": source,
            "contract.json": json.dumps(contract),
            **{path: (ROOT / path).read_text() for path in paths},
        },
    )
    before = (root / "contract.json").read_bytes()
    model = _model(root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64))
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assessments = [
        row
        for row in comparison.assessments
        if row.subject_id == f"IR-PROFILE-{port}" and row.aspect == aspect
    ]
    assert len(assessments) == 1 and assessments[0].status == ("FAIL" if widened else "PASS")
    if widened:
        assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == before
