# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-420: release scan refusals bound parse work before any syntax tree exists."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from filelock import FileLock
from test_cli_native_core_scan import (  # noqa: F401 - shared pytest fixtures
    HONEST,
    ROOT,
    built,
    case_root,
    diagnostics,
    install,
    report,
)

from archkeel.analyzer.runtime import package_version

PEAK_BOUND = 128 * 1024 * 1024
HEAD = "0123456789abcdef0123456789abcdef01234567"


def canonical(root: Path) -> Path:
    text = str(root.resolve())
    # Rust canonicalize keeps the Windows verbatim prefix in a scan identity.
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        text = "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
    return Path(text)


@pytest.fixture(scope="module")
def release_core() -> Path:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed")
    target = ROOT / "native/target"
    target.mkdir(exist_ok=True)
    with FileLock(str(target / ".pytest-native-build.lock")):
        subprocess.run(
            ["cargo", "build", "--release", "--locked", "-p", "archkeel-core"],
            cwd=ROOT / "native",
            env={**os.environ, "ARCHKEEL_VERSION": package_version()},
            capture_output=True,
            check=True,
            timeout=600,
        )
    suffix = ".exe" if os.name == "nt" else ""
    return ROOT / "native/target/release" / f"archkeel-core{suffix}"


def project(root: Path, files: int, depth: int) -> dict[str, object]:
    shutil.copytree(ROOT / "fixtures/H-typescript", root)
    (root / ".git").mkdir()
    (root / ".git/HEAD").write_text(HEAD + "\n")
    text = "(" * depth + "0" + ")" * depth + ";\n"
    for number in range(files):
        (root / f"src/deep{number}.ts").write_text(text)
    return {
        "protocol": "archkeel-core-scan-1",
        "root": str(canonical(root)),
        "config": "archkeel.toml",
        "git_head": HEAD,
        "dirty": False,
    }


@pytest.mark.parametrize(("files", "depth"), [(6, 1_992_294), (1, 1_500_000)])
def test_deep_release_scans_refuse_without_a_frame_under_128_mib(
    release_core: Path, tmp_path: Path, files: int, depth: int
) -> None:
    request = project(tmp_path / "project", files, depth)
    command = [str(release_core), "scan"]
    if sys.platform == "darwin":
        command = ["/usr/bin/time", "-l", *command]
    elif sys.platform.startswith("linux"):
        command = ["/usr/bin/time", "-f", "peak_kib=%M", *command]
    done = subprocess.run(
        command, input=json.dumps(request).encode(), capture_output=True, timeout=60, check=False
    )
    assert done.returncode == 2, done.stderr.decode()
    assert done.stdout == b""
    assert b"parse_work_limit" in done.stderr
    if sys.platform == "darwin":
        found = re.search(rb"(\d+)\s+maximum resident set size", done.stderr)
        assert found is not None, done.stderr
        peak = int(found[1])
    elif sys.platform.startswith("linux"):
        found = re.search(rb"peak_kib=(\d+)", done.stderr)
        assert found is not None, done.stderr
        peak = int(found[1]) * 1024
    else:
        return  # The work bound and typed refusal above also run on Windows.
    print(f"{files} files, depth {depth}: peak {peak} bytes; bound {PEAK_BOUND} bytes")
    assert peak < PEAK_BOUND


@pytest.mark.usefixtures("install")
def test_a_real_scan_work_refusal_leaves_no_shell_artifact() -> None:
    with case_root(HONEST) as root:
        root = canonical(root)
        (root / "src/deep.ts").write_text("(" * 50_000 + "0" + ")" * 50_000 + ";\n")
        python_code, _ = report(root)
        assert python_code == 0
        code, result = report(root, "--native-core")
        assert code == 2
        assert "parse_work_limit" in diagnostics(result)
        assert not (root.parent / "out/architecture.json").exists()
