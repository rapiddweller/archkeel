# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-313: `[scan] exclude_test_sources` gives report and validate one test-free scope."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.cli import main
from archkeel.cli.config import ConfigError, parse_config
from fixtures.demo_catalog_support import FIXTURE_DIR

_TYPESCRIPT = Path(__file__).parents[1] / "fixtures" / "H-typescript"
_KEY = "exclude_test_sources = true\n"
# language: fixture, a test file inside the scan root, its text
_CASES = {
    "python": (
        FIXTURE_DIR,
        "shop/model/test_scope_probe.py",
        "import shop.model\n",
    ),
    "typescript": (
        _TYPESCRIPT,
        "src/domain/scope-probe.spec.ts",
        'import { Order } from "./order";\nexport const probe = Order;\n',
    ),
}


def _scan_lines(fixture: Path) -> str:
    return (fixture / "archkeel.toml").read_text()


def _run(
    command: str,
    root: Path,
    config: str,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
) -> tuple[int, dict[str, object]]:
    capsys.readouterr()
    code = main([command, "--root", str(root), "--config", config, *extra, "--json"])
    return code, json.loads(capsys.readouterr().out)


def _repo(tmp_path: Path, name: str, language: str, *, probe: bool) -> Path:
    fixture, path, text = _CASES[language]
    scan = _scan_lines(fixture)
    files: dict[str, str | None] = {
        "archkeel-off.toml": scan,
        "archkeel-on.toml": scan + _KEY,
    }
    if probe:
        files[path] = text
    return _prepare_repo(tmp_path / name, files, fixture)


@pytest.mark.parametrize("language", sorted(_CASES))
@pytest.mark.parametrize("command", ["validate", "report"])
def test_the_key_removes_test_files_and_keeps_production_verdicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str, command: str
) -> None:
    clean = _repo(tmp_path, "clean", language, probe=False)
    probed = _repo(tmp_path, "probed", language, probe=True)
    _, base = _run(command, clean, "archkeel-off.toml", capsys)
    _, off = _run(command, probed, "archkeel-off.toml", capsys)
    _, on = _run(command, probed, "archkeel-on.toml", capsys)

    discovered = base["coverage"]["files_discovered"]  # type: ignore[index]
    assert off["coverage"]["files_discovered"] == discovered + 1  # type: ignore[index]
    assert on["coverage"] == base["coverage"]
    assert on["rule_assessments"] == base["rule_assessments"]
    assert off.get("notes") is None
    assert [note["subject"] for note in on["notes"]] == ["scan.exclude_test_sources"]  # type: ignore[attr-defined,union-attr]
    assert base.get("notes") is None


@pytest.mark.parametrize("language", sorted(_CASES))
def test_the_report_artifact_has_no_test_module_when_the_key_is_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str
) -> None:
    probed = _repo(tmp_path, "probed", language, probe=True)
    stem = Path(_CASES[language][1]).name.split(".")[0]
    for config, present in (("archkeel-off.toml", True), ("archkeel-on.toml", False)):
        artifact = tmp_path / f"{config}.json"
        assert _run("report", probed, config, capsys, "--output", str(artifact))[0] == 0
        assert (stem in artifact.read_text()) is present


@pytest.mark.parametrize("language", sorted(_CASES))
def test_an_absent_key_is_the_same_as_false(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str
) -> None:
    probed = _repo(tmp_path, "probed", language, probe=True)
    (probed / "archkeel-false.toml").write_text(
        _scan_lines(_CASES[language][0]) + "exclude_test_sources = false\n"
    )
    _, absent = _run("validate", probed, "archkeel-off.toml", capsys)
    _, false = _run("validate", probed, "archkeel-false.toml", capsys)
    assert absent == false


_HEAD = b'[scan]\nroots = ["src"]\nnamespace = "app"\ncontract = "c.json"\n'


def test_the_key_defaults_to_false_and_reads_true() -> None:
    assert parse_config(_HEAD).exclude_test_sources is False
    assert parse_config(_HEAD + b"exclude_test_sources = true\n").exclude_test_sources is True
    ts = b'language = "typescript"\n' + _HEAD.removeprefix(b"[scan]\n")
    assert parse_config(b"[scan]\n" + ts + b"exclude_test_sources = true\n").exclude_test_sources


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (b'exclude_test_sources = "yes"\n', "must be a boolean"),
        (b'language = "dart"\nexclude_test_sources = true\n', "not supported for dart"),
    ],
)
def test_the_key_rejects_a_bad_value_or_a_language_without_a_test_rule(
    extra: bytes, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(_HEAD + extra)


def test_dart_may_name_the_key_as_false() -> None:
    config = parse_config(_HEAD + b'language = "dart"\nexclude_test_sources = false\n')
    assert config.exclude_test_sources is False
