# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-352: the host starts the native collector of an install only with the digest of its wheel.

Consumer: `analyzer/bundled.py` and `observer_for`. A platform wheel carries the binary and the
file `<binary>.sha256`. The host gives the binary the producer kind `bundled`, checks its file
against the digest before each start and keeps the Python collector for an install without the
pair. A configured collector stays `external` or `pinned`, whatever an install holds.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from collector_pin import pin_of

from archkeel.analyzer import process as process_owner
from archkeel.analyzer.runtime import package_version
from archkeel.check.report import run_report
from archkeel.cli import observe as bundled
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.state_facts import ProducerKind

ROOT = Path(__file__).parents[1]
FIXTURE = "fixtures/H-typescript"


def _install(directory: Path, binary: Path, digest: str | None = None) -> Path:
    """An `_native` directory with the binary and the file of its digest."""
    directory.mkdir(parents=True)
    copy = shutil.copy2(binary, bundled.executable(bundled.TYPESCRIPT_COLLECTOR, directory))
    recorded = digest or pin_of(str(copy)).removeprefix("sha256:")
    Path(f"{copy}{bundled.DIGEST_SUFFIX}").write_text(recorded, encoding="ascii")
    return directory


def _project(root: Path) -> Path:
    """A copy of the TypeScript fixture, committed: the host reads the head of the repository."""
    shutil.copytree(
        ROOT / FIXTURE,
        root,
        ignore=shutil.ignore_patterns("node_modules", ".git"),
        dirs_exist_ok=True,
    )
    for command in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
    ):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)
    return root


def _scan(root: Path, directory: Path | None, **options: object):  # type: ignore[no-untyped-def]
    config = load_config(root)
    observer = observer_for(
        config.language,
        tsconfig="tsconfig.json",
        native_directory=directory,
        **options,  # type: ignore[arg-type]
    )
    # The debug binary has no build version; a wheel sets it to the version of the host (AD-317).
    launched = directory is not None and bundled.locate(bundled.TYPESCRIPT_COLLECTOR, directory)
    version = "0+unknown" if launched else package_version()
    with mock.patch.object(process_owner, "package_version", lambda: version):
        return run_report(root, config=config, analyzer=observer)


def test_an_install_with_the_binary_and_its_digest_is_located(
    native_binary: Path, tmp_path: Path
) -> None:
    directory = _install(tmp_path / "_native", native_binary)
    found = bundled.locate(bundled.TYPESCRIPT_COLLECTOR, directory)
    assert found is not None
    assert found.path == str(bundled.executable(bundled.TYPESCRIPT_COLLECTOR, directory))
    assert found.digest == pin_of(found.path)


def test_an_install_without_the_pair_has_no_bundled_collector(
    native_binary: Path, tmp_path: Path
) -> None:
    binary = bundled.executable(bundled.TYPESCRIPT_COLLECTOR, tmp_path / "none")
    assert bundled.locate(bundled.TYPESCRIPT_COLLECTOR, tmp_path / "none") is None
    directory = _install(tmp_path / "_native", native_binary)
    Path(f"{binary.parent.parent / '_native' / binary.name}{bundled.DIGEST_SUFFIX}").unlink()
    assert bundled.locate(bundled.TYPESCRIPT_COLLECTOR, directory) is None
    shorter = _install(tmp_path / "short", native_binary, digest="abc")
    assert bundled.locate(bundled.TYPESCRIPT_COLLECTOR, shorter) is None
    upper = _install(tmp_path / "upper", native_binary, digest="A" * 64)
    assert bundled.locate(bundled.TYPESCRIPT_COLLECTOR, upper) is None


def test_the_bundled_collector_gives_a_pass_and_records_its_kind(
    native_binary: Path, tmp_path: Path
) -> None:
    root = _project(tmp_path / "repo")
    directory = _install(tmp_path / "_native", native_binary)
    result, artifact = _scan(root, directory)
    assert artifact is not None
    assert json.loads(artifact)["producer_kind"] == ProducerKind.BUNDLED.value
    assert result.observation_complete.value == "PASS"
    assert result.exit_code == 0
    assert not [item for item in result.diagnostics if item.kind.value == "incomplete_scan"]


def test_an_install_without_the_pair_refuses_without_a_fallback(tmp_path: Path) -> None:
    root = _project(tmp_path / "repo")
    result, artifact = _scan(root, tmp_path / "nowhere")
    assert artifact is None
    assert result.exit_code == 2
    assert any(item.kind.value == "missing_tool" for item in result.diagnostics)


def test_a_binary_that_does_not_have_the_recorded_digest_is_not_started(
    native_binary: Path, tmp_path: Path
) -> None:
    root = _project(tmp_path / "repo")
    wrong = hashlib.sha256(b"another binary").hexdigest()
    directory = _install(tmp_path / "_native", native_binary, digest=wrong)
    result, _ = _scan(root, directory)
    assert result.observation_complete.value != "PASS"
    assert result.exit_code != 0
    # The reason names both digests: the file that is there and the digest that the wheel recorded.
    assert any(f"sha256:{wrong}" in item.unknown_claim for item in result.diagnostics)


def test_a_binary_inside_the_scanned_repository_is_still_the_bundled_collector(
    native_binary: Path, tmp_path: Path
) -> None:
    """A virtual environment in the repository holds the install that runs the host."""
    root = tmp_path / "repo"
    directory = _install(root / ".venv" / "archkeel" / "_native", native_binary)
    _project(root)
    result, artifact = _scan(root, directory)
    assert artifact is not None
    assert json.loads(artifact)["producer_kind"] == "bundled"
    assert not [item for item in result.diagnostics if "digest" in item.unknown_claim]


@pytest.mark.parametrize("pinned", [False, True])
def test_a_configured_collector_stays_external_or_pinned_whatever_the_install_holds(
    native_binary: Path, tmp_path: Path, pinned: bool
) -> None:
    root = _project(tmp_path / "repo")
    directory = _install(tmp_path / "_native", native_binary)
    config = load_config(root)
    observer = observer_for(
        config.language,
        collector_argv=(str(native_binary),),
        pinned_digest=pin_of(str(native_binary)) if pinned else None,
        native_directory=directory,
    )
    expected = ProducerKind.PINNED if pinned else ProducerKind.EXTERNAL
    assert observer.producer is expected
