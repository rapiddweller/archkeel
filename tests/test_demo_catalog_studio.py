# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 Studio lifecycle catalog harness tests."""

import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from fixtures.demo_catalog_studio import CATALOG, _cleanup_group, _fixture, _run_cli


def test_studio_demo_uses_only_supported_profiles(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    _fixture(root)
    assert (root / "src/demo/service.ts").is_file()
    assert (root / "tsconfig.json").is_file()
    assert not list(root.rglob("*.py"))
    assert all({v.active_language, v.requested_language} <= {"rust", "typescript"} for v in CATALOG)


def test_demo_cli_ignores_inherited_git_repository_redirection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    subprocess.run(["git", "init", "-q", str(protected)], check=True)
    (protected / "sentinel").write_text("keep", encoding="utf-8")
    subprocess.run(["git", "-C", str(protected), "add", "sentinel"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(protected),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "protected",
        ],
        check=True,
    )
    git_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    git_environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def protected_git(*arguments: str) -> bytes:
        return subprocess.check_output(
            ["git", "-C", str(protected), *arguments], env=git_environment
        )

    before_head = protected_git("rev-parse", "HEAD")
    before_status = protected_git("status", "--porcelain")
    before_index = (protected / ".git" / "index").read_bytes()
    before_sentinel = (protected / "sentinel").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(protected / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(protected))
    captured: dict[str, object] = {}
    child = Mock(returncode=0)
    child.communicate.return_value = ("", None)

    def fake_popen(_command: list[str], **kwargs: object) -> Mock:
        captured.update(kwargs)
        return child

    with monkeypatch.context() as patcher:
        patcher.setattr(subprocess, "Popen", fake_popen)
        _run_cli(tmp_path / "project", tmp_path / "cache", "--stop")

    child_environment = captured["env"]
    assert isinstance(child_environment, dict)
    assert "GIT_DIR" not in child_environment
    assert "GIT_WORK_TREE" not in child_environment
    assert protected_git("rev-parse", "HEAD") == before_head
    assert protected_git("status", "--porcelain") == before_status
    assert (protected / ".git" / "index").read_bytes() == before_index
    assert (protected / "sentinel").read_bytes() == before_sentinel


def test_fixture_ignores_inherited_git_repository_redirection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    protected = tmp_path / "protected"
    protected.mkdir()
    subprocess.run(["git", "init", "-q", str(protected)], check=True)
    (protected / "sentinel").write_text("keep", encoding="utf-8")
    subprocess.run(["git", "-C", str(protected), "add", "sentinel"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(protected),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "protected",
        ],
        check=True,
    )
    before = subprocess.check_output(["git", "-C", str(protected), "rev-parse", "HEAD"])
    monkeypatch.setenv("GIT_DIR", str(protected / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(protected))

    _fixture(root)

    after = subprocess.check_output(["git", "-C", str(protected), "rev-parse", "HEAD"])
    assert after == before
    assert (protected / "sentinel").read_text(encoding="utf-8") == "keep"
    assert (root / ".git").is_dir()


@pytest.mark.skipif(os.name == "nt", reason="the demo process-group cleanup is POSIX-only")
def test_cleanup_group_survives_a_terminate_exit_race() -> None:
    process = Mock(pid=123, poll=Mock(side_effect=[None, None]))
    process.terminate.side_effect = ProcessLookupError

    with patch("fixtures.demo_catalog_studio.os.killpg") as killpg:
        _cleanup_group(process)

    killpg.assert_called_once_with(123, signal.SIGKILL)
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
