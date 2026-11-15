# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1095: a bundled core binary is checked again at the start, not only at the lookup."""

import hashlib
import os
import sysconfig
from pathlib import Path

import pytest
from core_support import run
from rust_repository import repository

from archkeel.cli import core_only
from archkeel.cli.core_binary import confirm, locate_core
from archkeel.cli.core_json import CoreError
from archkeel.cli.native_scan import exchange

EXE = sysconfig.get_config_var("EXE") or ""
SCRIPT = b"#!/bin/sh\nexit 0\n"


def bundle(package: Path, content: bytes = SCRIPT) -> Path:
    native = package / "_native"
    native.mkdir(parents=True)
    binary = native / f"archkeel-core{EXE}"
    binary.write_bytes(content)
    binary.chmod(0o755)
    binary.with_name(binary.name + ".sha256").write_text(
        hashlib.sha256(content).hexdigest(), encoding="ascii"
    )
    return binary


def test_a_bundled_core_that_changes_after_the_lookup_is_refused_at_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = bundle(tmp_path / "package")
    assert locate_core(tmp_path / "package") == binary
    root = repository(tmp_path / "project", binary)

    def changed_after_the_lookup() -> Path:
        binary.write_bytes(b"#!/bin/sh\necho changed\n")
        return binary

    monkeypatch.setattr(core_only, "locate_core", changed_after_the_lookup)
    code, result = run("validate", "--root", str(root))
    assert code == 2 and result["status"] == "UNKNOWN"
    assert "digest does not match" in result["refusal"]["message"], result


def test_confirm_refuses_a_bundled_core_whose_digest_file_is_gone(tmp_path: Path) -> None:
    binary = bundle(tmp_path / "package")
    binary.with_name(binary.name + ".sha256").unlink()
    with pytest.raises(CoreError, match="missing"):
        confirm(binary)


def test_confirm_leaves_a_checkout_binary_alone(tmp_path: Path) -> None:
    binary = tmp_path / "target" / "release" / f"archkeel-core{EXE}"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"not checked")
    confirm(binary)


@pytest.mark.skipif(os.name == "nt", reason="the test core is a POSIX shell script")
def test_an_unchanged_bundled_core_starts(tmp_path: Path) -> None:
    binary = bundle(tmp_path / "package")
    assert exchange(str(binary), "scan", b"{}") == (b"", 0)
