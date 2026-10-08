# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A typed resolver gap may retain honest UML evidence without passing coverage."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from archkeel.analyzer.typescript.collect import collect
from archkeel.check.observe import Observer
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.check.uml import assemble_uml
from archkeel.check.uml_evaluation import evaluate_uml
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionError, CollectionRequest
from archkeel.ir.report_graph import architecture_report


@dataclass(frozen=True)
class _TypeScriptCollector:
    transform: Callable[[SourceFacts], SourceFacts] | None = None
    error: CollectionError | None = None

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        if self.error is not None:
            return self.error
        facts = collect(request)
        return self.transform(facts) if self.transform is not None else facts


def _project(
    root: Path, *, matching: bool = False, rules: list[dict[str, object]] | None = None
) -> tuple[Path, ScanConfig]:
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src/main.ts").write_text(
        "export function load(value: string): number { return 1; }\n"
        "const loader = './lazy';\nimport(loader);\n"
    )
    (root / "src/lazy.ts").write_text("export const value = 1;\n")
    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"module": "NodeNext", "moduleResolution": "NodeNext"},
                "include": ["src/**/*.ts"],
            }
        )
    )
    (root / "docs/target.md").write_text("The app exposes a typed loader.\n")
    expected_annotation, expected_return = (
        ("string", "number") if matching else ("number", "string")
    )
    entities = [
        {
            "id": "main",
            "kind": "module",
            "qualified_name": "demo.src.main_x2e_ts",
            "parent_id": "app",
            "language": "typescript",
            "presence": "planned",
            "responsibilities": ["Own the loader entry point."],
            "provenance": ["docs/target.md"],
            "file_path": "src/main.ts",
        },
        {
            "id": "load",
            "kind": "function",
            "qualified_name": "demo.src.main_x2e_ts.load",
            "parent_id": "main",
            "language": "typescript",
            "presence": "planned",
            "responsibilities": ["Load a value."],
            "provenance": ["docs/target.md"],
            "signature": {
                "parameters": [
                    {
                        "name": "value",
                        "annotation": expected_annotation,
                        "kind": "positional",
                        "default_known": True,
                    }
                ],
                "returns": expected_return,
            },
        },
    ]
    if not matching:
        entities.append(
            {
                "id": "absent",
                "kind": "function",
                "qualified_name": "demo.src.main_x2e_ts.absent",
                "parent_id": "main",
                "language": "typescript",
                "presence": "planned",
                "responsibilities": ["Reserve an unimplemented operation."],
                "provenance": ["docs/target.md"],
            }
        )
    contract = {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "app",
                "label": "app",
                "role": "component",
                "packages": ["demo.src"],
                "namespace": "demo.src",
                "exact_modules": ["demo.src.main_x2e_ts", "demo.src.lazy_x2e_ts"],
                "responsibilities": ["Own the small demo application."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        "rules": rules or [],
        "declarations": {"uml": {"schema_version": "1.0.0", "entities": entities}},
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    for command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "test@example.invalid"),
        ("git", "config", "user.name", "Test"),
        ("git", "add", "-A"),
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return root, ScanConfig(
        ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
    )


def _live(root: Path, config: ScanConfig):
    return run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))


def test_partial_typescript_report_keeps_observed_fail_and_unknown_in_live_and_saved_reports(
    tmp_path: Path, monkeypatch
) -> None:
    root, config = _project(tmp_path / "partial")
    result, encoded = _live(root, config)

    assert result.exit_code == 2
    assert result.coverage is not None and result.coverage.status == "FAIL"
    assert result.diagnostics
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert (
        model.coverage.files_discovered
        == model.coverage.files_read
        == model.coverage.files_parsed
        == 2
    )
    assert architecture_report(model).comparison is not None
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL"
    assert {item.kind for item in model.coverage.failures} == {"source_resolution_gap"}
    receipt = next(
        item
        for item in model.records("scope_observations") or ()
        if item.data.get("comparison") is not None
    )
    assert receipt.data.get("assessment_complete") is False
    assert any(
        item.subject_id == "load" and item.aspect == "signature" and item.status == "FAIL"
        for item in comparison.assessments
    )
    assert any(
        item.subject_id == "absent" and item.aspect == "existence" and item.status == "UNKNOWN"
        for item in comparison.assessments
    )
    assert comparison.status != "PASS"

    saved_path = root / "architecture.json"
    saved_path.write_bytes(encoded)
    monkeypatch.setattr(
        "archkeel.check.uml_evaluation.compare_graphs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("saved reports must not compare")
        ),
    )
    saved = run_saved_report(saved_path)
    assert saved.exit_code == 2
    assert saved.diagnostics
    assert saved.architecture_projection is not None
    uml = next(item for item in saved.rule_assessments or () if item.kind == "uml_target")
    assert uml.status == "FAIL" and not uml.evaluation_proven


def test_partial_all_pass_comparison_is_withheld(tmp_path: Path) -> None:
    root, config = _project(tmp_path / "all-pass", matching=True)
    result, encoded = _live(root, config)

    assert result.exit_code == 2
    assert result.coverage is not None and result.coverage.status == "FAIL"
    assert result.diagnostics
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert architecture_report(model).comparison is None
    assert not any(
        item.data.get("comparison") is not None
        for item in model.records("scope_observations") or ()
    )


