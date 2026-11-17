# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the rolling main build publication."""

import json
from pathlib import Path

import pytest

from tools import publish_main_build as build


def test_publish_requires_a_complete_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dist").mkdir()
    for tag in list(build.TAGS)[:-1]:
        (tmp_path / "dist" / f"archkeel-5.0.0.dev1-{tag}.whl").write_bytes(b"wheel")
    with pytest.raises(ValueError, match="six wheels"):
        build.main()


def test_publish_lists_and_checksums_each_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_REPOSITORY", "rapiddweller/archkeel")
    (tmp_path / "dist").mkdir()
    for tag in build.TAGS:
        (tmp_path / "dist" / f"archkeel-5.0.0.dev1-{tag}.whl").write_bytes(b"wheel")
    calls: list[tuple[str, ...]] = []

    def command(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("git", "show"):
            return "2026-11-17T00:00:00Z"
        if args[:2] == ("gh", "api"):
            return json.dumps([[]])
        return ""

    monkeypatch.setattr(build, "command", command)
    build.main()
    assert len((tmp_path / "dist" / "SHA256SUMS").read_text().splitlines()) == 6
    notes = (tmp_path / "dist" / "notes.txt").read_text()
    assert all(tag in notes for tag in build.TAGS)
    assert build.LINKS in notes
    assert any(args[:3] == ("gh", "release", "create") for args in calls)


def test_publish_replaces_the_old_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_REPOSITORY", "rapiddweller/archkeel")
    (tmp_path / "dist").mkdir()
    for tag in build.TAGS:
        (tmp_path / "dist" / f"archkeel-5.0.0.dev1-{tag}.whl").write_bytes(b"wheel")
    calls: list[tuple[str, ...]] = []

    def command(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("gh", "api") and "--slurp" in args:
            return json.dumps([[{"tag_name": "main-build", "assets": [{"name": "old.whl"}]}]])
        return ""

    monkeypatch.setattr(build, "command", command)
    build.main()
    assert any(args[:3] == ("gh", "release", "upload") for args in calls)
    assert any(
        args[:3] == ("gh", "release", "delete-asset") and "old.whl" in args for args in calls
    )
    assert any(args[:3] == ("gh", "api", "--method") and "force=true" in args for args in calls)
