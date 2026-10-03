# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep published schemas aligned with their executable parsers."""

import json
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_delta import _model

from archkeel.cli.config import parse_config
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import (
    amendment_bytes,
    baseline_bytes,
    decode_canonical_model,
    parse_amendment,
    parse_baseline,
    parse_contract,
    parse_observation,
)
from archkeel.ir.profiles import PROFILES
from archkeel.ir.widening import Amendment

ROOT = Path(__file__).parents[1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schema" / name).read_bytes())


def test_config_schema_accepts_the_parsed_repository_config() -> None:
    payload = (ROOT / "archkeel.toml").read_bytes()
    schema = _schema("archkeel.schema.json")
    Draft202012Validator.check_schema(schema)
    parse_config(payload)
    assert not list(Draft202012Validator(schema).iter_errors(tomllib.loads(payload.decode())))


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
def test_config_schema_accepts_supported_language_options(language: str) -> None:
    payload = (
        f'[scan]\nlanguage="{language}"\nroots=["src"]\nnamespace="sample"\n'
        'contract="contract.json"\ncollector_argv=["node", "collector.js"]\n'
        + ('tsconfig="config/custom.json"\n' if language == "typescript" else "")
    ).encode()
    parse_config(payload)
    assert Draft202012Validator(_schema("archkeel.schema.json")).is_valid(
        tomllib.loads(payload.decode())
    )


@pytest.mark.parametrize(
    "setting",
    [
        'language="rust"',
        'language="dart"\ntsconfig="tsconfig.json"',
        'tsconfig="tsconfig.json"',
        'language="typescript"\ntsconfig="../outside.json"',
        'language="typescript"\ntsconfig="config:unsafe.json"',
        "collector_argv=[]",
        'collector_argv=[""]',
        'collector_argv=["\\u0000"]',
        'roots=["src/*"]',
        "unknown=true",
    ],
)
def test_config_schema_rejects_unsupported_language_options(setting: str) -> None:
    roots = "" if setting.startswith("roots=") else 'roots=["src"]\n'
    payload = (
        "[scan]\n" + roots + 'namespace="sample"\ncontract="contract.json"\n' + setting
    ).encode()
    with pytest.raises(ValueError):
        parse_config(payload)
    assert not Draft202012Validator(_schema("archkeel.schema.json")).is_valid(
        tomllib.loads(payload.decode())
    )


@pytest.mark.parametrize(
    "suffix", [".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
)
def test_contract_schema_accepts_supported_module_targets(suffix: str) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": {
            "modules": [{"path": f"src/planned{suffix}", "responsibility": "Own planned work."}]
        },
    }
    parse_contract(contract)
    assert Draft202012Validator(_schema("architecture-contract.schema.json")).is_valid(contract)


@pytest.mark.parametrize(
    "path",
    [
        "../planned.dart",
        "/planned.ts",
        "src//planned.dart",
        "src/./planned.ts",
        "src/planned.json",
        "C:planned.dart",
        "src/planned.dart\n",
        "src/planned\u0000.dart",
    ],
)
def test_contract_schema_rejects_unsupported_module_target_paths(path: str) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": {"modules": [{"path": path, "responsibility": "Own planned work."}]},
    }
    with pytest.raises(ValueError):
        parse_contract(contract)
    assert not Draft202012Validator(_schema("architecture-contract.schema.json")).is_valid(contract)


def test_baseline_schema_accepts_what_the_writer_writes_and_the_parser_reads() -> None:
    """AD-52: one shape for the file, checked against the executable writer and parser."""
    violations = (
        KnownViolation(
            ViolationFingerprint(("CONSTRUCT-NO-DYNAMIC",), ("shop.model.read",)),
            2,
        ),
        KnownViolation(
            ViolationFingerprint(("DEP-RENDER-NO-STORE",), ("a", "b")),
            1,
            (("shop.render", "shop.store"),),
        ),
    )
    schema = _schema("violation-baseline.schema.json")
    Draft202012Validator.check_schema(schema)
    written = json.loads(baseline_bytes(violations))

    assert parse_baseline(written) == violations
    assert not list(Draft202012Validator(schema).iter_errors(written))


def test_amendment_schema_accepts_what_the_writer_writes_and_the_parser_reads() -> None:
    """AD-61: one shape for the file, checked against the executable writer and parser."""
    amendment = Amendment("0" * 64, "1" * 64, "architect: Jordan", "Planned migration, phase 2.")
    schema = _schema("contract-amendment.schema.json")
    Draft202012Validator.check_schema(schema)
    written = json.loads(amendment_bytes(amendment))

    assert parse_amendment(written) == amendment
    assert not list(Draft202012Validator(schema).iter_errors(written))


