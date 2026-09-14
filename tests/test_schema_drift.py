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
from archkeel.ir.codec import decode_canonical_model, parse_observation

ROOT = Path(__file__).parents[1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schema" / name).read_bytes())


def test_config_schema_accepts_the_parsed_repository_config() -> None:
    payload = (ROOT / "archkeel.toml").read_bytes()
    schema = _schema("archkeel.schema.json")
    Draft202012Validator.check_schema(schema)
    parse_config(payload)
    assert not list(Draft202012Validator(schema).iter_errors(tomllib.loads(payload.decode())))


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
