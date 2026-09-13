# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from test_snapshot import _committed_repository, _git

from pledge.check.git import GitError
from pledge.check.ports import ScanConfig
from pledge.cli.config import ConfigError, load_check_config, load_config, parse_config


def test_parse_config_returns_frozen_scan_config() -> None:
    payload = (
        b'[scan]\nroots = ["backend", "shared"]\nnamespace = "backend"\n'
        b'contract = "docs/architecture/contract.json"\n'
    )
    config = parse_config(payload)
    assert config == ScanConfig(
        ("backend", "shared"),
        "backend",
        "docs/architecture/contract.json",
        hashlib.sha256(payload).hexdigest(),
    )
    with pytest.raises(FrozenInstanceError):
        config.namespace = "changed"


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
    with pytest.raises(ConfigError):
        parse_config(payload)


def test_load_rejects_missing_contract_and_symlink_escape(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    (outside / "contract.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pledge.toml").write_bytes(
        b'[scan]\nroots = ["escape"]\nnamespace = "backend"\ncontract = "escape/contract.json"\n'
    )
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_rejects_config_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-config-outside"
    outside.mkdir()
    (outside / "pledge.toml").write_bytes(
        b'[scan]\nroots = ["."]\nnamespace = "backend"\ncontract = "contract.json"\n'
    )
    (tmp_path / "pledge.toml").symlink_to(outside / "pledge.toml")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_accepts_existing_contained_paths(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    contract = tmp_path / "docs" / "architecture" / "contract.json"
    contract.write_text("{}", encoding="utf-8")
    (tmp_path / "pledge.toml").write_bytes(
        b'[scan]\nroots = ["backend"]\nnamespace = "backend"\n'
        b'contract = "docs/architecture/contract.json"\n'
    )
    assert load_config(tmp_path).namespace == "backend"


def _config_commits(tmp_path: Path) -> tuple[Path, str, str, bytes]:
    root, _ = _committed_repository(tmp_path)
    payload = b'[scan]\nroots = ["example"]\nnamespace = "example"\ncontract = "contract.json"\n'
    (root / "pledge.toml").write_bytes(payload)
    _git(root, "add", "pledge.toml")
    _git(root, "commit", "-q", "-m", "accepted config")
    baseline = _git(root, "rev-parse", "HEAD")
    (root / "example/tasks/sample.py").write_text("value = 2\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "candidate")
    return root, baseline, _git(root, "rev-parse", "HEAD"), payload


def test_check_config_uses_git_blobs_despite_modified_worktree(tmp_path: Path) -> None:
    root, baseline, head, payload = _config_commits(tmp_path)
    (root / "pledge.toml").write_text("invalid local config")
    assert load_check_config(root, baseline, head) == parse_config(payload)


@pytest.mark.parametrize("symlink", [False, True])
def test_check_config_rejects_changed_or_symlink_candidate(tmp_path: Path, symlink: bool) -> None:
    root, baseline, _, payload = _config_commits(tmp_path)
    path = root / "pledge.toml"
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
