# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Configured finite process limits preserve the complete selected source scope."""

import json
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_onboarding import _repository

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.cli import main
from archkeel.cli.config import ConfigError, parse_config
from archkeel.cli.observe import observer_for
from archkeel.ir.facts import Language

ROOT = Path(__file__).parents[1]
CONFIG = '[scan]\nroots = ["src/sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("limit", [None, 1, 256 * 1024 * 1024])
def test_configured_output_limit_keeps_a_finite_default(language: str, limit: int | None) -> None:
    payload = CONFIG + f'language = "{language}"\n'
    if limit is not None:
        payload += f"collector_output_limit_bytes = {limit}\n"
    config = parse_config(payload.encode())
    selected = observer_for(
        config.language, output_limit_bytes=config.collector_output_limit_bytes
    ).collector
    assert isinstance(selected, PythonProviderCollector) is (language == "python")
    collector = selected.collector if isinstance(selected, PythonProviderCollector) else selected

    assert isinstance(collector, ProcessCollector)
    assert collector.output_limit_bytes == (64 * 1024 * 1024 if limit is None else limit)
    schema = json.loads((ROOT / "schema/archkeel.schema.json").read_bytes())
    Draft202012Validator(schema).validate(tomllib.loads(payload))


@pytest.mark.parametrize("value", ["0", "-1", "true", "false", "1.5", '"1000"', "[]"])
def test_output_limit_rejects_nonpositive_or_noninteger_configuration(value: str) -> None:
    payload = CONFIG + f"collector_output_limit_bytes = {value}\n"
    with pytest.raises(ConfigError, match="collector_output_limit_bytes.*positive integer"):
        parse_config(payload.encode())
    schema = json.loads((ROOT / "schema/archkeel.schema.json").read_bytes())
    assert not Draft202012Validator(schema).is_valid(tomllib.loads(payload))


def test_init_persists_the_limit_that_made_its_scope_observable(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path, packages=("sample",))
    args = ["init", "--root", str(root), "--json", "--collector-output-limit-bytes"]

    assert main([*args, "1000"]) == 2
    failed = json.loads(capsys.readouterr().out)
    assert "1000 byte limit" in failed["diagnostics"][0]["unknown_claim"]
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()

    assert main([*args, "10485760"]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["observation_complete"] == "PASS"
    config = parse_config((root / "archkeel.toml").read_bytes())
    assert config.collector_output_limit_bytes == 10485760


@pytest.mark.parametrize("command", ["report", "validate"])
def test_configured_limit_bounds_the_same_complete_cli_scope(
    tmp_path: Path, capsys, command: str
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    capsys.readouterr()
    config_path = root / "archkeel.toml"
    config = config_path.read_text()
    args = [command, "--root", str(root), "--json"]

    config_path.write_text(config + "collector_output_limit_bytes = 1000\n")
    assert main(args) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["observation_complete"] == "UNKNOWN"
    assert "1000 byte limit" in failed["diagnostics"][0]["unknown_claim"]

    config_path.write_text(config + "collector_output_limit_bytes = 10485760\n")
    assert main(args) == (0 if command == "report" else 2)
    observed = json.loads(capsys.readouterr().out)
    assert observed["observation_complete"] == "PASS"
    assert observed["coverage"]["files_read"] == len(list((root / "src").rglob("*.py")))
    assert not any("byte limit" in item["unknown_claim"] for item in observed["diagnostics"])


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "unlimited"])
def test_init_rejects_invalid_output_limits_without_writing_files(
    tmp_path: Path, capsys, value: str
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert (
        main(["init", "--root", str(root), "--json", "--collector-output-limit-bytes", value]) == 2
    )
    assert json.loads(capsys.readouterr().out)["diagnostics"]
    assert not (root / "archkeel.toml").exists()


def test_observer_carries_the_bundler_flag() -> None:
    assert observer_for(Language.TYPESCRIPT).bundler is False
    assert observer_for(Language.TYPESCRIPT, bundler=True).bundler is True
