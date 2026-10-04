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

from archkeel.check.delta import SUPPORTED_DIMENSIONS, build_architecture_delta
from archkeel.check.run import _incomplete
from archkeel.ir.codec import delta_payload, observation_payload, result_payload
from archkeel.ir.model import CLASSIFIED_SECTIONS, DiagnosticCode, DiagnosticKind, RunResult
from fixtures.architecture_demo import CATALOG, materialized_fixture
from tests.test_dart_profile import _observe
from tests.test_exact_module_ownership import _contract, _observe_tree

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
    coverage = json.loads((ROOT / "schema/architecture-ir-common.schema.json").read_bytes())[
        "$defs"
    ]["coverage"]
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


@pytest.mark.parametrize(
    ("language", "source", "total", "unresolved"),
    [
        ("python", "VALUE = 1\n", 0, 0),
        ("python", "def run():\n    return missing()\n", 1, 1),
        ("dart", "void main() { print('hello'); }\n", None, None),
    ],
)
def test_real_cli_call_totals_preserve_availability(
    validator,
    tmp_path: Path,
    language: str,
    source: str,
    total: int | None,
    unresolved: int | None,
) -> None:
    from archkeel.ir.codec import parse_measurements

    (tmp_path / "src").mkdir()
    if language == "python":
        (tmp_path / "src/sample").mkdir()
    source_path = "src/app.dart" if language == "dart" else "src/sample/app.py"
    (tmp_path / source_path).write_text(source)
    (tmp_path / ("pubspec.yaml" if language == "dart" else "pyproject.toml")).write_text(
        "name: sample\n" if language == "dart" else '[project]\nrequires-python=">=3.11"\n'
    )
    (tmp_path / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [], "rules": []})
    )
    (tmp_path / "archkeel.toml").write_text(
        f'[scan]\nroots=["src"]\nnamespace="sample"\ncontract="contract.json"\n'
        f'language="{language}"\n'
    )
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Call measurement fixture",
        ),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    run = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(tmp_path),
            "--output",
            str(tmp_path / "architecture.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    payload = json.loads(run.stdout)
    assert run.returncode == 0, (payload["diagnostics"], run.stderr)
    assert payload["coverage"]["calls_analyzed"] == total
    assert payload["measurements"]["calls_total"] == total
    assert payload["measurements"]["scalars"]["calls_unresolved"] == unresolved
    assert not list(validator.iter_errors(payload))
    assert parse_measurements(payload["measurements"], "report").calls_total == total


@pytest.mark.parametrize(
    ("total", "unresolved", "resolution", "valid"),
    [
        (None, None, "n/a", True),
        (0, None, "n/a", True),
        (0, 0, "n/a", True),
        (1, 1, "measured", True),
        (None, 0, "n/a", False),
        (None, None, "measured", False),
        (1, None, "measured", False),
        (0, 1, "n/a", False),
        (0, 0, "measured", False),
        (1, 0, "n/a", False),
        (True, 0, "measured", False),
        (-1, 0, "measured", False),
        ("1", 0, "measured", False),
    ],
)
def test_measurement_schema_rejects_incoherent_count_availability(
    validator, total: object, unresolved: int | None, resolution: str, valid: bool
) -> None:
    from dataclasses import asdict

    from archkeel.ir.measurements import RatchetScalars

    payload = {
        "scalars": asdict(RatchetScalars(0, 0, 0, 0, unresolved, 0)),
        "calls_total": total,
        "resolution": resolution,
    }
    measurements = validator.evolve(schema=validator.schema["$defs"]["measurements"])
    assert measurements.is_valid(payload) is valid


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


def test_real_dart_delta_matches_the_published_schema(validator, tmp_path: Path) -> None:
    result = _observe(tmp_path, {"lib/a.dart": ""})
    assert result.exit_code == 0 and result.observation is not None
    delta = delta_payload(
        build_architecture_delta(
            result.observation,
            result.observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="b" * 64,
        )
    )
    schema = validator.evolve(schema={"$ref": "urn:archkeel:command-result:3.0.0#/$defs/delta"})
    assert not list(schema.iter_errors(delta))
    delta["analyzer"]["name"] = "unknown-analyzer"
    assert not schema.is_valid(delta)


def test_delta_schema_keeps_legacy_integer_call_totals(validator, tmp_path: Path) -> None:
    result = _observe_tree(tmp_path, {"sample/a.py": ""}, _contract([]))
    assert result.observation is not None
    delta = delta_payload(
        build_architecture_delta(
            result.observation,
            result.observation,
            baseline_digest="a" * 64,
            head_digest="a" * 64,
            checker_digest="b" * 64,
        )
    )
    schema = validator.evolve(schema=validator.schema["$defs"]["delta"])
    for side in ("baseline", "head"):
        delta["ratchets"][side]["scalars"]["calls_unresolved"] = None
    for version in ("1.3.0", "1.4.0"):
        legacy = copy.deepcopy(delta)
        legacy["schema_version"] = version
        assert schema.is_valid(legacy)
        for side in ("baseline", "head"):
            legacy["ratchets"][side]["calls_total"] = None
        assert schema.is_valid(legacy) is (version == "1.4.0")


def test_incomplete_dart_check_preserves_profile_sections(validator, tmp_path: Path) -> None:
    result = _observe(tmp_path, {"lib/a.dart": "import 'x.dart'\n"})
    assert result.exit_code == 2 and result.observation is not None
    payload = result_payload(_incomplete(result))
    assert not list(validator.iter_errors(payload))
    python = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:python-decoded:1.3.0"})
    assert not python.is_valid(payload["observation"])
    for section, invalid in (
        ("symbols", []),
        ("references", []),
        ("bindings", []),
        ("imports", None),
    ):
        malformed = copy.deepcopy(payload)
        malformed["observation"][section] = invalid
        assert not validator.is_valid(malformed), section
        del malformed["observation"][section]
        assert not validator.is_valid(malformed), section
    payload["observation"]["analyzer"]["name"] = "unknown-analyzer"
    assert not validator.is_valid(payload)


def test_python_observation_sections_remain_required(validator, tmp_path: Path) -> None:
    result = _observe_tree(tmp_path, {"sample/a.py": ""}, _contract([]))
    assert result.exit_code == 0 and result.observation is not None
    observation = observation_payload(result.observation)
    schemas = (
        validator.evolve(schema=validator.schema["properties"]["observation"]),
        validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:python-decoded:1.3.0"}),
    )
    for schema in schemas:
        assert schema.is_valid(observation)
        for section in CLASSIFIED_SECTIONS:
            malformed = dict(observation)
            del malformed[section]
            assert not schema.is_valid(malformed), section
            malformed[section] = None
            assert not schema.is_valid(malformed), section


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
        ("tour-validate", "validate: PASS / FAIL / n/a\n"),
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


def test_diagnostic_validate_preserves_complete_evidence_only(validator, results) -> None:
    payload = copy.deepcopy(results["tour-validate"])
    assert payload["exit_code"] == 2
    assert [payload[key] for key in VERDICTS] == ["PASS", "FAIL", "n/a"]
    assert validator.is_valid(payload)
    for field in ("measurements", "coverage", "claims"):
        invalid = copy.deepcopy(payload)
        invalid[field] = None
        assert not validator.is_valid(invalid), field
    for command in ("check", "report"):
        invalid = copy.deepcopy(payload)
        invalid["command"] = command
        assert not validator.is_valid(invalid), command
    incomplete = copy.deepcopy(payload)
    incomplete["observation_complete"] = "UNKNOWN"
    assert not validator.is_valid(incomplete)
    legacy = copy.deepcopy(validator.schema)
    legacy["allOf"][1]["then"] = legacy["allOf"][1]["then"]["else"]
    assert not validator.evolve(schema=legacy).is_valid(payload)
    assert validator.evolve(schema=legacy).is_valid(results["invalid-validate"])
