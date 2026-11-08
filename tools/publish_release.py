# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify a tag's draft assets before PyPI, then publish that same release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import quote

# AD-317: the platform wheels of the native collector, one for each pinned build image of Full.
# The release workflow adds them to `dist/` only when PUBLISH_NATIVE_WHEELS is "true".
PLATFORM_TAGS = (
    "py3-none-macosx_10_12_x86_64",
    "py3-none-macosx_11_0_arm64",
    "py3-none-manylinux_2_17_x86_64",
    "py3-none-manylinux_2_17_aarch64",
    "py3-none-musllinux_1_2_x86_64",
    "py3-none-win_amd64",
)


def _run(*args: str) -> bytes:
    return subprocess.run(args, check=True, stdout=subprocess.PIPE).stdout


class ReleaseAsset(TypedDict):
    id: int
    name: str


class Release(TypedDict):
    id: int
    tag_name: str
    target_commitish: str
    draft: bool
    body: str | None
    assets: list[ReleaseAsset]


class GitObject(TypedDict):
    type: Literal["commit", "tag"]
    sha: str


def _api(repository: str, path: str, *args: str) -> object:
    value: object = json.loads(_run("gh", "api", f"repos/{repository}/{path}", *args))
    return value


def _release_asset(value: object) -> ReleaseAsset:
    if not isinstance(value, dict):
        raise ValueError("release asset must be an object")
    identity, name = value.get("id"), value.get("name")
    if type(identity) is not int or identity <= 0 or not isinstance(name, str) or not name:
        raise ValueError("invalid release asset identity")
    return {"id": identity, "name": name}


def _release(value: object) -> Release:
    if not isinstance(value, dict):
        raise ValueError("release must be an object")
    identity, tag, commit = value.get("id"), value.get("tag_name"), value.get("target_commitish")
    draft, body, assets = value.get("draft"), value.get("body"), value.get("assets")
    if (
        type(identity) is not int
        or identity <= 0
        or not isinstance(tag, str)
        or not tag
        or not isinstance(commit, str)
        or not commit
        or not isinstance(draft, bool)
        or (body is not None and not isinstance(body, str))
        or not isinstance(assets, list)
    ):
        raise ValueError("invalid release metadata")
    return {
        "id": identity,
        "tag_name": tag,
        "target_commitish": commit,
        "draft": draft,
        "body": body,
        "assets": [_release_asset(asset) for asset in assets],
    }


def _git_object(value: object) -> GitObject:
    if not isinstance(value, dict) or not isinstance(value.get("object"), dict):
        raise ValueError("Git object identity is missing")
    obj = value["object"]
    kind, sha = obj.get("type"), obj.get("sha")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("invalid Git object SHA")
    if kind == "commit":
        return {"type": "commit", "sha": sha}
    if kind == "tag":
        return {"type": "tag", "sha": sha}
    raise ValueError("tag must ultimately name a commit")


def _tag_commit(repository: str, tag: str) -> str:
    ref = _api(repository, f"git/ref/tags/{quote(tag, safe='')}")
    if not isinstance(ref, dict) or ref.get("ref") != f"refs/tags/{tag}":
        raise ValueError("GitHub did not return the exact tag ref")
    obj = _git_object(ref)
    seen: set[str] = set()
    while obj["type"] == "tag":
        if obj["sha"] in seen:
            raise ValueError("cyclic annotated tag")
        seen.add(obj["sha"])
        obj = _git_object(_api(repository, f"git/tags/{obj['sha']}"))
    return obj["sha"]


def _draft(repository: str, tag: str, commit: str) -> Release | None:
    if _tag_commit(repository, tag) != commit:
        raise ValueError("release tag does not name the expected commit")
    pages = _api(repository, "releases?per_page=100", "--paginate", "--slurp")
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("invalid release inventory")
    matches = [
        release
        for page in pages
        for value in page
        if (release := _release(value))["tag_name"] == tag
    ]
    if len(matches) > 1:
        raise ValueError("multiple releases name this tag")
    if not matches:
        return None
    release = matches[0]
    if release["draft"] is not True or release["target_commitish"] != commit:
        raise ValueError("refusing a published release or a draft for another commit")
    return release


def _release_body(notes: Path, repository: str, tag: str, version: str) -> str:
    body = notes.read_text().split("\n# ", 1)[0].strip()
    if not re.match(rf"# ArchKeel {re.escape(version)}(?:\s|$)", body):
        raise ValueError("first release-notes section does not match the tag")
    body = re.sub(r"\n---\s*$", "", body).rstrip()
    return (
        re.sub(
            r"\]\((docs/[^)]+)\)",
            lambda match: (
                f"](https://github.com/{repository}/blob/{quote(tag, safe='')}/{match[1]})"
            ),
            body,
        )
        + "\n"
    )


