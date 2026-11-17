# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#946: a registry or git dependency named like a crate of the workspace is a pair gap.

Consumer: `archkeel validate` with the native Rust collector. `app` names `base-crate` by a registry
version or a git URL, never by a `path`, and calls `base_crate::make()`. Cargo can still build the
crate `base` of the workspace for it: a git URL of this repository, a `[patch]` in a Cargo config
outside the repository or on the command line, or a `[patch]` in the repository. rustc is the
oracle: each plant compiles, and `make` exists only in `base`, so the edge `app -> base` is real.
The collector cannot see such a redirect, so the pair is a gap: never PASS. Without any redirect
Cargo fetches another crate, so a FAIL would be false as well: the twins stay UNKNOWN.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import APP, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

PARTS = (component("base", "base_crate"), component("app", "app"))
RULES = (
    rule("REQUIRES", "complete_requires"),
    rule(
        "NO-APP-TO-BASE",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate",
        include_type_checking=True,
    ),
)
REGISTRY_APP = APP.replace('base-crate = { path = "../base" }', 'base-crate = "0.0.0"')
WORKSPACE = '[workspace]\nmembers = ["base", "app"]\nresolver = "2"\n'


def _patch(root: Path) -> str:
    return f'[patch.crates-io]\nbase-crate = {{ path = "{root.resolve()}/crates/base" }}\n'


def _cargo(root: Path, home: Path, *extra: str) -> None:
    home.mkdir(exist_ok=True)
    env = {**os.environ, "CARGO_HOME": str(home), "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "crates/Cargo.toml"
    command = ["cargo", "check", "--quiet", "--manifest-path", str(manifest), *extra]
    done = subprocess.run(command, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr


def _verdicts(root: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    found = statuses(validate(root, capsys))
    return {name: found.get(name, "") for name in ("REQUIRES", "NO-APP-TO-BASE")}


def test_a_git_url_of_this_repository_gives_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = (tmp_path / "repo").resolve().as_uri()
    manifest = APP.replace('base-crate = { path = "../base" }', f'base-crate = {{ git = "{url}" }}')
    root = repository(
        tmp_path / "repo",
        core_binary,
        {"crates/Cargo.toml": WORKSPACE, "crates/app/Cargo.toml": manifest},
        components=PARTS,
        rules=RULES,
    )
    _cargo(root, tmp_path / "home")

    assert "PASS" not in _verdicts(root, capsys).values()


def test_a_patch_in_a_cargo_config_outside_the_repository_gives_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"crates/Cargo.toml": WORKSPACE, "crates/app/Cargo.toml": REGISTRY_APP}
    root = repository(tmp_path / "repo", core_binary, files, components=PARTS, rules=RULES)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(_patch(root))
    _cargo(root, home, "--offline")

    assert "PASS" not in _verdicts(root, capsys).values()


def test_a_patch_on_the_command_line_gives_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"crates/Cargo.toml": WORKSPACE, "crates/app/Cargo.toml": REGISTRY_APP}
    root = repository(tmp_path / "repo", core_binary, files, components=PARTS, rules=RULES)
    path = f"{root.resolve()}/crates/base"
    _cargo(
        root,
        tmp_path / "home",
        "--offline",
        "--config",
        f'patch.crates-io.base-crate.path="{path}"',
    )

    assert "PASS" not in _verdicts(root, capsys).values()


def test_a_patch_in_the_repository_gives_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    files = {
        "crates/Cargo.toml": WORKSPACE + _patch(root),
        "crates/app/Cargo.toml": REGISTRY_APP,
    }
    root = repository(root, core_binary, files, components=PARTS, rules=RULES)
    _cargo(root, tmp_path / "home", "--offline")

    assert "PASS" not in _verdicts(root, capsys).values()


# Cargo fetches `base-crate` from the registry unless a redirect exists, maybe outside the
# repository: the edge `app -> base` may or may not exist, and the scan cannot tell. Main gave PASS
# for the plain form, and a false FAIL when any file of the repository could redirect another name
# (AD-502 point 5). No registry is at hand offline, so rustc is not the oracle here.
UNSEEN = {
    "no redirect in the repository": {},
    "a patch of another name in the repository": {
        "crates/Cargo.toml": WORKSPACE + '[patch.crates-io]\nother = { path = "other" }\n',
    },
}


@pytest.mark.parametrize("extra", UNSEEN.values(), ids=UNSEEN.keys())
def test_a_registry_name_that_the_scan_cannot_follow_is_unknown(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], extra: dict[str, str]
) -> None:
    files = {"crates/app/Cargo.toml": REGISTRY_APP, **extra}
    root = repository(tmp_path / "repo", core_binary, files, components=PARTS, rules=RULES)

    assert _verdicts(root, capsys) == {"REQUIRES": "UNKNOWN", "NO-APP-TO-BASE": "UNKNOWN"}
