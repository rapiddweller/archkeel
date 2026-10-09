# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A proven missing external superclass can keep honest UML comparison partial."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dart_native_helpers import collect_native_dart

from archkeel.check.observe import Observer
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionError, CollectionRequest
from archkeel.ir.report_graph import architecture_report


class _DartCollector:
    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        return collect_native_dart(request)


def _project(root: Path, source: str, *, nested_outside: bool = False) -> tuple[Path, ScanConfig]:
    (root / "lib").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )
    (root / "lib/main.dart").write_text(source, encoding="utf-8")
    (root / "docs/target.md").write_text("The Child constructor forwards an inherited key.\n")
    contract = {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "app",
                "label": "app",
                "role": "component",
                "packages": ["commerce"],
                "namespace": "commerce",
                "exact_modules": ["commerce.main"],
                "responsibilities": ["Own the source example."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        "rules": [],
        "declarations": {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        "id": "main",
                        "kind": "module",
                        "qualified_name": "commerce.main",
                        "parent_id": "app",
                        "language": "dart",
                        "presence": "planned",
                        "responsibilities": ["Own the Child declaration."],
                        "provenance": ["docs/target.md"],
                        "file_path": "lib/main.dart",
                    },
                    {
                        "id": "child",
                        "kind": "class",
                        "qualified_name": "commerce.main.Child",
                        "parent_id": "main",
                        "language": "dart",
                        "presence": "planned",
                        "responsibilities": ["Forward superclass constructor arguments."],
                        "provenance": ["docs/target.md"],
                    },
                    {
                        "id": "child-constructor",
                        "kind": "method",
                        "qualified_name": "commerce.main.Child.Child",
                        "parent_id": "child",
                        "language": "dart",
                        "presence": "planned",
                        "responsibilities": ["Construct a Child with an inherited key."],
                        "provenance": ["docs/target.md"],
                        "signature": {
                            "parameters": [
                                {
                                    "name": "key",
                                    "annotation": "String",
                                    "kind": "keyword_only",
                                    "default_known": True,
                                }
                            ],
                            "returns": "Child",
                        },
                    },
                ],
            }
        },
    }
    if nested_outside:
        contract["components"][0]["inside"] = "contracts/feature.json"
        (root / "contracts").mkdir()
        (root / "contracts/feature.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.2.0",
                    "components": [
                        {
                            "id": "feature",
                            "label": "feature",
                            "role": "component",
                            "packages": ["outside"],
                            "namespace": "outside",
                            "exact_modules": ["outside.feature"],
                            "responsibilities": ["Claim a nested source boundary."],
                            "forbidden_responsibilities": [],
                            "provenance": ["docs/target.md"],
                            "decided_by": "architect",
                        }
                    ],
                    "rules": [],
                }
            ),
            encoding="utf-8",
        )
    (root / "architecture-contract.json").write_text(json.dumps(contract), encoding="utf-8")
    for command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "test@example.invalid"),
        ("git", "config", "user.name", "Test"),
        ("git", "add", "-A"),
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return root, ScanConfig(
        ("lib",), "commerce", "architecture-contract.json", "unused", language="dart"
    )


def _report(root: Path, config: ScanConfig):
    return run_report(root, config=config, analyzer=Observer(_DartCollector()))


def test_missing_superclass_report_keeps_coverage_fail_and_partial_unknown_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    root, config = _project(
        tmp_path / "partial",
        "class Child extends MissingParent {\n  Child({super.key});\n}\n",
    )
    result, encoded = _report(root, config)

    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    assert result.coverage is not None and result.coverage.status == "FAIL"
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert (
        model.coverage.files_discovered
        == model.coverage.files_read
        == model.coverage.files_parsed
        == 1
    )
    assert model.coverage.rules == "PASS"
    assert {item.kind for item in model.coverage.failures} == {"source_resolution_gap"}
    report = architecture_report(model)
    assert report.comparison is not None and report.comparison.status == "UNKNOWN"
    assert any(
        item.subject_id == "child-constructor"
        and item.aspect == "signature"
        and item.status == "UNKNOWN"
        for item in report.comparison.assessments
    )
    receipt = next(
        item
        for item in model.records("scope_observations") or ()
        if item.data.get("comparison") is not None
    )
    assert receipt.data.get("assessment_complete") is False

    saved_path = root / "architecture.json"
    saved_path.write_bytes(encoded)
    monkeypatch.setattr(
        "archkeel.check.uml_evaluation.compare_graphs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("saved reports must not compare again")
        ),
    )
    saved = run_saved_report(saved_path)
    assert saved.exit_code == 2 and saved.diagnostics
    saved_uml = next(item for item in saved.rule_assessments or () if item.kind == "uml_target")
    assert saved_uml.status == "UNKNOWN" and not saved_uml.evaluation_proven


def test_unresolved_super_gap_does_not_hide_resolved_parent_parameter_gap(tmp_path: Path) -> None:
    root, config = _project(
        tmp_path / "mixed",
        """class Child extends MissingParent { Child({super.key}); }
class Parent { Parent({required String other}); }
class ResolvedChild extends Parent { ResolvedChild({super.key}); }
""",
    )
    result, encoded = _report(root, config)

    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert {item.kind for item in model.coverage.failures} == {
        "source_resolution_gap",
        "UnsupportedParameter",
    }
    assert architecture_report(model).comparison is None


def test_unresolved_super_gap_does_not_hide_wrong_nested_target_ownership(tmp_path: Path) -> None:
    root, config = _project(
        tmp_path / "nested",
        "class Child extends MissingParent { Child({super.key}); }\n",
        nested_outside=True,
    )
    result, encoded = _report(root, config)

    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert any(item.kind == "inside_source_domain_incomplete" for item in model.coverage.failures)
    assert architecture_report(model).comparison is None
