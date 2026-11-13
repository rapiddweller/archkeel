# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-418: the core decides each rule of the self-contract of native/ (#880, goal M2).

The test collects `native/` from this tree with the Rust collector of this build and sends the
reply to the core of the same build. Stage 1 sends no request while the Python run is not
complete, so the test calls the core of the shell directly with the collected reply. Each rule
has a decision: the status of the Python engine, or PASS beyond it over a Python UNKNOWN that
the frame names (AD-384). No rule names a part of the scope proof.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
from collections import Counter
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock

from archkeel.analyzer.runtime import package_version
from archkeel.cli import main, native_core, observe

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
SUFFIX = ".exe" if os.name == "nt" else ""
BINARIES = ("archkeel-core", "archkeel-rust-collector")


@pytest.fixture(scope="module")
def built() -> Path:
    """The core and the Rust collector, built with the version of this install (AD-319)."""
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native core tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    target = NATIVE / "target" / "shell"
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [cargo, "build", "--locked", "-q", "-p", BINARIES[0], "-p", BINARIES[1]]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            [*command, "--target-dir", str(target)],
            cwd=NATIVE,
            env={**os.environ, "ARCHKEEL_VERSION": package_version()},
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stderr
    return target / "debug"


def _self_check(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The core frame and the Python result of the report of `native/archkeel.toml`."""
    install = tmp_path / "native"
    install.mkdir()
    for name in BINARIES:
        binary = install / f"{name}{SUFFIX}"
        shutil.copy2(built / binary.name, binary)
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        (install / f"{binary.name}.sha256").write_text(digest, encoding="ascii")
    monkeypatch.setattr(observe, "_NATIVE_DIRECTORY", install)
    monkeypatch.delenv(native_core.SWITCH_VARIABLE, raising=False)
    monkeypatch.delenv(observe.NATIVE_STORE, raising=False)
    frames: list[Any] = []

    def decide(self: native_core.NativeCore, result: Any, root: Path, config: Any) -> Any:
        assert self.binary is not None
        read = partial(native_core.read_inside, root)
        frames.append(self.run(self.binary, config, read, self.replies[0], None))
        return result

    monkeypatch.setattr(native_core.NativeCore, "decide", decide)
    monkeypatch.chdir(ROOT)
    output = io.StringIO()
    artifact = tmp_path / "out" / "architecture.json"
    with contextlib.redirect_stdout(output):
        main(
            ["report", "--config", "native/archkeel.toml", "--json", "--output", str(artifact)]
            + ["--native-core"]
        )
    [frame] = frames
    return asdict(frame), json.loads(output.getvalue())


def test_the_core_decides_each_rule_of_the_self_contract(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame, result = _self_check(built, tmp_path, monkeypatch)
    python = {row["id"]: row["status"] for row in result["rule_assessments"]}
    pinned = json.loads((NATIVE / "expected-gaps.json").read_text())["rules"]
    assert python == pinned
    core = {rule: row["status"] for rule, row in frame["rules"].items()}
    assert set(core) == set(python), set(core) ^ set(python)
    assert len(core) == 43
    # No rule names a part of the scope proof: each one has a decision.
    assert [gap for gap in frame["gaps"] if gap["kind"] == "scope_proof"] == []
    assert list(frame["gaps"]) == []
    beyond = set(frame["beyond"])
    for rule, status in core.items():
        if rule in beyond:
            assert (status, python[rule]) == ("PASS", "UNKNOWN"), rule
        else:
            assert status == python[rule], rule
    assert Counter(python.values()) == {"UNKNOWN": 42, "FAIL": 1}
    assert Counter(core.values()) == {"PASS": 23, "UNKNOWN": 19, "FAIL": 1}
    assert beyond == {rule for rule, status in core.items() if status == "PASS"}
    # The run keeps the kept gaps; it never passes.
    assert frame["status"] == "FAIL"
    assert frame["scope"].startswith("incomplete scope: 39 gaps between two modules")
