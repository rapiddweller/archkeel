"""AD-11 Studio lifecycle catalog harness tests."""

import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from fixtures.demo_catalog_studio import _cleanup_group, _fixture


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
