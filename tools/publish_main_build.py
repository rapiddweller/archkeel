# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the six tested wheels as the rolling main build."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

TAGS = {
    "py3-none-manylinux_2_17_x86_64",
    "py3-none-manylinux_2_17_aarch64",
    "py3-none-musllinux_1_2_x86_64",
    "py3-none-macosx_10_12_x86_64",
    "py3-none-macosx_11_0_arm64",
    "py3-none-win_amd64",
}
LINKS = "https://github.com/rapiddweller/archkeel/releases/expanded_assets/main-build"


def command(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def main() -> None:
    wheels = sorted(Path("dist").glob("*.whl"))
    names = {wheel.name.removesuffix(".whl").split("-", 2)[-1] for wheel in wheels}
    versions = {wheel.name.split("-")[1] for wheel in wheels}
    if len(wheels) != 6 or names != TAGS or len(versions) != 1:
        raise ValueError(f"Expected six wheels of one version: {wheels}")
    sums = Path("dist/SHA256SUMS")
    sums.write_text(
        "".join(f"{hashlib.sha256(w.read_bytes()).hexdigest()}  {w.name}\n" for w in wheels),
        encoding="utf-8",
    )
    sha = os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    date = command("git", "show", "-s", "--format=%cI", sha).strip()
    notes = Path("dist/notes.txt")
    notes.write_text(
        f"Development build, not a release.\n\nCommit: {sha}\nDate: {date}\n\n"
        + "".join(f"- {w.name}\n" for w in wheels)
        + f"\n```sh\npip install --pre --find-links {LINKS} archkeel\n"
        + f"uv tool install --prerelease allow --find-links {LINKS} archkeel\n```\n",
        encoding="utf-8",
    )
    pages = json.loads(command("gh", "api", "--paginate", "--slurp", f"repos/{repo}/releases"))
    release = next(
        (item for page in pages for item in page if item["tag_name"] == "main-build"), None
    )
    if release is not None:
        raise ValueError("The main-build release already exists; do not replace its assets")
    if command("git", "ls-remote", "--tags", "origin", "refs/tags/main-build").strip():
        raise ValueError("The main-build tag already exists; do not replace it")
    command(
        "gh",
        "release",
        "create",
        "main-build",
        "--target",
        sha,
        "--draft",
        "--prerelease",
        "--latest=false",
        "--title",
        "Latest main build (not a release)",
        "--notes-file",
        str(notes),
        *map(str, wheels),
        str(sums),
    )
    pages = json.loads(command("gh", "api", "--paginate", "--slurp", f"repos/{repo}/releases"))
    release = next(
        (item for page in pages for item in page if item["tag_name"] == "main-build"), None
    )
    expected = {
        item.name: "sha256:" + hashlib.sha256(item.read_bytes()).hexdigest()
        for item in [*wheels, sums]
    }
    if (
        release is None
        or not release["draft"]
        or release["target_commitish"] != sha
        or len(release["assets"]) != len(expected)
        or {asset["name"]: asset["digest"] for asset in release["assets"]} != expected
    ):
        raise ValueError("The draft assets do not match the tested wheels")
    command(
        "gh",
        "release",
        "edit",
        "main-build",
        "--draft=false",
        "--prerelease",
        "--latest=false",
        "--title",
        "Latest main build (not a release)",
        "--notes-file",
        str(notes),
    )


if __name__ == "__main__":
    main()