def _assets(dist: Path, plugin: Path, version: str) -> tuple[list[Path], dict[str, Path]]:
    pure = dist / f"archkeel-{version}-py3-none-any.whl"
    sdist = dist / f"archkeel-{version}.tar.gz"
    platform = [dist / f"archkeel-{version}-{tag}.whl" for tag in PLATFORM_TAGS]
    found = set(dist.glob("*.whl")) | set(dist.glob("*.tar.gz"))
    if pure not in found or sdist not in found:
        raise ValueError("expected the pure wheel and the sdist for this tag")
    if found - {pure, sdist} - set(dist.glob(f"archkeel-{version}-*.whl")):
        raise ValueError("distribution directory contains another version")
    if found - {pure, sdist} not in (set(), set(platform)):
        raise ValueError("expected none or all six platform wheels for this tag")
    distributions = [pure, *(platform if platform[0] in found else []), sdist]
    archive = plugin / f"archkeel-plugin-{version}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    if set(plugin.iterdir()) != {archive, checksum}:
        raise ValueError("plugin directory must contain only the archive and checksum")
    paths = [*distributions, archive, checksum]
    if any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0 for path in paths):
        raise ValueError("release assets must be nonempty regular files")
    expected = hashlib.sha256(archive.read_bytes()).hexdigest() + f"  {archive.name}\n"
    if checksum.read_text() != expected:
        raise ValueError("plugin checksum differs from its archive")
    return distributions, {path.name: path for path in paths}


def _verify_assets(
    repository: str, release: Release, assets: dict[str, Path], *, complete: bool
) -> set[str]:
    remote = release["assets"]
    names = [asset["name"] for asset in remote]
    if len(set(names)) != len(names) or not set(names) <= assets.keys():
        raise ValueError("draft contains unexpected or duplicate assets")
    if complete and set(names) != assets.keys():
        raise ValueError("draft is missing release assets")
    for asset in remote:
        actual = _run(
            "gh",
            "api",
            f"repos/{repository}/releases/assets/{asset['id']}",
            "-H",
            "Accept: application/octet-stream",
        )
        if actual != assets[asset["name"]].read_bytes():
            raise ValueError(f"downloaded release asset differs: {asset['name']}")
    return set(names)


def publish(repository: str, tag: str, commit: str, dist: Path, plugin: Path, notes: Path) -> None:
    version = tag.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:rc|a|b)\d+)?", version):
        raise ValueError("unsupported release tag")
    if _run("git", "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("checkout does not match the release commit")
    body = _release_body(notes, repository, tag, version)
    distributions, assets = _assets(dist, plugin, version)
    release = _draft(repository, tag, commit)
    if release is None:
        with tempfile.TemporaryDirectory() as directory:
            note_file = Path(directory) / "notes.md"
            note_file.write_text(body)
            _run(
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                repository,
                "--draft",
                "--target",
                commit,
                "--verify-tag",
                "--title",
                tag,
                "--notes-file",
                str(note_file),
                *(("--prerelease",) if re.search(r"[a-z]", version) else ()),
            )
        release = _draft(repository, tag, commit)
    if release is None:
        raise ValueError("draft release was not created")
    release_id = release["id"]
    if release["body"] != body:
        _api(repository, f"releases/{release_id}", "--method", "PATCH", "-f", f"body={body}")
    existing = _verify_assets(repository, release, assets, complete=False)
    missing = [str(path) for name, path in assets.items() if name not in existing]
    if missing:
        _run("gh", "release", "upload", tag, *missing, "--repo", repository)
    verified = _draft(repository, tag, commit)
    if verified is None or verified["id"] != release_id or verified["body"] != body:
        raise ValueError("draft identity changed before publication")
    _verify_assets(repository, verified, assets, complete=True)
    subprocess.run(
        [
            "uv",
            "publish",
            "--trusted-publishing",
            "always",
            "--check-url",
            "https://pypi.org/simple",
            "--publish-url",
            "https://upload.pypi.org/legacy/",
            *(str(path) for path in distributions),
        ],
        check=True,
    )
    verified = _draft(repository, tag, commit)
    if verified is None or verified["id"] != release_id or verified["body"] != body:
        raise ValueError("draft identity changed after PyPI publication")
    _verify_assets(repository, verified, assets, complete=True)
    result = _release(
        _api(repository, f"releases/{release_id}", "--method", "PATCH", "-F", "draft=false")
    )
    if (
        result["id"] != release_id
        or result["draft"] is not False
        or result["tag_name"] != tag
        or result["target_commitish"] != commit
    ):
        raise ValueError("GitHub release publication was not confirmed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--plugin", type=Path, default=Path("build/plugin-release"))
    parser.add_argument("--notes", type=Path, default=Path("RELEASE_NOTES.md"))
    args = parser.parse_args()
    publish(
        os.environ["GITHUB_REPOSITORY"],
        os.environ["GITHUB_REF_NAME"],
        os.environ["GITHUB_SHA"],
        args.dist,
        args.plugin,
        args.notes,
    )


if __name__ == "__main__":
    main()
