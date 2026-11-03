# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Command preparation keeps legacy imports and the recorded wire representation."""

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, replace

import pytest

from archkeel.ir.architecture_graph import ComponentRole
from archkeel.ir.architecture_projection import (
    ArchitectureProjection,
    ComponentProjection,
    ModuleProjection,
    PermissionProjection,
    RequiredRelationshipProjection,
    RequiresProjection,
    UnknownProjection,
)
from archkeel.ir.codec import result_bytes
from archkeel.ir.command_view import architecture_command_envelope
from archkeel.ir.facts import SourceInfo
from archkeel.ir.model import BaselineViolationComparison, ReportFilter, RunResult


def _recorded_result(*, full=False, selected=None):
    component = ComponentProjection(
        id="CORE",
        scope="core:inner",
        label="inner",
        parent_id="PARENT",
        role=ComponentRole.COMPONENT,
        path="src/sample/core",
        provenance=("docs/target.md",),
        namespace="sample.core",
        packages=("sample.core", "sample.core_extra"),
        exact_modules=("sample.core.child",),
        responsibilities=("Own core work.",),
        not_responsible_for=(),
        public=("sample.core:API", "sample.core.child:Nested", "sample.other"),
        planned=None,
        modules=(
            ModuleProjection("sample.core", "src/sample/core"),
            ModuleProjection("sample.core.child", "src/sample/core/child.py"),
            ModuleProjection("sample.core_extra", "src/sample/core_extra.py"),
        ),
        requires=(
            RequiresProjection("REQUIRES", "STORE", ("sample.store",), "Persist.", "architect", 2),
        ),
        permissions=(
            PermissionProjection("STORE", "allowed", ("REQUIRES", "ALLOW"), "Declared."),
            PermissionProjection("OTHER", "forbidden", ("REQUIRES", "DENY"), "Blocked."),
            PermissionProjection("PEER", "undecided", (), "No decision."),
        ),
        used_by=(),
        finding_ids=("HIDDEN",),
        status="UNKNOWN",
        reason="No decision.",
        decided_by="architect",
        selector_prefix="sample.core",
    )
    required = RequiredRelationshipProjection(
        "INTERNAL",
        "references",
        "CLASS-A",
        "sample.core.A",
        "CLASS-B",
        "sample.core.B",
        "UNKNOWN",
        ("No Core evidence.",),
        ("CORE",),
        "core:inner",
    )
    projection = ArchitectureProjection(
        source=SourceInfo("a" * 40, False, "b" * 64, ("src",)),
        contract_digest="c" * 64,
        analyzer_digest="d" * 64,
        components=(component,),
        levels=(),
        permission_rules=(),
        required_relationships=(
            required,
            replace(required, id="INTERNAL-2"),
            replace(required, id="EXTERNAL", target_id="PEER", internal_scope=None),
        ),
        ownership_gaps=(),
        unknowns=(
            UnknownProjection("U2", "Missing evidence.", kind="coverage", scopes=("other",)),
            UnknownProjection("U1", "Missing evidence.", kind="coverage", scopes=("core:inner",)),
            UnknownProjection("U3", "Missing evidence.", kind="coverage", scopes=("core:inner",)),
        ),
        status="UNKNOWN",
        reason="Missing evidence.",
        violation_remedy="Review the recorded evidence.",
        policy_context=(replace(component, id="CONTEXT", reason="Context only."),),
    )
    return RunResult(
        "report",
        1,
        declared_rules="FAIL",
        architecture_projection=projection,
        report_filter=ReportFilter(
            only_architecture=True, full_architecture=full, component=selected
        ),
        filtered_violations=(),
        baseline_path="baseline.json",
        baseline_comparisons=(
            BaselineViolationComparison(("DENY",), ("CORE",), 1, 0, 0, 0, 1, "resolved"),
        ),
        baseline_new=0,
        baseline_resolved=1,
    )


