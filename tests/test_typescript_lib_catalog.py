# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard-global catalog follows the compiler's own lib files for each `lib` and target."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TYPESCRIPT_LIB = ROOT / "tools/browser-runtime/node_modules/typescript/lib"


def test_generated_catalog_is_the_one_the_pinned_compiler_produces():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    result = subprocess.run(
        [sys.executable, "-m", "tools.typescript_libs", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# AD-261: the Python collector and the native collector read this one data file. Every digest below
# was printed from the generated Python module before it became JSON, so a change in what a lookup
# returns shows as a different digest, not as a silent drift of the data file.
CATALOG_DIGEST = "b2b16641f75c995f0efa160c1cc391922f72f7a3bd3cb30173f74d43ee31ec67"
LOOKUP_DIGEST = "a1f1f155d4e8a670f423db8b5efb366390c7d68e089778f8c143013c118322d7"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _generator():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    from tools import typescript_libs

    return typescript_libs


def test_check_compares_bytes_and_write_emits_lf(tmp_path, monkeypatch):
    generator = _generator()
    target = tmp_path / "standard_libs.json"
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "OUTPUT", target)
    expected = generator.build_catalog().encode("utf-8")
    assert generator.main(["--write"]) == 0
    assert target.read_bytes() == expected
    assert generator.main(["--check"]) == 0
    # The same text with Windows line endings is a different file: Rust embeds the bytes.
    target.write_bytes(expected.replace(b"\n", b"\r\n"))
    assert generator.main(["--check"]) == 1
    target.write_bytes(expected)
    target.write_bytes(b"{}\n")
    assert generator.main(["--check"]) == 1