def test_ir_schemas_accept_the_parsed_self_observation() -> None:
    common = _schema("architecture-ir-common.schema.json")
    profile = _schema("architecture-ir-python-decoded.schema.json")
    Draft202012Validator.check_schema(common)
    Draft202012Validator.check_schema(profile)
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    observation = decode_canonical_model(
        json.loads((ROOT / "fixtures/D-self/architecture.json").read_bytes())
    )
    parse_observation(observation)
    assert not list(Draft202012Validator(profile, registry=registry).iter_errors(observation))
    for imported in observation["imports"]:
        imported["data"].pop("source_member_binding_static", None)
        imported["data"].pop("reexport_candidates", None)
    assert not list(Draft202012Validator(profile, registry=registry).iter_errors(observation))


@pytest.mark.parametrize("profile", PROFILES.values(), ids=lambda profile: profile.analyzer)
def test_shared_observation_schema_preserves_each_profile_and_provenance(profile) -> None:
    common = _schema("architecture-ir-common.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    validator = Draft202012Validator(
        {"$ref": common["$id"] + "#/$defs/observation"}, registry=registry
    )
    observation = _model(git_head="a" * 40)
    observation["analyzer"]["name"] = profile.analyzer
    observation["producer"] = dict(observation["analyzer"])
    observation["runtime"] = {"name": "python", "version": "3.11.12"}
    for section in profile.absent_sections:
        observation[section] = None
    parse_observation(observation)
    assert not list(validator.iter_errors(observation))
    for section in profile.absent_sections:
        observation[section] = []
        assert not validator.is_valid(observation), section
        observation[section] = None
    for section in {
        "symbols",
        "references",
        "bindings",
        "calls",
        "typing_signals",
        "constructs",
    } - profile.absent_sections:
        observation[section] = None
        assert not validator.is_valid(observation), section
        observation[section] = []
    observation["analyzer"]["name"] = "unknown-analyzer"
    assert not validator.is_valid(observation)


@pytest.mark.parametrize("field", ["runtime", "producer"])
@pytest.mark.parametrize("value", ["", " ", "unknown", "UNKNOWN", None, False])
def test_shared_observation_schema_rejects_unknown_provenance(field, value) -> None:
    common = _schema("architecture-ir-common.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    validator = Draft202012Validator(
        {"$ref": common["$id"] + "#/$defs/observation"}, registry=registry
    )
    observation = _model(git_head="a" * 40)
    observation[field] = {"name": "python", "version": "3.11.12"}
    if field == "producer":
        observation[field]["code_digest"] = "b" * 64
    assert validator.is_valid(observation)
    for key in observation[field]:
        original = observation[field][key]
        observation[field][key] = value
        with pytest.raises(ValueError):
            parse_observation(observation)
        assert not validator.is_valid(observation), key
        observation[field][key] = original


@pytest.mark.parametrize(
    ("field", "value", "accepted"),
    [
        ("source_member_binding_static", True, True),
        ("source_member_binding_static", False, True),
        ("source_member_binding_static", None, False),
        ("source_member_binding_static", 0, False),
        ("source_member_binding_static", 1, False),
        ("source_member_binding_static", "false", False),
        ("reexport_candidates", [], True),
        ("reexport_candidates", ["archkeel.ir.model.Record"], True),
        ("reexport_candidates", None, False),
        ("reexport_candidates", [None], False),
        ("reexport_candidates", [0], False),
        ("reexport_candidates", [True], False),
        ("reexport_candidates", [""], False),
        ("reexport_candidates", "archkeel.ir.model.Record", False),
    ],
)
def test_import_proof_metadata_schema(field: str, value: object, accepted: bool) -> None:
    common = _schema("architecture-ir-common.schema.json")
    profile = _schema("architecture-ir-python-decoded.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    observation = decode_canonical_model(
        json.loads((ROOT / "fixtures/D-self/architecture.json").read_bytes())
    )
    imported = next(
        item for item in observation["imports"] if "source_member_binding_static" in item["data"]
    )
    imported["data"][field] = value
    errors = list(Draft202012Validator(profile, registry=registry).iter_errors(observation))
    assert (not errors) == accepted
    if not accepted:
        assert len(errors) == 1
        assert field in errors[0].absolute_path
