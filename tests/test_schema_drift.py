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

from archkeel.cli.config import ConfigError, load_config, parse_config
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


def test_config_schema_accepts_typescript_file_roots_tsconfig_and_argv(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.ts").write_text("export {}\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config/tsconfig.json").write_text("{}\n")
    (tmp_path / "architecture-contract.json").write_text("{}\n")
    payload = (
        b'[scan]\nroots = ["src/app.ts"]\nnamespace = "app"\n'
        b'contract = "architecture-contract.json"\nlanguage = "typescript"\n'
        b'tsconfig = "config/tsconfig.json"\n'
        b'collector_argv = ["node", "packages/adapter/bin/cli.js", "--format=json"]\n'
    )
    (tmp_path / "archkeel.toml").write_bytes(payload)
    schema = _schema("archkeel.schema.json")
    Draft202012Validator.check_schema(schema)

    config = load_config(tmp_path)
    assert config.roots == ("src/app.ts",)
    assert config.tsconfig == "config/tsconfig.json"
    assert config.collector_argv == ("node", "packages/adapter/bin/cli.js", "--format=json")
    assert not list(Draft202012Validator(schema).iter_errors(tomllib.loads(payload.decode())))


def test_typescript_config_defaults_its_tsconfig_in_parser_and_schema() -> None:
    payload = (
        b'[scan]\nroots = ["src"]\nnamespace = "app"\n'
        b'contract = "architecture-contract.json"\nlanguage = "typescript"\n'
    )
    parsed = tomllib.loads(payload.decode())
    schema = _schema("archkeel.schema.json")

    assert parse_config(payload).tsconfig == "tsconfig.json"
    assert not list(Draft202012Validator(schema).iter_errors(parsed))


@pytest.mark.parametrize(
    "options",
    [
        "collector_argv = []\n",
        'collector_argv = ["node", ""]\n',
        'collector_argv = ["node", "\\u0000"]\n',
        'language = "dart"\ntsconfig = "tsconfig.json"\n',
        'language = "typescript"\ntsconfig = "."\n',
    ],
)
def test_config_schema_and_parser_reject_invalid_typescript_options(options: str) -> None:
    payload = (
        '[scan]\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\n' + options
    ).encode()
    schema = _schema("archkeel.schema.json")

    with pytest.raises(ConfigError):
        parse_config(payload)
    assert list(Draft202012Validator(schema).iter_errors(tomllib.loads(payload.decode())))


@pytest.mark.parametrize("root", ["src/*.ts", r"src\app.ts", "src/app:ts"])
def test_config_schema_matches_parser_unsafe_path_rejection(root: str) -> None:
    payload = (
        f'[scan]\nroots = [{json.dumps(root)}]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\nlanguage = "typescript"\n'
    ).encode("ascii")
    schema = _schema("archkeel.schema.json")

    with pytest.raises(ConfigError):
        parse_config(payload)
    assert list(Draft202012Validator(schema).iter_errors(tomllib.loads(payload.decode())))


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
