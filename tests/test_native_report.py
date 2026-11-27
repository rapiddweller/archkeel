# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The model, evaluator and engine-frame barriers (AD-381, AD-388)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import ensure_target_dir
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
# The attempts of AD-381: the run proof in the barrier crate, the report and the evaluator in
# their own document tests (the barrier crate is below them in the crate order, AD-382).
# AD-385 adds the attempts of the models of a tree to the barrier crate.
BARRIER = NATIVE / "model-barrier/src/lib.rs"
MODEL_BARRIERS = [
    NATIVE / "model/src" / f"{name}.rs" for name in ("ids", "scope", "run", "verdict")
]
BARRIER_FILES = [BARRIER, *MODEL_BARRIERS, NATIVE / "report/src/lib.rs", NATIVE / "eval/src/lib.rs"]
CRATES = ("archkeel-model", "archkeel-model-barrier", "archkeel-report", "archkeel-eval")


def test_each_barrier_attempt_of_ad_381_fails_with_its_error_code() -> None:
    """S2 of the review of #1080: a stable rustdoc does not check the error code of a
    `compile_fail` test. `RUSTC_BOOTSTRAP=1` makes it check: rustdoc compiles each attempt on
    its own and fails when the named code is not the error. Each attempt of AD-381 names one."""
    for path in BARRIER_FILES:
        fences = re.findall(
            r"^//[!/]\s*```(compile_fail\S*)$", path.read_text(encoding="utf-8"), re.M
        )
        assert fences and all(re.fullmatch(r"compile_fail,E\d{4}", fence) for fence in fences), path
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native report tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    command = [cargo, "test", "--locked", "-q", "--doc"]
    for crate in CRATES:
        command += ["-p", crate]
    ensure_target_dir(NATIVE)
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command,
            cwd=NATIVE,
            env={**os.environ, "RUSTC_BOOTSTRAP": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stdout + done.stderr


def test_barriers_have_no_missing_name_errors(tmp_path: Path) -> None:
    """An expected privacy error must not hide an unrelated missing-name error."""
    cargo, rustc = shutil.which("cargo"), shutil.which("rustc")
    if cargo is None or rustc is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo and rustc for the model barriers.")
        pytest.skip("cargo and rustc are required for the model barriers.")
    env = {**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")}
    build = subprocess.run(
        [
            cargo,
            "build",
            "--locked",
            "--message-format=json",
            "-p",
            "archkeel-model-barrier",
            "-p",
            "archkeel-report",
        ],
        cwd=NATIVE,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    artifacts = {}
    for line in build.stdout.splitlines():
        message = json.loads(line)
        if message.get("reason") == "compiler-artifact":
            name = message["target"]["name"]
            for filename in message["filenames"]:
                if name in (
                    "archkeel_model",
                    "archkeel_contract",
                    "archkeel_eval",
                    "archkeel_report",
                ) and filename.endswith(".rlib"):
                    artifacts[name] = filename
    assert set(artifacts) == {
        "archkeel_model",
        "archkeel_contract",
        "archkeel_eval",
        "archkeel_report",
    }
    for path in BARRIER_FILES:
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(
            r"(?m)^//[!/]\s*```compile_fail,(E\d{4})\n(.*?)^//[!/]\s*```$",
            text,
            re.S,
        )
        assert blocks, path
        for index, (expected, block) in enumerate(blocks):
            code = re.sub(r"(?m)^//[!/]\s?", "", block)
            source = tmp_path / "probe.rs"
            source.write_text("fn main() {\n" + code + "\n}\n", encoding="utf-8")
            command = [
                rustc,
                "--edition=2021",
                "--crate-name=barrier_probe",
                "--emit=link",
                str(source),
                "-L",
                f"dependency={tmp_path / 'target' / 'debug' / 'deps'}",
                "-o",
                str(tmp_path / "probe"),
            ]
            for name, filename in artifacts.items():
                command.extend(["--extern", f"{name}={filename}"])
            result = subprocess.run(
                command, cwd=NATIVE, capture_output=True, text=True, check=False
            )
            errors = set(re.findall(r"error\[(E\d{4})\]", result.stderr))
            missing = {"E0412", "E0422", "E0425", "E0432", "E0433", "E0463"}
            assert result.returncode != 0 and expected in errors and errors.isdisjoint(missing), (
                path,
                index,
                result.stderr,
            )