def test_syntax_recovery_gap_blocks_partial_uml_even_when_parsed_counts_are_full(
    tmp_path: Path,
) -> None:
    root, config = _project(tmp_path / "syntax")
    (root / "src/main.ts").write_text("export function load( {\n")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True)
    subprocess.run(
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "syntax"),
        cwd=root,
        check=True,
        capture_output=True,
    )
    result, encoded = _live(root, config)

    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert (
        model.coverage.files_discovered
        == model.coverage.files_read
        == model.coverage.files_parsed
        == 2
    )
    assert any(item.kind == "collection_gap" for item in model.records("unknowns") or ())
    assert architecture_report(model).comparison is None


def test_runtime_and_rule_failures_mixed_with_resolution_gap_block_partial_uml(
    tmp_path: Path,
) -> None:
    rule = {
        "id": "boundary",
        "kind": "boundary_types",
        "source": "demo.src.main_x2e_ts",
        "rationale": "Keep public types within the declared boundary.",
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    root, config = _project(tmp_path / "rule", rules=[rule])
    result, encoded = _live(root, config)
    assert result.exit_code == 2 and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert model.coverage.rules == "FAIL"
    assert architecture_report(model).comparison is None

    root, config = _project(tmp_path / "runtime")

    def runtime_failure(facts: SourceFacts) -> SourceFacts:
        return replace(facts, runtime=replace(facts.runtime, version="0.0.1"))

    result, encoded = run_report(
        root, config=config, analyzer=Observer(_TypeScriptCollector(transform=runtime_failure))
    )
    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert model.coverage.status == "FAIL"
    assert architecture_report(model).comparison is None


def test_collection_failure_and_malformed_source_facts_never_emit_partial_uml(
    tmp_path: Path,
) -> None:
    root, config = _project(tmp_path / "collection-error")
    result, encoded = run_report(
        root,
        config=config,
        analyzer=Observer(
            _TypeScriptCollector(error=CollectionError("execution_error", "collector", "failed"))
        ),
    )
    assert result.exit_code == 2 and encoded is None

    root, config = _project(tmp_path / "malformed")

    def malformed_counts(facts: SourceFacts) -> SourceFacts:
        return replace(facts, coverage=replace(facts.coverage, files_read=100))

    result, encoded = run_report(
        root, config=config, analyzer=Observer(_TypeScriptCollector(transform=malformed_counts))
    )
    assert result.exit_code == 2 and result.diagnostics and encoded is None

    root, config = _project(tmp_path / "malformed-evidence")

    def unbound_evidence(facts: SourceFacts) -> SourceFacts:
        evidence = (replace(facts.evidence[0], file="outside.ts"), *facts.evidence[1:])
        return replace(facts, evidence=evidence)

    result, encoded = run_report(
        root,
        config=config,
        analyzer=Observer(_TypeScriptCollector(transform=unbound_evidence)),
    )
    assert result.exit_code == 2 and result.diagnostics and encoded is None


def test_missing_selected_input_and_git_failure_block_partial_uml(tmp_path: Path) -> None:
    root, config = _project(tmp_path / "missing-input")

    def missing_selected_input(facts: SourceFacts) -> SourceFacts:
        return replace(
            facts,
            inputs=tuple(
                item
                for item in facts.inputs
                if item.role != "selected" or item.path != "src/lazy.ts"
            ),
        )

    result, encoded = run_report(
        root,
        config=config,
        analyzer=Observer(_TypeScriptCollector(transform=missing_selected_input)),
    )
    assert result.exit_code == 2 and result.diagnostics and encoded is None

    root, config = _project(tmp_path / "git")
    result = Observer(_TypeScriptCollector())(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="unknown",
        dirty="unknown",
        contract_root=root,
        language="typescript",
    )
    result = evaluate_uml(assemble_uml(result, root, config.contract))
    assert result.diagnostics and result.observation is not None
    assert architecture_report(result.observation).comparison is None


def test_target_digest_change_revokes_partial_eligibility(tmp_path: Path) -> None:
    root, config = _project(tmp_path / "target-digest")
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    result = Observer(_TypeScriptCollector())(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=commit,
        dirty=False,
        contract_root=root,
        language="typescript",
    )
    (root / config.contract).write_text((root / config.contract).read_text() + "\n")

    result = evaluate_uml(assemble_uml(result, root, config.contract))

    assert any(item.code == "contract.invalid" for item in result.diagnostics)
    assert result.observation is not None
    assert architecture_report(result.observation).comparison is None


def test_incomplete_nested_contract_never_enables_partial_uml(tmp_path: Path) -> None:
    root, config = _project(tmp_path / "nested")
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_text())
    contract["components"][0]["inside"] = "missing.json"
    contract_path.write_text(json.dumps(contract))
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True)
    subprocess.run(
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "nested"),
        cwd=root,
        check=True,
        capture_output=True,
    )

    result, encoded = _live(root, config)

    assert result.exit_code == 2 and result.diagnostics and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert model.coverage.status == "FAIL"
    assert architecture_report(model).comparison is None
