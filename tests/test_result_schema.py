# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Published command results describe real CLI output, including failed observations."""

import copy
import json
import os
import shlex
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from typing import get_args

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from archkeel.check.delta import SUPPORTED_DIMENSIONS
from archkeel.ir.model import DiagnosticCode, DiagnosticKind, RunResult
from fixtures.architecture_demo import CATALOG, materialized_fixture

ROOT = Path(__file__).parents[1]
VERDICTS = ("observation_complete", "declared_rules", "expectation_fulfilled")


def _incomplete_check(demo: Path) -> dict:
    root = demo / "C"
    origin = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=root, text=True
    ).strip()
    assert origin == str(demo / "C-origin.git")
    (root / "sample/broken.py").write_text("def broken(\n")
    for args in (
        ("add", "."),
        ("commit", "-qm", "Break the fixture parser"),
        ("push", "-q", "origin", "candidate"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    commands = [
        shlex.split(item["command"]) for item in json.loads((demo / "commands.json").read_bytes())
    ]
    args = next(
        args
        for args in commands
        if args[1] == "check" and args[args.index("--root") + 1] == str(root)
    )
    args[args.index("--head") + 1] = head
    host = Path(args[args.index("--host-records") + 1])
    events = json.loads(host.read_bytes())
    events[-1]["sha"] = head
    host.write_text(json.dumps(events))
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode == 2, (run.stdout, run.stderr)
    payload = json.loads(run.stdout)
    assert payload["command"] == "check" and payload["observation"] is not None
    return payload


def _open_decision_results(root: Path, output: Path) -> dict[str, dict]:
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract["rules"] = [
        rule
        for rule in contract["rules"]
        if rule["kind"] not in {"complete_requires", "allowed_dependency", "forbidden_dependency"}
    ]
    payloads = {}
    for mode in ("known", "unavailable"):
        if mode == "unavailable":
            component = next(item for item in contract["components"] if item["label"] == "app")
            component["packages"] = []
            del component["namespace"]
            component["exact_modules"] = ["shop.app.orders"]
        path.write_text(json.dumps(contract))
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "archkeel.cli",
                "report",
                "--root",
                str(root),
                "--output",
                str(output / f"open-{mode}.json"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        payload = json.loads(run.stdout)
        assert run.returncode == 0, (payload["diagnostics"], run.stderr)
        assert payload["open_decisions"]
        if mode == "known":
            assert all(item["options"] for item in payload["open_decisions"])
        else:
            assert any("options_unavailable_reason" in item for item in payload["open_decisions"])
        payloads[f"open-{mode}-report"] = payload
    return payloads


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = json.loads((ROOT / "schema/command-result.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry)


def test_command_coverage_distinguishes_unmeasured_from_mixed_call_counts(validator) -> None:
    coverage = json.loads(
        (ROOT / "schema/architecture-ir-python-decoded.schema.json").read_bytes()
    )["properties"]["coverage"]
    payload = {
        "status": "PASS",
        "files_discovered": 1,
        "files_read": 1,
        "files_parsed": 1,
        "ast_coverage_percent": 100,
        "failures": [],
        "rules": "PASS",
        **dict.fromkeys(
            (
                "calls_analyzed",
                "calls_resolved",
                "calls_partially_resolved",
                "calls_unresolved",
                "call_resolution_percent",
            )
        ),
    }
    neutral = validator.evolve(schema=validator.schema["properties"]["coverage"])
    assert neutral.is_valid(payload)
    payload["calls_analyzed"] = 0
    assert not neutral.is_valid(payload)
    assert not validator.evolve(schema=coverage).is_valid(payload)


def test_python_decoded_schema_accepts_producer_and_legacy_omission(results) -> None:
    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema_paths = (
        ROOT / "schema/architecture-ir-decoded.schema.json",
        ROOT / "schema/architecture-ir-python-decoded.schema.json",
    )
    observations = [
        payload["observation"]
        for payload in results.values()
        if isinstance(payload.get("observation"), dict)
        and payload["observation"]["analyzer"]["name"] == "archkeel-python-analyzer"
    ]
    assert observations
    current = observations[0]
    assert "producer" in current
    legacy = {key: value for key, value in current.items() if key != "producer"}

    for path in schema_paths:
        schema = json.loads(path.read_bytes())
        decoded = Draft202012Validator(schema, registry=registry)
        assert not list(decoded.iter_errors(current))
        assert not list(decoded.iter_errors(legacy))


def test_decoded_typescript_schema_preserves_unmeasured_call_availability() -> None:
    from test_nullable_profile_measurements import _profile_model

    from archkeel.ir.codec import observation_payload, parse_observation

    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = json.loads((ROOT / "schema/architecture-ir-decoded.schema.json").read_bytes())
    decoded = Draft202012Validator(schema, registry=registry)
    payload = observation_payload(parse_observation(_profile_model("archkeel-typescript-imports")))
    assert not list(decoded.iter_errors(payload))
    payload["coverage"].update(
        calls_analyzed=0,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
        call_resolution_percent=0,
    )
    assert not decoded.is_valid(payload)


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict]:
    output = tmp_path_factory.mktemp("json-result-demos")
    demo = output / "check"
    make_env = {**os.environ, "MAKELEVEL": "1", "MAKEFLAGS": "w"}
    run = subprocess.run(
        ["make", "--no-print-directory", "demo", f"OUTPUT={demo}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=make_env,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    payloads = {path.stem: json.loads(path.read_bytes()) for path in demo.glob("*.stdout.json")}
    payloads["parse-check"] = _incomplete_check(demo)
    for variant, expected in (
        ("clean", 0),
        ("tour", 2),
        ("validation-parse-error", 2),
        ("validation-measurement-budget-rise", 2),
        ("validation-facade-budget-clean", 0),
        ("class-a-boundary-types-contained-mapping-unknown", 0),
        ("ownership-exact-module-positive", 0),
        ("dart-clean", 0),
    ):
        run = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "demo-architecture",
                f"VARIANT={variant}",
                f"OUTPUT={output / variant}.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=make_env,
        )
        assert run.returncode == expected, (run.stdout, run.stderr)
        for payload in (json.loads(line) for line in run.stdout.splitlines()):
            payloads[f"{variant}-{payload['command']}"] = payload
    for command in ("check", "validate", "report"):
        args = [command, "--root", str(output), "--json"]
        if command == "check":
            args.extend(
                [
                    "--baseline",
                    "0" * 40,
                    "--expectation-commit",
                    "0" * 40,
                    "--head",
                    "0" * 40,
                    "--expected",
                    "expectation.json",
                    "--expected-digest",
                    "0" * 64,
                    "--branch",
                    "candidate",
                    "--accepted-branch",
                    "main",
                ]
            )
        run = subprocess.run(
            [sys.executable, "-m", "archkeel.cli", *args],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 2, (run.stdout, run.stderr)
        payloads[f"invalid-{command}"] = json.loads(run.stdout)
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    with materialized_fixture(tour) as root:
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "archkeel.cli",
                "report",
                "--root",
                str(root),
                "--only",
                "violations",
                "--output",
                str(output / "filtered.json"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, (run.stdout, run.stderr)
        payloads["filtered-report"] = json.loads(run.stdout)
        payloads.update(_open_decision_results(root, output))
    return payloads


def test_real_cli_demo_results_match_the_published_schema(validator, results) -> None:
    for name, payload in results.items():
        errors = list(validator.iter_errors(payload))
        assert not errors, (name, [(list(error.path), error.message) for error in errors])
    assert results["C-check.stdout"]["expectation_fulfilled"] == "PASS"
    assert results["A-check.stdout"]["expectation_fulfilled"] == "FAIL"
    assert results["B-missing-host.stdout"]["expectation_fulfilled"] == "UNKNOWN"
    assert results["tour-report"]["exit_code"] == 0
    assert results["tour-report"]["declared_rules"] == "FAIL"
    assert results["validation-measurement-budget-rise-validate"]["exit_code"] == 1
    assert (
        results["class-a-boundary-types-contained-mapping-unknown-report"]["declared_rules"]
        == "UNKNOWN"
    )


def test_result_properties_cover_the_writer(validator) -> None:
    assert set(validator.schema["properties"]) == {field.name for field in fields(RunResult)}
    diagnostic = validator.schema["$defs"]["diagnostic"]["properties"]
    assert set(diagnostic["kind"]["enum"]) == set(get_args(DiagnosticKind))
    assert set(diagnostic["code"]["enum"]) == set(get_args(DiagnosticCode))


@pytest.mark.parametrize("field", VERDICTS)
@pytest.mark.parametrize("value", [None, "", "SUPPORTED", [], 0])
def test_verdicts_cannot_be_missing_or_malformed(validator, results, field, value) -> None:
    payload = copy.deepcopy(results["clean-report"])
    payload[field] = value
    assert not validator.is_valid(payload)
    del payload[field]
    assert not validator.is_valid(payload)


@pytest.mark.parametrize("command", ["check", "validate", "report"])
def test_unknown_requires_diagnostic_evidence(validator, results, command) -> None:
    payload = copy.deepcopy(results[f"invalid-{command}"])
    for field in ("kind", "subject", "unknown_claim", "remedy"):
        malformed = copy.deepcopy(payload)
        del malformed["diagnostics"][0][field]
        assert not validator.is_valid(malformed), field
    payload["diagnostics"] = []
    assert not validator.is_valid(payload)


def test_mode_specific_nulls_and_expectations(validator, results) -> None:
    report = copy.deepcopy(results["clean-report"])
    report["expectation_fulfilled"] = "PASS"
    assert not validator.is_valid(report)
    report = copy.deepcopy(results["clean-report"])
    report["provenance"] = results["C-check.stdout"]["provenance"]
    assert not validator.is_valid(report)
    check = copy.deepcopy(results["C-check.stdout"])
    check["expectation_fulfilled"] = "n/a"
    assert not validator.is_valid(check)
    check["delta"] = None
    assert not validator.is_valid(check)
    validation = copy.deepcopy(results["clean-validate"])
    validation["report_filter"] = results["A-calls.stdout"]["report_filter"]
    assert not validator.is_valid(validation)


def test_measured_empty_and_unmeasured_are_distinct(validator, results) -> None:
    report = copy.deepcopy(results["clean-report"])
    assert report["filtered_violations"] is None
    report["filtered_violations"] = []
    assert not validator.is_valid(report)
    calls = copy.deepcopy(results["A-calls.stdout"])
    calls["filtered_calls"] = None
    assert not validator.is_valid(calls)


@pytest.mark.parametrize("command", ["check", "validate", "report"])
def test_unverifiable_results_cannot_claim_completed_measurements(
    validator, results, command
) -> None:
    payload = copy.deepcopy(results[f"invalid-{command}"])
    payload["measurements"] = results["clean-report"]["measurements"]
    assert not validator.is_valid(payload)


def test_filtered_violation_evidence_is_a_violation(validator, results) -> None:
    payload = copy.deepcopy(results["filtered-report"])
    payload["filtered_violations"][0]["evidence_class"] = "FACT"
    assert not validator.is_valid(payload)


def test_open_suggestions_require_contract_evidence_or_an_unavailable_reason(
    validator, results
) -> None:
    payload = copy.deepcopy(results["open-known-report"])
    payload["open_decisions"][0]["options"]["allowed_dependency"]["provenance"] = []
    assert not validator.is_valid(payload)
    payload = copy.deepcopy(results["open-unavailable-report"])
    unavailable = next(
        item for item in payload["open_decisions"] if "options_unavailable_reason" in item
    )
    del unavailable["options_unavailable_reason"]
    assert not validator.is_valid(payload)


def test_source_and_delta_evidence_cannot_be_missing_or_malformed(validator, results) -> None:
    payload = copy.deepcopy(results["C-check.stdout"])
    changes = payload["delta"]["semantic_changes"]
    projection = next(change["after"] for change in changes if change["after"] is not None)
    assert projection["evidence"]
    del projection["evidence"][0]["file"]
    assert not validator.is_valid(payload)
    payload = copy.deepcopy(results["C-check.stdout"])
    del payload["delta"]["coverage"]["status"]
    assert not validator.is_valid(payload)
    payload = copy.deepcopy(results["validation-parse-error-report"])
    failure = payload["coverage"]["failures"][0]
    del failure["evidence_class"]
    assert not validator.is_valid(payload)


@pytest.mark.parametrize("dimension", [*SUPPORTED_DIMENSIONS, None])
def test_check_requires_every_supported_dimension_assessment(validator, results, dimension) -> None:
    payload = copy.deepcopy(results["C-check.stdout"])
    if dimension is None:
        payload["delta"]["dimensions"] = {}
    else:
        del payload["delta"]["dimensions"][dimension]
    assert not validator.is_valid(payload)


def test_unknown_future_fields_are_additive(validator, results) -> None:
    payload = copy.deepcopy(results["clean-report"])
    payload["future_optional_field"] = {"detail": "ignored by an older consumer"}
    assert validator.is_valid(payload)
    check = copy.deepcopy(results["C-check.stdout"])
    check["delta"]["dimensions"]["future_dimension"] = check["delta"]["dimensions"]["violations"]
    assert validator.is_valid(check)


@pytest.mark.parametrize("field", ["diagnostics", "coverage", "delta", "provenance"])
def test_check_evidence_envelope_cannot_be_missing(validator, results, field) -> None:
    payload = copy.deepcopy(results["C-check.stdout"])
    del payload[field]
    assert not validator.is_valid(payload)


def test_small_consumer_preserves_report_fail_and_unknown(results) -> None:
    consumer = ROOT / "fixtures/consume_result.py"
    for name, expected in (
        ("C-check.stdout", "check: PASS / PASS / PASS\n"),
        ("tour-report", "report: PASS / FAIL / n/a\n"),
        ("invalid-validate", "validate: UNKNOWN / UNKNOWN / UNKNOWN\n"),
    ):
        run = subprocess.run(
            [sys.executable, str(consumer)],
            input=json.dumps(results[name]),
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, (run.stdout, run.stderr)
        assert run.stdout == expected
