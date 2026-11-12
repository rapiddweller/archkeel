# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390 point 2: the trust root of stage 1 is the shell, which starts only the bundled binaries
with their recorded digests. The fixtures are the fixtures of `test_cli_native_core`."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from graph_report_support import commit_tree
from test_cli_native_core import (
    _CYCLE,
    SUFFIX,
    built,
    core_notes,
    diagnostics,
    install,
    posix,
    report,
    repository,
)

from archkeel.cli import observe

__all__ = ["built", "install"]  # the fixtures of the core and the Rust collector of one build

FORGED = """#!{python}
import sys
sys.stdout.write("a forged reply that keeps the digest of this build")
"""


def _script(path: Path, text: str) -> None:
    path.write_text(text.format(python=sys.executable))
    path.chmod(0o755)


@posix
def test_a_rust_collector_with_a_stale_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    """Review B1: the collector is a script that prints a forged reply; its `.sha256` is stale."""
    root = repository(tmp_path / "repo", install, components=_CYCLE)
    _script(install / f"archkeel-rust-collector{SUFFIX}", FORGED)
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is not verified" in diagnostics(result)
    assert (result["declared_rules"], written) == ("UNKNOWN", b"")


def test_a_rust_collector_without_its_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    root = repository(tmp_path / "repo", install)
    (install / f"archkeel-rust-collector{SUFFIX}.sha256").unlink()
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is missing" in diagnostics(result)
    assert written == b""


@posix
def test_a_typescript_collector_without_its_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    """Without the switch the host takes the Python collector here (AD-352); with it, the binary
    that is present must have its digest."""
    root = tmp_path / "ts"
    (root / "src").mkdir(parents=True)
    (root / "src/a.ts").write_text("export const a = 1;\n")
    (root / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}, "include": ["src"]}')
    contract = {"schema_version": "2.1.0", "components": [], "rules": []}
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "src"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    )
    commit_tree(root)
    _script(install / f"archkeel-typescript-collector{SUFFIX}", FORGED)
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is missing" in diagnostics(result)
    assert written == b""


@posix
def test_the_repository_and_the_environment_cannot_redirect_the_binaries(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignored: a core or a collector in the scanned repository or on `PATH` never runs. The
    binaries come only from the directory of the package (`observe._NATIVE_DIRECTORY`)."""
    root = repository(tmp_path / "repo", install)
    marker = tmp_path / "marker"
    planted = f"#!{sys.executable}\nopen({str(marker)!r}, 'a').write('ran')\n"
    for directory in (root, root / "_native", tmp_path / "bin"):
        directory.mkdir(exist_ok=True)
        for name in ("archkeel-core", "archkeel-rust-collector"):
            (directory / name).write_text(planted)
            (directory / name).chmod(0o755)
            (directory / f"{name}.sha256").write_text(hashlib.sha256(planted.encode()).hexdigest())
    commit_tree(root)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    code, result, _ = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (0, "PASS")
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert not marker.exists()


def test_a_store_variable_is_refused_with_the_switch(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused: `ARCHKEEL_NATIVE_STORE` would redirect the decode of the Python engine."""
    root = repository(tmp_path / "repo", install)
    monkeypatch.setenv(observe.NATIVE_STORE, str(tmp_path / "store"))
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "ARCHKEEL_NATIVE_STORE redirects the decode" in diagnostics(result)
    assert written == b""
