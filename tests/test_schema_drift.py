# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep published schemas aligned with their executable parsers."""

import json
import tomllib
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from archkeel.cli.config import parse_config
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import (
    amendment_bytes,
    baseline_bytes,
    decode_canonical_model,
    parse_amendment,
    parse_baseline,
    parse_observation,
)
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


def test_baseline_schema_accepts_what_the_writer_writes_and_the_parser_reads() -> None:
    """AD-52: one shape for the file, checked against the executable writer and parser."""
    violations = (
        KnownViolation(ViolationFingerprint(("CONSTRUCT-NO-DYNAMIC",), ("shop.model.read",)), 2),
        KnownViolation(ViolationFingerprint(("DEP-RENDER-NO-STORE",), ("a", "b")), 1),
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
