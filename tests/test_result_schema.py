# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Published command results describe real CLI output, including failed observations."""

import json
import shlex
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_delta import _model

from archkeel.ir.codec import observation_payload
from archkeel.ir.model import (
    DiagnosticCode,
    DiagnosticKind,
    RunResult,
)
from archkeel.ir.profiles import PYTHON

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


def _validator(schema_name: str) -> Draft202012Validator:
    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = json.loads((ROOT / "schema" / schema_name).read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry)


@pytest.mark.parametrize(
    ("schema_name", "schema_version"),
    [
        ("architecture-contract-2.3.schema.json", "2.3.0"),
        ("architecture-contract.schema.json", "2.4.0"),
    ],
)
def test_command_result_open_decisions_resolve_legacy_and_current_contract_schemas(
    schema_name: str, schema_version: str
) -> None:
    provenance = ["docs/architecture/dependencies.md"]
    allowed = {
        "id": "ALLOW",
        "kind": "allowed_dependency",
        "source": "sample.source",
        "target": "sample.target",
        "rationale": "Permit the service edge.",
        "provenance": provenance,
        "decided_by": "architect",
    }
    forbidden = {
        "id": "FORBID",
        "kind": "forbidden_dependency",
        "source": "sample.source",
        "target": "sample.other",
        "include_type_checking": False,
        "rationale": "Keep the storage boundary closed.",
        "provenance": provenance,
        "decided_by": "architect",
    }
    contract = {
        "schema_version": schema_version,
        "components": [
            {
                "id": "source",
                "label": "source",
                "role": "component",
                "packages": ["sample.source"],
                "responsibilities": ["Own the source service."],
                "forbidden_responsibilities": [],
                "provenance": provenance,
            },
            {
                "id": "target",
                "label": "target",
                "role": "component",
                "packages": ["sample.target"],
                "responsibilities": ["Own the target service."],
                "forbidden_responsibilities": [],
                "provenance": provenance,
            },
        ],
        "rules": [allowed, forbidden],
    }
    contract_schema = json.loads((ROOT / "schema" / schema_name).read_bytes())
    Draft202012Validator(contract_schema).validate(contract)

    result_validator = _validator("command-result.schema.json")
    decision_validator = result_validator.evolve(
        schema=result_validator.schema["$defs"]["openDecision"]
    )
    decision = {
        "source": "sample.source",
        "target": "sample.target",
        "observed": True,
        "import_sites": 1,
        "source_package": "sample.source",
        "target_package": "sample.target",
        "options": {"allowed_dependency": allowed, "forbidden_dependency": forbidden},
    }
    assert not list(decision_validator.iter_errors(decision))


def test_historical_python_call_binding_reference_resolves_frozen_v4_schema() -> None:
    validator = _validator("architecture-ir-python-decoded-2.6.schema.json")
    call_binding = validator.evolve(
        schema={"$ref": ("https://archkeel.dev/schema/source-facts/4.0.0#/$defs/CallBinding")}
    )

    assert not call_binding.is_valid({})


# A validator is read-only, so one worker can share it across files (tests/conftest.py groups
# the tests of a module fixture on one worker).
@pytest.fixture(scope="session")
def legacy_validator() -> Draft202012Validator:
    return _validator("command-result.schema.json")


@pytest.fixture(scope="session")
def validator() -> Draft202012Validator:
    return _validator("command-result-13.0.schema.json")


@pytest.fixture(scope="session")
def current_validator() -> Draft202012Validator:
    return _validator("command-result-13.0.schema.json")


def test_command_coverage_distinguishes_unmeasured_from_mixed_call_counts(legacy_validator) -> None:
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
    neutral = legacy_validator.evolve(schema=legacy_validator.schema["properties"]["coverage"])
    assert neutral.is_valid(payload)
    payload["calls_analyzed"] = 0
    assert not neutral.is_valid(payload)
    assert not legacy_validator.evolve(schema=coverage).is_valid(payload)


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
    legacy_validator, total: object, unresolved: int | None, resolution: str, valid: bool
) -> None:
    from dataclasses import asdict

    from archkeel.ir.measurements import RatchetScalars

    payload = {
        "scalars": asdict(RatchetScalars(0, 0, 0, 0, unresolved, 0)),
        "calls_total": total,
        "resolution": resolution,
    }
    measurements = legacy_validator.evolve(schema=legacy_validator.schema["$defs"]["measurements"])
    assert measurements.is_valid(payload) is valid


@pytest.mark.parametrize("version", ["2.0.0", "2.1.0"])
def test_decoded_typescript_schema_preserves_unmeasured_call_availability(version) -> None:
    from test_nullable_profile_measurements import _profile_model

    from archkeel.ir.codec import parse_observation

    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    decoded = Draft202012Validator(
        {"$ref": f"urn:archkeel:architecture-ir:decoded:{version}"}, registry=registry
    )
    payload = observation_payload(parse_observation(_profile_model("archkeel-typescript-imports")))
    payload["schema_version"] = version
    assert not list(decoded.iter_errors(payload))
    payload["coverage"].update(
        calls_analyzed=0,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
        call_resolution_percent=0,
    )
    assert not decoded.is_valid(payload)


@pytest.mark.parametrize("version", [f"2.{minor}.0" for minor in range(1, 10)])
@pytest.mark.parametrize("branch", [1, 2])
def test_command_result_9_observation_branches_admit_supported_history(
    validator, version: str, branch: int
) -> None:
    profile = PYTHON
    observation = _model(git_head="a" * 40, schema_version=version)
    observation["analyzer"]["name"] = profile.analyzer
    observation["producer"] = dict(observation["analyzer"])
    observation["runtime"] = {"name": "python", "version": "3.11.12"}
    for section in profile.absent_sections | profile.all_optional_sections:
        observation[section] = None

    references = validator.schema["anyOf"][branch]["properties"]["observation"]
    nested = validator.evolve(schema=references)
    errors = list(nested.iter_errors(observation))
    assert not errors, (version, branch, [(list(error.path), error.message) for error in errors])


def test_result_properties_cover_the_writer(legacy_validator, current_validator) -> None:
    # Published schemas stay byte-exact; the current version's strict branch names every field.
    strict = current_validator.schema["anyOf"][2]
    assert set(strict["properties"]) == {field.name for field in fields(RunResult)}
    diagnostic = legacy_validator.schema["$defs"]["diagnostic"]["properties"]
    current = current_validator.schema["$defs"]["diagnostic"]["properties"]
    assert set(current["kind"]["enum"]) == set(DiagnosticKind)
    assert set(diagnostic["kind"]["enum"]) == set(DiagnosticKind) - {
        DiagnosticKind.UNRESOLVED_IMPORT,
        DiagnosticKind.NOT_EXAMINED,
        DiagnosticKind.INCOMPLETE_SCAN,
    }
    assert set(diagnostic["code"]["enum"]) == set(DiagnosticCode)
