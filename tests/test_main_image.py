# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the container image of the rolling main build."""

import subprocess
from pathlib import Path

import pytest

from tools import publish_main_image as image

IMAGE = "ghcr.io/rapiddweller/archkeel"
OLD = "a" * 40
NEW = "b" * 40


class Registry:
    """A registry and a local image store that record what the tool does."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.remote: dict[str, str] = {}
        self.local: dict[str, str] = {}
        self.calls: list[tuple[str, ...]] = []
        self.head = NEW
        self.smoke_fails = False
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GITHUB_REPOSITORY", "rapiddweller/archkeel")
        monkeypatch.setattr(image, "command", self.command)
        monkeypatch.setattr(image, "exists", lambda name: name in self.remote)

    def publish(self, sha: str, wheel_sha: str | None = None, head: str | None = None) -> None:
        for old in (self.tmp_path / "image-context").glob("*.whl"):
            old.unlink()
        (self.tmp_path / "image-context").mkdir(exist_ok=True)
        abbreviated = (wheel_sha or sha)[:9]
        wheel = f"archkeel-4.0.2.dev1+g{abbreviated}-py3-none-manylinux_2_17_x86_64.whl"
        (self.tmp_path / "image-context" / wheel).write_bytes(b"wheel")
        self.head = head or sha
        self.monkeypatch.setenv("GITHUB_SHA", sha)
        image.main()

    def command(self, *args: str) -> str:
        self.calls.append(args)
        match args[:2]:
            case ("docker", "build"):
                self.local[args[args.index("--tag") + 1]] = next(
                    arg.split("=", 1)[1] for arg in args if arg.startswith(image.REVISION)
                )
            case ("docker", "run"):
                if self.smoke_fails:
                    raise subprocess.CalledProcessError(1, args)
            case ("docker", "push"):
                self.remote[args[2]] = self.local[args[2]]
            case ("docker", "pull"):
                self.local[args[2]] = self.remote[args[2]]
            case ("docker", "tag"):
                self.local[args[3]] = self.local[args[2]]
            case ("docker", "image"):
                return self.local[args[3]] + "\n"
            case ("gh", "api"):
                return self.head + "\n"
        return ""

    def pushes(self) -> list[str]:
        return [call[2] for call in self.calls if call[:2] == ("docker", "push")]


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Registry:
    return Registry(monkeypatch, tmp_path)


def test_two_commits_move_the_tag_and_keep_the_old_image(registry: Registry) -> None:
    registry.publish(OLD)
    registry.publish(NEW)
    assert registry.remote[f"{IMAGE}:{image.TAG}"] == NEW
    assert registry.remote[f"{IMAGE}:sha-{OLD}"] == OLD
    assert registry.remote[f"{IMAGE}:sha-{NEW}"] == NEW
    # The moving tag is pushed only after the image of the commit.
    assert registry.pushes()[2:] == [f"{IMAGE}:sha-{NEW}", f"{IMAGE}:{image.TAG}"]


def test_a_rerun_reuses_the_tested_image(registry: Registry) -> None:
    registry.publish(OLD)
    builds = [call for call in registry.calls if call[:2] == ("docker", "build")]
    registry.publish(OLD)
    assert [call for call in registry.calls if call[:2] == ("docker", "build")] == builds
    assert registry.remote[f"{IMAGE}:{image.TAG}"] == OLD


def test_a_failed_smoke_test_keeps_the_old_tag(registry: Registry) -> None:
    registry.publish(OLD)
    registry.smoke_fails = True
    with pytest.raises(subprocess.CalledProcessError):
        registry.publish(NEW)
    assert registry.remote[f"{IMAGE}:{image.TAG}"] == OLD
    assert f"{IMAGE}:sha-{NEW}" not in registry.remote


def test_an_older_wheel_does_not_get_this_commit(registry: Registry) -> None:
    with pytest.raises(ValueError, match="was not built from"):
        registry.publish(NEW, wheel_sha=OLD)
    assert registry.calls == []


def test_an_older_run_does_not_move_the_tag_over_a_newer_main(registry: Registry) -> None:
    registry.publish(NEW)
    registry.publish(OLD, head=NEW)
    assert registry.remote[f"{IMAGE}:{image.TAG}"] == NEW
    assert registry.remote[f"{IMAGE}:sha-{OLD}"] == OLD