@pytest.mark.parametrize(
    "full,selected,digest",
    [
        (False, None, "2c0b58f9a4e3a0aa1f106cf091f133a3657de8d0f6842cb1249204e8ebb4f9c0"),
        (True, None, "bacbcd698b3d0acf979d3b4e6b0d7525f1faffa15d77be8330bbd9ae6f26a64e"),
        (False, "core:inner", "8a07b2a4bd28de35ec154de9f6d0400712b39a6577d4c317ce6215fbcf49ea49"),
    ],
    ids=("compact", "full", "component"),
)
def test_recorded_command_bytes(full, selected, digest):
    # Captured from the original owner before the responsibility extraction.
    encoded = result_bytes(_recorded_result(full=full, selected=selected))
    assert hashlib.sha256(encoded).hexdigest() == digest


def test_command_reasons_permissions_scopes_and_selector_negative_controls():
    result = _recorded_result(full=True)
    envelope = architecture_command_envelope(result)
    view = envelope.architecture_projection
    assert view.reasons == ("Declared.", "Blocked.", "No decision.")
    (component,) = view.components
    assert component.reason == 2
    assert [(row.status, row.rule_ids, row.reason) for row in component.permissions] == [
        ("allowed", ("ALLOW",), 0),
        ("forbidden", ("REQUIRES", "DENY"), 1),
        ("undecided", (), 2),
    ]
    assert component.packages == ("", "sample.core_extra")
    assert component.modules == {
        "": "",
        ".child": "child.py",
        "sample.core_extra": "src/sample/core_extra.py",
    }
    assert component.public == {"": ("API",), ".child": ("Nested",), "sample.other": ("",)}
    assert component.planned is None and component.finding_ids == ()
    assert view.unknowns == {
        "coverage": {"Missing evidence.": ((("core:inner",), 2), (("other",), 1))}
    }
    assert [row.id for row in view.required_relationships] == ["EXTERNAL"]
    assert [asdict(row) for row in view.required_summaries] == [
        {
            "scope": "core:inner",
            "kind": "references",
            "status": "UNKNOWN",
            "reasons": ("No Core evidence.",),
            "count": 2,
        }
    ]
    assert asdict(envelope)["baseline_comparisons"] == tuple(
        asdict(row) for row in result.baseline_comparisons
    )
    assert json.loads(result_bytes(result))["declared_rules"] == "FAIL"
    with pytest.raises(ValueError, match="requires its authenticated projection"):
        architecture_command_envelope(replace(result, architecture_projection=None))


@pytest.mark.parametrize(
    "first",
    ["command_view", "report_projection", "codec", "model"],
)
def test_type_hints_survive_eager_import_orders(first):
    script = """
import importlib
import sys
from dataclasses import is_dataclass
from inspect import isfunction
from typing import get_type_hints

first = sys.argv[1]
importlib.import_module("archkeel.ir." + first)
if first in {"command_view", "codec"}:
    assert "archkeel.ir.report_projection" not in sys.modules
    assert "archkeel.ir.report_graph" not in sys.modules
from archkeel.ir import command_view, report_projection
from archkeel.ir import codec, model
names = (
    "PermissionGroup", "ScopeCount", "UnknownGroups", "ArchitectureComponentView",
    "PermissionContextView", "RequiredRelationshipSummary", "ArchitectureCommandView",
    "ArchitectureCommandEnvelope", "short_selector", "grouped_selectors", "unknown_groups",
    "architecture_command_envelope",
)
for name in names:
    current = getattr(command_view, name)
    if is_dataclass(current) or isfunction(current):
        get_type_hints(current)
assert get_type_hints(command_view.architecture_command_envelope)["result"] is model.RunResult
envelope_hints = get_type_hints(command_view.ArchitectureCommandEnvelope)
assert envelope_hints["architecture_projection"] is command_view.ArchitectureCommandView
"""
    subprocess.run(
        [sys.executable, "-c", script, first], check=True, capture_output=True, text=True
    )
