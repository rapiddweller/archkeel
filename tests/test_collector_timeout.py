# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Configured collector deadlines bound the same complete scope as the output limit."""

import json
import tomllib
from pathlib import Path
from threading import TIMEOUT_MAX

import pytest
from jsonschema import Draft202012Validator
from test_onboarding import _repository

from archkeel import cli
from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.cli import main
from archkeel.cli.config import ConfigError, parse_config
from archkeel.cli.observe import observer_for

ROOT = Path(__file__).parents[1]
CONFIG = '[scan]\nroots = ["src/sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
OVER_LIMIT = str(int(TIMEOUT_MAX) + 1)


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("seconds", [None, 600])
def test_configured_timeout_keeps_a_300_second_default(language: str, seconds: int | None) -> None:
    payload = CONFIG + f'language = "{language}"\n'
    if seconds is not None:
        payload += f"collector_timeout_seconds = {seconds}\n"
    config = parse_config(payload.encode())
    selected = observer_for(config.language, timeout_seconds=config.collector_timeout_seconds)
    collector = selected.collector
    if isinstance(collector, PythonProviderCollector):
        collector = collector.collector

    assert isinstance(collector, ProcessCollector)
    assert collector.timeout_seconds == (300 if seconds is None else seconds)
    schema = json.loads((ROOT / "schema/archkeel.schema.json").read_bytes())
    Draft202012Validator(schema).validate(tomllib.loads(payload))


@pytest.mark.parametrize("value", ["0", "-1", "true", "false", "1.5", '"600"', "[]"])
def test_timeout_rejects_nonpositive_or_noninteger_configuration(value: str) -> None:
    payload = CONFIG + f"collector_timeout_seconds = {value}\n"
    with pytest.raises(ConfigError, match="collector_timeout_seconds.*positive integer"):
        parse_config(payload.encode())
    schema = json.loads((ROOT / "schema/archkeel.schema.json").read_bytes())
    assert not Draft202012Validator(schema).is_valid(tomllib.loads(payload))


def test_timeout_rejects_values_beyond_the_thread_deadline() -> None:
    payload = CONFIG + f"collector_timeout_seconds = {OVER_LIMIT}\n"
    with pytest.raises(ConfigError, match="collector_timeout_seconds.*positive integer"):
        parse_config(payload.encode())


def test_init_persists_the_configured_timeout(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path, packages=("sample",))
    args = ["init", "--root", str(root), "--json", "--collector-timeout-seconds", "600"]

    assert main(args) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["observation_complete"] == "PASS"
    config = parse_config((root / "archkeel.toml").read_bytes())
    assert config.collector_timeout_seconds == 600


@pytest.mark.parametrize("command", ["report", "validate"])
def test_configured_timeout_reaches_the_collector(
    tmp_path: Path, monkeypatch, capsys, command: str
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json", "--collector-timeout-seconds", "600"]) == 0
    capsys.readouterr()
    requested: list[object] = []
    build_observer = cli.observer_for

    def record(*args, **kwargs):
        requested.append(kwargs.get("timeout_seconds"))
        return build_observer(*args, **kwargs)

    monkeypatch.setattr(cli, "observer_for", record)
    main([command, "--root", str(root), "--json"])

    assert requested == [600]


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "unlimited", OVER_LIMIT])
def test_init_rejects_invalid_timeouts_without_writing_files(
    tmp_path: Path, capsys, value: str
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json", "--collector-timeout-seconds", value]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"]
    assert not (root / "archkeel.toml").exists()
