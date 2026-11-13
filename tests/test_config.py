# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest
from test_snapshot import _committed_repository, _git

from archkeel.check.git import GitError
from archkeel.cli.config import ConfigError, load_check_config, load_config, parse_config


@pytest.mark.parametrize(
    "payload",
    [
        b'[scan]\nroots = ["backend"]\nnamespace = "backend"\ncontract = "x.json"\nextra = true\n',
        b'[other]\nroots = ["backend"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = []\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["../backend"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["back*"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["backend", "backend"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["backend", "backend/api"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["backend/api", "backend"]\nnamespace = "backend"\ncontract = "x.json"\n',
        b'[scan]\nroots = ["backend"]\nnamespace = "backend-name"\ncontract = "x.json"\n',
    ],
)
def test_parse_rejects_invalid_shape_or_paths(payload: bytes) -> None:
    payload = payload.replace(b"[scan]\n", b'[scan]\nlanguage = "typescript"\n')
    with pytest.raises(ConfigError):
        parse_config(payload)


def test_load_rejects_config_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-config-outside"
    outside.mkdir()
    (outside / "archkeel.toml").write_bytes(
        b'[scan]\nroots = ["."]\nnamespace = "backend"\ncontract = "contract.json"\n'
    )
    (tmp_path / "archkeel.toml").symlink_to(outside / "archkeel.toml")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("../archkeel.toml", "--config must be a safe POSIX relative path"),
        ("/etc/archkeel.toml", "--config must be a safe POSIX relative path"),
        (".", "--config must be a safe POSIX relative path"),
        ("missing.toml", "cannot read missing.toml"),
    ],
)
def test_load_rejects_an_unsafe_or_missing_configuration_path(
    tmp_path: Path, path: str, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(tmp_path, path)


def test_an_invalid_second_configuration_is_named_by_its_own_file(tmp_path: Path) -> None:
    (tmp_path / "archkeel-tests.toml").write_text("[scan\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="^invalid archkeel-tests.toml: "):
        load_config(tmp_path, "archkeel-tests.toml")


def _config_commits(tmp_path: Path) -> tuple[Path, str, str, bytes]:
    root, _ = _committed_repository(tmp_path)
    payload = b'[scan]\nroots = ["example"]\nnamespace = "example"\ncontract = "contract.json"\n'
    (root / "archkeel.toml").write_bytes(payload)
    _git(root, "add", "archkeel.toml")
    _git(root, "commit", "-q", "-m", "accepted config")
    baseline = _git(root, "rev-parse", "HEAD")
    (root / "example/tasks/sample.py").write_text("value = 2\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "candidate")
    return root, baseline, _git(root, "rev-parse", "HEAD"), payload


@pytest.mark.parametrize("symlink", [False, True])
def test_check_config_rejects_changed_or_symlink_candidate(tmp_path: Path, symlink: bool) -> None:
    root, baseline, _, payload = _config_commits(tmp_path)
    path = root / "archkeel.toml"
    if symlink:
        path.unlink()
        (root / "alternate.toml").write_bytes(payload)
        path.symlink_to("alternate.toml")
    else:
        path.write_bytes(payload.replace(b'namespace = "example"', b'namespace = "changed"'))
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "changed policy")
    head = _git(root, "rev-parse", "HEAD")
    with pytest.raises(GitError if symlink else ConfigError):
        load_check_config(root, baseline, head)


def test_typescript_config_defaults_to_tsconfig_and_keeps_argv_optional() -> None:
    payload = (
        b'[scan]\nroots = ["src"]\nnamespace = "sample"\n'
        b'contract = "architecture-contract.json"\nlanguage = "typescript"\n'
    )

    config = parse_config(payload)

    assert config.language == "typescript"
    assert config.tsconfig == "tsconfig.json"
    assert config.collector_argv is None


@pytest.mark.parametrize(
    "extra",
    [
        b'tsconfig = "../tsconfig.json"\n',
        b'tsconfig = "/repo/tsconfig.json"\n',
        b'tsconfig = ""\n',
        b'collector_argv = "node adapter.js"\n',
        b"collector_argv = []\n",
        b'collector_argv = ["node", ""]\n',
        b'collector_argv = ["node\\u0000"]\n',
    ],
)
def test_typescript_config_rejects_unsafe_paths_and_invalid_argv(extra: bytes) -> None:
    payload = (
        b'[scan]\nroots = ["src"]\nnamespace = "sample"\n'
        b'contract = "architecture-contract.json"\nlanguage = "typescript"\n' + extra
    )

    with pytest.raises(ConfigError):
        parse_config(payload)


def test_load_typescript_config_requires_contained_tsconfig(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "architecture-contract.json").write_text("{}", encoding="utf-8")
    (tmp_path / "archkeel.toml").write_bytes(
        b'[scan]\nroots = ["src"]\nnamespace = "sample"\n'
        b'contract = "architecture-contract.json"\nlanguage = "typescript"\n'
        b'tsconfig = "config/tsconfig.json"\n'
    )

    with pytest.raises(ConfigError, match="tsconfig"):
        load_config(tmp_path)


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_scan_language_is_narrowed_to_a_supported_profile(language: str) -> None:
    payload = (
        f'[scan]\nroots = ["src"]\nnamespace = "sample"\n'
        f'contract = "architecture-contract.json"\nlanguage = "{language}"\n'
    ).encode()

    assert parse_config(payload).language == language


@pytest.mark.parametrize("language", ['"go"', "1", "true", '["python"]'])
def test_scan_rejects_a_language_outside_its_profile_alias(language: str) -> None:
    payload = (
        '[scan]\nroots = ["src"]\nnamespace = "sample"\n'
        f'contract = "architecture-contract.json"\nlanguage = {language}\n'
    ).encode()

    with pytest.raises(ConfigError, match="scan.language"):
        parse_config(payload)


_BUNDLER_BASE = (
    b'[scan]\nroots = ["src"]\nnamespace = "web"\ncontract = "architecture-contract.json"\n'
)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [(b"", False), (b"bundler = true\n", True), (b"bundler = false\n", False)],
)
def test_typescript_bundler_key_is_an_optional_boolean(extra: bytes, expected: bool) -> None:
    config = parse_config(_BUNDLER_BASE + b'language = "typescript"\n' + extra)
    assert config.bundler is expected


@pytest.mark.parametrize("value", [b'"yes"', b"1", b"[]"])
def test_typescript_bundler_key_rejects_non_booleans(value: bytes) -> None:
    payload = _BUNDLER_BASE + b'language = "typescript"\nbundler = ' + value + b"\n"
    with pytest.raises(ConfigError, match="scan.bundler must be a boolean"):
        parse_config(payload)


def test_bundler_key_is_in_the_published_schema() -> None:
    import json
    import tomllib

    from jsonschema import Draft202012Validator

    schema = json.loads((Path(__file__).parents[1] / "schema/archkeel.schema.json").read_bytes())
    validator = Draft202012Validator(schema)
    base = _BUNDLER_BASE.decode() + 'language = "typescript"\n'
    assert validator.is_valid(tomllib.loads(base + "bundler = true\n"))
    assert not validator.is_valid(tomllib.loads(base + 'bundler = "yes"\n'))
    python = _BUNDLER_BASE.decode() + "bundler = true\n"
    assert not validator.is_valid(tomllib.loads(python))
