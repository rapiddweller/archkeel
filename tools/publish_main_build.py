# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replace the rolling main build with the next set of six tested wheels (AD-863)."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
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
RELEASE = "main-build"
SUMS = "SHA256SUMS"
STAGING = ".staging"
PREVIOUS = ".old"
TITLE = "Latest main build (not a release)"
# Only these names are ours. Any other asset of the release stays.
OWN = re.compile(
    rf"archkeel-[^-]+-({'|'.join(map(re.escape, TAGS))})\.whl(\.staging)?"
    rf"|{SUMS}(\.staging|\.old)?"
)


def command(*args: str) -> str:
    done = subprocess.run(args, text=True, capture_output=True)
    if done.returncode:
        raise RuntimeError(f"{' '.join(args[:4])} failed: {done.stderr.strip()}")
    return done.stdout


def is_ancestor(old: str, new: str) -> bool:
    code = subprocess.run(["git", "merge-base", "--is-ancestor", old, new]).returncode
    if code > 1:
        raise RuntimeError(f"Cannot compare {old} with {new}")
    return code == 0


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def candidate(sha: str) -> list[Path]:
    wheels = sorted(Path("dist").glob("*.whl"))
    names = {wheel.name.removesuffix(".whl").split("-", 2)[-1] for wheel in wheels}
    versions = {wheel.name.split("-")[1] for wheel in wheels}
    if len(wheels) != 6 or names != TAGS or len(versions) != 1:
        raise ValueError(f"Expected six wheels of one version: {wheels}")
    (version,) = versions
    # hatch-vcs puts the abbreviated commit after "+g". A wheel of another commit must not pass.
    _, marker, abbreviated = version.partition("+g")
    if not marker or not sha.startswith(abbreviated):
        raise ValueError(f"The wheels of {version} were not built from {sha}")
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            metadata = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            lines = archive.read(metadata[0]).decode().splitlines() if metadata else []
            if archive.testzip() is not None or f"Version: {version}" not in lines:
                raise ValueError(f"{wheel.name} is damaged or carries another version")
    return wheels


def assets_of(repo: str, release: dict) -> dict[str, dict]:
    path = f"repos/{repo}/releases/{release['id']}/assets?per_page=100"
    return {item["name"]: item for item in json.loads(command("gh", "api", path))}


def rename(repo: str, asset: dict, name: str) -> None:
    command(
        "gh",
        "api",
        "-X",
        "PATCH",
        f"repos/{repo}/releases/assets/{asset['id']}",
        "-f",
        f"name={name}",
    )


def remove(repo: str, asset: dict) -> None:
    command("gh", "api", "-X", "DELETE", f"repos/{repo}/releases/assets/{asset['id']}")


def main() -> None:
    sha = os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    wheels = candidate(sha)

    release = json.loads(command("gh", "api", f"repos/{repo}/releases/tags/{RELEASE}"))
    if release["draft"] or not release["prerelease"]:
        raise ValueError(f"{RELEASE} must stay a published pre-release")
    published = re.search(r"^Commit: ([0-9a-f]{40})\s*$", release["body"] or "", re.MULTILINE)
    if published is None:
        raise ValueError(f"The notes of {RELEASE} name no commit")
    if not is_ancestor(published[1], sha):
        print(f"Skipped: {sha} is not newer than the published build {published[1]}")
        return

    # A name that is already public keeps its published bytes. A rerun may build other bytes.
    assets = assets_of(repo, release)
    final = {}
    for wheel in wheels:
        public = assets.get(wheel.name)
        if public is not None and not public.get("digest"):
            raise ValueError(f"The published {wheel.name} has no digest")
        final[wheel.name] = public["digest"] if public else digest(wheel.read_bytes())
    sums = "".join(
        f"{value.removeprefix('sha256:')}  {name}\n" for name, value in sorted(final.items())
    )
    sums_digest = digest(sums.encode())

    stage = Path("dist/staging")
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    wanted = {
        wheel.name + STAGING: (wheel, final[wheel.name])
        for wheel in wheels
        if wheel.name not in assets
    }
    if assets.get(SUMS, {}).get("digest") != sums_digest:
        (stage / (SUMS + STAGING)).write_text(sums, encoding="utf-8")
        wanted[SUMS + STAGING] = (stage / (SUMS + STAGING), sums_digest)
    for name, (source, expected) in wanted.items():
        have = assets.get(name)
        if have is not None and have.get("digest") == expected:
            continue
        if have is not None:
            remove(repo, have)
        upload = stage / name
        if not upload.exists():
            shutil.copyfile(source, upload)
        command("gh", "release", "upload", RELEASE, str(upload))

    # Every check passes before the first public name changes.
    assets = assets_of(repo, release)
    for name, value in final.items():
        if (assets.get(name) or assets.get(name + STAGING) or {}).get("digest") != value:
            raise ValueError(f"{name} is not complete or does not match; nothing was promoted")
    if sums_digest not in {assets.get(n, {}).get("digest") for n in (SUMS, SUMS + STAGING)}:
        raise ValueError("SHA256SUMS does not match; nothing was promoted")

    for name in final:
        if name not in assets:
            rename(repo, assets[name + STAGING], name)
    if assets.get(SUMS, {}).get("digest") != sums_digest:
        if SUMS in assets:
            if SUMS + PREVIOUS in assets:
                remove(repo, assets[SUMS + PREVIOUS])
            rename(repo, assets[SUMS], SUMS + PREVIOUS)
        rename(repo, assets[SUMS + STAGING], SUMS)

    date = command("git", "show", "-s", "--format=%cI", sha).strip()
    notes = Path("dist/notes.txt")
    notes.write_text(
        f"Development build, not a release.\n\nCommit: {sha}\nDate: {date}\n\n"
        + "".join(f"- {name}\n" for name in sorted(final))
        + f"\n```sh\npip install --pre --find-links {LINKS} archkeel\n"
        + f"uv tool install --prerelease allow --find-links {LINKS} archkeel\n```\n",
        encoding="utf-8",
    )
    command(
        "gh",
        "release",
        "edit",
        RELEASE,
        "--prerelease",
        "--latest=false",
        "--title",
        TITLE,
        "--notes-file",
        str(notes),
    )

    assets = assets_of(repo, release)
    if any(assets.get(name, {}).get("digest") != value for name, value in final.items()) or (
        assets.get(SUMS, {}).get("digest") != sums_digest
    ):
        raise ValueError("The promoted set does not match; old files stay")
    command(
        "gh",
        "api",
        "-X",
        "PATCH",
        f"repos/{repo}/git/refs/tags/{RELEASE}",
        "-f",
        f"sha={sha}",
        "-F",
        "force=true",
    )
    # Only now is the previous set obsolete. Names that are not ours stay.
    keep = {*final, SUMS}
    for name, asset in assets.items():
        if name not in keep and OWN.fullmatch(name):
            remove(repo, asset)


if __name__ == "__main__":
    main()
