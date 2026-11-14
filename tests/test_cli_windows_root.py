# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-442: a release core uses one disk root and refuses network and device roots."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from rust_repository import component, repository
from test_cli_core_only_scan import command

from archkeel.cli.core_frame import resolve_root


def test_the_release_core_proves_a_disk_pass_and_failure(
    release_core: Path, tmp_path: Path
) -> None:
    for name, components, code, status in [
        ("pass", (component("base", "base_crate"), component("app", "app", ("base",))), 0, "PASS"),
        ("fail", (component("base", "base_crate"), component("app", "app")), 1, "FAIL"),
    ]:
        root = repository(tmp_path / name, release_core, components=components)
        done = command(release_core, root, "--json")
        assert done.returncode == code, done.stdout + done.stderr
        result = json.loads(done.stdout)
        assert result["status"] == status
        assert result["frame"]["self_test"]["collect"]["request"]["snapshot"]["root"] == str(
            resolve_root(root)
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path resolution")
def test_windows_shell_resolves_disk_spellings(release_core: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "long project name", release_core).resolve()
    short = subprocess.run(
        ["cmd", "/C", f'for %I in ("{root}") do @echo %~sI'],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    spellings = [
        str(root),
        str(root).replace("\\", "/"),
        str(root) + "\\",
        str(root)[0].lower() + str(root)[1:],
        "\\\\?\\" + str(root),
        short,
    ]
    junction = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/C", "mklink", "/J", str(junction), str(root)], check=True, capture_output=True
    )
    try:
        for text in [*spellings, str(junction)]:
            assert resolve_root(Path(text)) == root, text
            done = command(release_core, Path(text), "--json")
            assert done.returncode == 0, done.stdout + done.stderr
            snapshot = json.loads(done.stdout)["frame"]["self_test"]["collect"]["request"][
                "snapshot"
            ]
            assert snapshot["root"] == str(root)
    finally:
        junction.rmdir()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path prefixes")
@pytest.mark.parametrize(
    "text", [r"\\server\share", r"\\?\UNC\server\share", "\\\\.\\" + "C:" + "\\", "\\\\?\\Volume{abc}\\"]
)
def test_windows_network_and_device_roots_refuse(release_core: Path, text: str) -> None:
    done = command(release_core, Path(text), "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    result = json.loads(done.stdout)
    assert result["status"] == "UNKNOWN"
    assert result["refusal"]["kind"] == "invalid_input"
    # Send the same root directly, so a shell refusal cannot hide a core acceptance.
    refused = subprocess.run(
        [str(release_core), "scan"],
        input=json.dumps(
            {
                "protocol": "archkeel-core-scan-1",
                "root": text,
                "config": "archkeel.toml",
                "root_only": True,
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert refused.returncode == 3, refused.stdout + refused.stderr
    frame = json.loads(refused.stdout)
    assert frame["status"] == "UNKNOWN"
    assert "root" in frame["self_test"]["collect"]["refused"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction containment")
def test_windows_an_escaping_config_junction_has_no_verdict(
    release_core: Path, tmp_path: Path
) -> None:
    root = repository(tmp_path / "project", release_core)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "archkeel.toml").write_bytes((root / "archkeel.toml").read_bytes())
    link = root / "escape"
    subprocess.run(
        ["cmd", "/C", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
    )
    try:
        done = command(release_core, root, "--config", "escape/archkeel.toml", "--json")
        assert done.returncode == 2, done.stdout + done.stderr
        result = json.loads(done.stdout)
        assert result["status"] == "UNKNOWN"
        assert "cannot read escape/archkeel.toml" in result["refusal"]["message"]
    finally:
        link.rmdir()
