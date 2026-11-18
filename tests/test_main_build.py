# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the rolling main build publication."""

import hashlib
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
            if sum(call[:2] == ("gh", "api") for call in calls) == 1:
                return json.dumps([[]])
            assets = list((tmp_path / "dist").glob("*.whl")) + [tmp_path / "dist" / "SHA256SUMS"]
            return json.dumps(
                [
                    [
                        {
                            "tag_name": "main-build",
                            "draft": True,
                            "target_commitish": "a" * 40,
                            "assets": [
                                {
                                    "name": item.name,
                                    "digest": "sha256:"
                                    + hashlib.sha256(item.read_bytes()).hexdigest(),
                                }
                                for item in assets
                            ],
                        }
                    ]
                ]
            )
        return ""

    monkeypatch.setattr(build, "command", command)
    build.main()
    assert len((tmp_path / "dist" / "SHA256SUMS").read_text().splitlines()) == 6
    notes = (tmp_path / "dist" / "notes.txt").read_text()
    assert all(tag in notes for tag in build.TAGS)
    assert build.LINKS in notes
    create = next(args for args in calls if args[:3] == ("gh", "release", "create"))
    assert "--draft" in create
    assert any(args[:3] == ("gh", "release", "edit") and "--draft=false" in args for args in calls)


def test_publish_preserves_the_old_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    with pytest.raises(ValueError, match="already exists"):
        build.main()
    assert not any(
        args[:3] in (("gh", "release", "upload"), ("gh", "release", "delete-asset"))
        for args in calls
    )


def test_publish_does_not_expose_an_incomplete_draft(
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
        if args[:2] == ("gh", "api"):
            if sum(call[:2] == ("gh", "api") for call in calls) == 1:
                return json.dumps([[]])
            return json.dumps(
                [
                    [
                        {
                            "tag_name": "main-build",
                            "draft": True,
                            "target_commitish": "a" * 40,
                            "assets": [],
                        }
                    ]
                ]
            )
        return ""

    monkeypatch.setattr(build, "command", command)
    with pytest.raises(ValueError, match="draft assets"):
        build.main()
    assert not any(args[:3] == ("gh", "release", "edit") for args in calls)
